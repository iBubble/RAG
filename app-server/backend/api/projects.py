import json
import uuid
import time
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core.config import settings
from core.auth_deps import get_current_user, get_optional_user
from core.project_access import require_project_access
from core.database import get_db
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    visibility: str = "public"  # public / private
    project_type: str = "case"  # case(普通案件) / library(公共文档库)


class ProjectMetadata(BaseModel):
    # WHY: model_config extra="allow" 让前端可以传任意扩展字段（如 caseInfo），
    #      不被 Pydantic 校验丢弃。
    model_config = {"extra": "allow"}
    projectDate: Optional[str] = ""
    projectAddress: Optional[str] = ""
    constructionUnit: Optional[str] = ""
    preparationUnit: Optional[str] = ""
    competentUnit: Optional[str] = ""
    aiPersona: Optional[str] = ""


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    metadata: Optional[ProjectMetadata] = None


def _row_to_project(row) -> dict:
    """将 SQLite Row 转为前端兼容的项目 dict。"""
    p = dict(row)
    try:
        p["metadata"] = json.loads(p.pop("metadata_json", "{}"))
    except (json.JSONDecodeError, TypeError):
        p["metadata"] = {}
    p["createdAt"] = p.pop("created_at", "")
    # WHY: source_count 数据库字段从未被更新，改为动态扫描上传目录计算文件数
    p.pop("source_count", None)
    proj_dir = Path(settings.UPLOAD_DIR) / p["id"]
    if proj_dir.exists():
        import os
        count = 0
        for root, dirs, fnames in os.walk(str(proj_dir)):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fn in fnames:
                if not fn.startswith("."):
                    count += 1
        p["sourceCount"] = count
    else:
        p["sourceCount"] = 0
    # WHY: 兼容迁移前的旧数据（没有 project_type 字段）
    p.setdefault("project_type", "case")
    return p


@router.get("")
async def list_projects(user: dict = Depends(get_current_user)):
    """
    返回当前用户可见的项目：自己的所有项目 + 他人的公开项目。
    """
    with get_db() as conn:
        if user.get("role") == "admin":
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY sort_order ASC, created_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM projects
                   WHERE owner_id = ? OR visibility = 'public'
                   ORDER BY sort_order ASC, created_at DESC""",
                (user["id"],),
            ).fetchall()
    return [_row_to_project(r) for r in rows]


@router.post("")
async def create_project(data: ProjectCreate, user: dict = Depends(get_current_user)):
    """
    创建项目，记录所有者和可见性属性。
    WHY: project_type='library' 仅管理员可创建。
    """
    name = data.name.strip()
    if not name:
        raise HTTPException(400, "项目名称不能为空")

    # WHY: 公共文档库仅管理员可创建
    if data.project_type == "library" and user.get("role") != "admin":
        raise HTTPException(403, "仅管理员可创建公共文档库")

    with get_db() as conn:
        # 防止重名
        if conn.execute(
            "SELECT 1 FROM projects WHERE name = ?", (name,)
        ).fetchone():
            raise HTTPException(400, "存在同名项目")

        new_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None).isoformat()
        metadata_json = json.dumps({
            "projectDate": "",
            "projectAddress": "",
            "constructionUnit": "",
            "preparationUnit": "",
            "competentUnit": "",
        }, ensure_ascii=False)

        conn.execute(
            """INSERT INTO projects
               (id, name, created_at, source_count, owner_id,
                owner_name, visibility, metadata_json, project_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_id, name, now, 0,
                user["id"], user["username"],
                data.visibility, metadata_json, data.project_type,
            ),
        )

    # 记录日志
    from core.audit_log import log_operation
    log_operation(user["id"], "project_create", f"创建项目：{name}（{data.visibility}）")

    return {
        "id": new_id, "name": name, "createdAt": now,
        "sourceCount": 0, "owner_id": user["id"],
        "owner_name": user["username"],
        "visibility": data.visibility,
        "project_type": data.project_type,
        "metadata": {
            "projectDate": "", "projectAddress": "",
            "constructionUnit": "", "preparationUnit": "",
            "competentUnit": "",
        },
    }


class ProjectReorder(BaseModel):
    ids: list[str]


@router.put("/reorder")
async def reorder_projects(data: ProjectReorder, user: dict = Depends(get_current_user)):
    """
    重新排列项目卡片顺序。仅系统管理员可执行。
    """
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="只有系统管理员才允许重新调整项目卡片排序"
        )
    with get_db() as conn:
        for idx, proj_id in enumerate(data.ids):
            conn.execute(
                "UPDATE projects SET sort_order = ? WHERE id = ?",
                (idx, proj_id)
            )
    return {"status": "success", "message": "排序已更新"}


@router.get("/{project_id}")
async def get_project(project_id: str, user: dict = Depends(get_current_user)):
    """
    获取单个项目的详细信息（包含 metadata）。
    WHY: 私有项目仅 Owner/Admin 可读取。
    """
    if project_id == "linvis-status":
        return await get_linvis_status(user=user)

    p = require_project_access(project_id, user, write=False)
    # 兼容旧数据没 metadata 的情况
    if "metadata" not in p:
        p["metadata"] = {
            "projectDate": "", "projectAddress": "",
            "constructionUnit": "", "preparationUnit": "",
            "competentUnit": "",
        }
    return p


@router.put("/{project_id}")
async def update_project(project_id: str, data: ProjectUpdate, user: dict = Depends(get_current_user)):
    """
    更新项目基础信息或元数据。
    WHY: 仅 Owner/Admin 可编辑项目配置。
    """
    p = require_project_access(project_id, user, write=True)

    with get_db() as conn:
        if data.name is not None:
            conn.execute(
                "UPDATE projects SET name = ? WHERE id = ?",
                (data.name.strip(), project_id),
            )

        if data.metadata is not None:
            # 深度合并 metadata
            existing_meta = p.get("metadata", {})
            for key, value in data.metadata.dict().items():
                existing_meta[key] = value
            conn.execute(
                "UPDATE projects SET metadata_json = ? WHERE id = ?",
                (json.dumps(existing_meta, ensure_ascii=False), project_id),
            )

    # 返回更新后的数据
    return require_project_access(project_id, user, write=False)


class VisibilityUpdate(BaseModel):
    visibility: str  # public / private

@router.put("/{project_id}/visibility")
async def update_visibility(project_id: str, data: VisibilityUpdate, user: dict = Depends(get_current_user)):
    """快捷切换项目可见性（私有/公开）。仅 owner 或管理员可操作。"""
    p = require_project_access(project_id, user, write=True)

    with get_db() as conn:
        conn.execute(
            "UPDATE projects SET visibility = ? WHERE id = ?",
            (data.visibility, project_id),
        )

    from core.audit_log import log_operation
    log_operation(user["id"], "project_visibility", f"修改项目可见性：{p['name']} → {data.visibility}")

    p["visibility"] = data.visibility
    return p


class IconUpdate(BaseModel):
    icon: str  # emoji 图标

@router.put("/{project_id}/icon")
async def update_icon(project_id: str, data: IconUpdate, user: dict = Depends(get_current_user)):
    """快捷修改项目图标。仅 owner 或管理员可操作。"""
    p = require_project_access(project_id, user, write=True)

    with get_db() as conn:
        conn.execute(
            "UPDATE projects SET icon = ? WHERE id = ?",
            (data.icon, project_id),
        )

    p["icon"] = data.icon
    return p

# ----------------- 项目彻底删除 -----------------

@router.delete("/{project_id}")
async def delete_project(project_id: str, user: dict = Depends(get_current_user)):
    """
    彻底删除一个项目及其所有关联数据：
    - SQLite projects 表记录
    - uploads/{project_id}/ 下的所有上传文件
    - data/documents/{project_id}/ 下的所有归档文档
    - data/templates/{project_id}.json 范文模板
    """
    p = require_project_access(project_id, user, write=True)

    # 1. 从数据库中移除
    with get_db() as conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.execute("DELETE FROM web_sources WHERE project_id = ?", (project_id,))

    # 2. 删除上传文件目录
    uploads_dir = Path(settings.UPLOAD_DIR) / project_id
    if uploads_dir.exists():
        shutil.rmtree(uploads_dir, ignore_errors=True)

    # 3. 删除归档文档目录
    docs_dir = Path(settings.DATA_DIR) / "documents" / project_id
    if docs_dir.exists():
        shutil.rmtree(docs_dir, ignore_errors=True)

    # 4. 删除范文模板
    template_file = Path(settings.DATA_DIR) / "templates" / f"{project_id}.json"
    if template_file.exists():
        template_file.unlink()

    # 5. 删除写作范文（exemplar）
    exemplar_file = Path(settings.DATA_DIR) / "exemplars" / f"{project_id}.json"
    if exemplar_file.exists():
        exemplar_file.unlink()

    # 6. 删除知识库表结构及切片配置
    knowledge_dir = Path(settings.DATA_DIR) / "knowledge" / project_id
    if knowledge_dir.exists():
        shutil.rmtree(knowledge_dir, ignore_errors=True)

    # 7. 删除向量库中的切片数据
    try:
        from core.vector_store import delete_by_project_id as qdrant_delete_by_project
        qdrant_delete_by_project(project_id)
    except Exception as e:
        logger.warning(f"删除 Qdrant 项目数据异常: {e}")

# 缓存高耗时的学习进度及 Redis 队列状态，避免 4.5s 频繁轮询轰炸 Qdrant/Neo4j 数据库
_LINVIS_STATS_CACHE = None
_LINVIS_STATS_CACHE_TIME = 0.0
_LINVIS_STATS_CACHE_TTL = 15.0  # 缓存 15 秒

@router.get("/linvis-status")
async def get_linvis_status(user: dict = Depends(get_current_user)):
    """
    获取 Linvis 看板所需要的实时状态数据。
    支持返回 7 个 Agent 角色所对应的真实后端队列与任务，并根据搞笑程度 funny_level 注入随机摸鱼事件。
    """
    from api.admin import _read_system_settings, get_learning_progress
    import time
    
    settings_data = _read_system_settings()
    active_level = settings_data.get("active_level", settings_data.get("funny_level", "low"))

    # 1. 采集全局学习进度与队列深度（带 15s 全局缓存逻辑，防超频轮询死锁）
    global _LINVIS_STATS_CACHE, _LINVIS_STATS_CACHE_TIME
    now = time.time()
    if _LINVIS_STATS_CACHE is None or (now - _LINVIS_STATS_CACHE_TIME) > _LINVIS_STATS_CACHE_TTL:
        try:
            progress_list = await get_learning_progress(user=user)
            
            slow_queue_tasks = 0
            fast_queue_tasks = 0
            try:
                from core.redis_client import get_redis
                r = get_redis()
                if r:
                    slow_queue_tasks = r.llen("slow_queue") or 0
                    fast_queue_tasks = r.llen("celery") or 0
            except Exception:
                pass
                
            _LINVIS_STATS_CACHE = {
                "progress_list": progress_list,
                "slow_queue_tasks": slow_queue_tasks,
                "fast_queue_tasks": fast_queue_tasks
            }
            _LINVIS_STATS_CACHE_TIME = now
        except Exception as _cache_e:
            logger.error(f"[linvis-status] 获取看板数据并更新缓存失败: {_cache_e}")
            if _LINVIS_STATS_CACHE is None:
                _LINVIS_STATS_CACHE = {
                    "progress_list": [],
                    "slow_queue_tasks": 0,
                    "fast_queue_tasks": 0
                }
                
    progress_list = _LINVIS_STATS_CACHE["progress_list"]
    slow_queue_tasks = _LINVIS_STATS_CACHE["slow_queue_tasks"]
    fast_queue_tasks = _LINVIS_STATS_CACHE["fast_queue_tasks"]

    total_projects = len(progress_list)
    total_files = sum(p["vectorization"]["total"] for p in progress_list)
    completed_files = sum(p["vectorization"]["completed"] for p in progress_list)
    total_chunks = sum(p["vectorization"]["total_chunks"] for p in progress_list)
    total_entities = sum(p["graph_rag"]["total_entities"] for p in progress_list)

    completed_percent = round(completed_files / total_files * 100, 2) if total_files > 0 else 100.0

    # 2. 统计当前正在活跃的项目 and 任务
    active_vectorizer = None
    active_graph = None
    active_summary = None
    active_precompute = None

    for p in progress_list:
        if p["vectorization"]["current_task"]:
            active_vectorizer = {"project_name": p["name"], "filename": p["vectorization"]["current_task"]["filename"]}
        if p["graph_rag"]["current_task"]:
            active_graph = {"project_name": p["name"], "filename": p["graph_rag"]["current_task"]["filename"]}
        if p["community_summary"]["status"] in ("running", "queued", "processing"):
            active_summary = {
                "project_name": p["name"], 
                "filename": p["community_summary"]["current_task"].get("filename", "社区提炼") if p["community_summary"]["current_task"] else "聚类摘要中"
            }
        # 修正 precompute 状态解析，遍历三个子模式状态，移入循环体内
        if p.get("precompute") and isinstance(p["precompute"], dict):
            for mode, mdata in p["precompute"].items():
                if mdata.get("status") in ("running", "queued"):
                    active_precompute = {
                        "project_name": p["name"],
                        "filename": f"预计算({mode}): {mdata.get('current_task', {}).get('section_title') or '排队中...'}"
                    }
                    break

    # 对 active_summary 增加 Redis 模糊扫描的强力兜底逻辑，绕过 15s 的全局缓存
    if not active_summary:
        try:
            from core.redis_client import get_redis
            r = get_redis()
            if r:
                keys = r.keys("community_summary:status:*")
                for k in keys:
                    status_val = r.get(k)
                    if status_val == "processing" or (isinstance(status_val, bytes) and status_val.decode() == "processing"):
                        pid = k.split(":")[-1]
                        pname = "进行中项目"
                        try:
                            from core.project_access import _read_projects
                            for proj in _read_projects():
                                if proj["id"] == pid:
                                    pname = proj.get("name", "本案项目")
                                    break
                        except:
                            pass
                        
                        cur_task_val = r.get(f"community_summary:current_task:{pid}")
                        cur_task_name = "聚类摘要中"
                        if cur_task_val:
                            cur_task_name = cur_task_val.decode() if isinstance(cur_task_val, bytes) else str(cur_task_val)
                            
                        active_summary = {
                            "project_name": pname,
                            "filename": cur_task_name
                        }
                        break
        except Exception as _e_summary:
            logger.warning(f"扫 Redis 兜底 active_summary 失败: {_e_summary}")

    # 3. 统计 Redis 的 slow_queue 深度
    # 真实队列任务数量已在前文缓存获取中统计并缓存，此处直接占位防止语法错

    # 4. 生成 7 个 Agent 具体状态（如果空闲，则根据 funny_level 决定是否摸鱼或睡觉）
    import random
    
    funny_pool = {
        "vectorizer": {
            "low": ["正在擦拭数据光纤", "整理数据库抽屉", "给向量数据贴标签"],
            "medium": ["偷偷把 Bug 伪装成新功能", "偷偷用 Qwen 给小貔写情书", "给数据浇水盼其早日向量化"],
            "high": ["删库跑路准备中", "正在手写 0 和 1 替代 BGE 模型", "在内存里偷偷斗地主", "因为切片切到手指正在哭泣"]
        },
        "graph": {
            "low": ["绘制实体连接线", "消除同义实体", "整理关系网络"],
            "medium": ["偷偷织一张蜘蛛网挂在局长头上", "八卦小貔和小理的暗恋关系", "试图用三元组表达午饭吃什么"],
            "high": ["被关系连线缠住动弹不得", "正在计划把所有企业连成同义实体", "在 Neo4j 里偷偷种菜", "抽取了'局长-属于-加班界'的三元组"]
        },
        "summary": {
            "low": ["进行社区发现聚类", "撰写社区摘要", "分析网络拓扑"],
            "medium": ["把 Agent 们分成摸鱼和加班两派", "总结今天办公室的核心八卦", "将大饼图切成披萨吃掉"],
            "high": ["正在对老板的发言做脱水处理", "试图将自己聚类到高富帅社区", "总结出了 100 条如何推卸责任的摘要", "因为计算社区摘要导致脑瓜子嗡嗡响"]
        },
        "precompute": {
            "low": ["预热深度学习模型", "预计算全文大纲", "缓存常见法条"],
            "medium": ["提前猜测小律下一步想查什么", "用预计算能力预测彩票中", "给明天的天气做一次预推理"],
            "high": ["正在强行用算盘加速 GPU", "预计算今晚几点下班能不被局长抓住", "脑补自己评上先进工作者的场景", "算得太快系统有些发烧"]
        },
        "chat": {
            "low": ["接待消费维权咨询", "查询市监法规库", "翻阅陈年执法卷宗"],
            "medium": ["偷偷往水杯里加红枸杞", "整理市场巡查制服", "模仿局长的威严表情"],
            "high": ["正在用 Ollama 写执法报告", "对投诉人发出'喵喵'的声音", "在草稿纸上画局长的简笔画", "被连珠炮般的投诉问得直翻白眼"]
        },
        "legal": {
            "low": ["起草行政处罚决定", "审阅案件线索资料", "拟定专项整治方案"],
            "medium": ["痛斥违规企业瞎编乱造", "在处罚决定书里偷偷加入错别字", "用茶杯盖敲桌子维持听证会秩序"],
            "high": ["把投诉人和被投诉人的名字写反了", "正在拍桌子大喊'停业整顿！'", "用大模型生成了一份罚款依据", "被复杂案情逼得想去出家"]
        },
        "service": {
            "low": ["进行食品安全风险排查", "匹配特种设备检验服务", "审查霸王条款"],
            "medium": ["在整改报告里寻找错别字和标点符号问题", "试图说服小向买一份防脱发保险", "帮大家拟定消费提示"],
            "high": ["在提示里偷偷加上'最终解释权归市监局所有'", "正对着一份奇葩投诉目瞪口呆", "正偷偷上网看如何跳槽到大厂", "在审查'地沟油作坊'时血压飙升"]
        },
        "planner": {
            "low": ["正在分析投诉举报类型", "规划最优核查路径", "评估证据关联度"],
            "medium": ["在白板上画了一棵超大的执法决策树", "试图用甘特图管理所有案件的进度", "给每个案件贴上优先级小红旗"],
            "high": ["大喊'此案我来督办！'", "正在用彩色粉笔在白板上画突击检查图", "因为投诉太多而开始头脑风暴", "把待办案件写满了整面墙"]
        },
        "checker": {
            "low": ["正在校验罚款金额准确性", "核实法条编号是否适用", "检查执法日期合规性"],
            "medium": ["对数据精确到小数点后第5位表示不满", "发现了一个可疑的统计数字正在追查", "试图验证报告里引用的每一个百分比"],
            "high": ["拍着桌子说'这数字不对！'", "大喊'我不信！让我再算一遍！'", "因为找到计算错误而兴奋得跳起来", "正在用计算器验证大模型的加减乘除"]
        },
        "auditor": {
            "low": ["主持智能体圆桌会议", "对争议条款进行最终裁决", "润色终稿措辞"],
            "medium": ["给校验员倒一杯咖啡安抚情绪", "试图在各智能体之间和稀泥", "修改最终报告的字体排版"],
            "high": ["大手一挥高喊'就这么定了！'", "正在戴上法官假发准备宣判", "因为审计报告太多头晕眼花", "正在给优秀智能体发小红花"]
        }
    }

    def get_agent_status(agent_key: str, active_task: dict | None):
        if active_task:
            return {
                "status": "working",
                "funny_event": None,
                "current_project": active_task.get("project") or active_task.get("project_name") or "系统任务",
                "current_task": active_task.get("task") or active_task.get("filename") or "处理中..."
            }
        
        # 闲置状态，根据 active_level 决定是否搞怪活跃
        p_active = 0.2 if active_level == "low" else (0.55 if active_level == "medium" else 0.85)
        if random.random() < p_active:
            event = random.choice(funny_pool[agent_key][active_level])
            
            # ─── 动态替换搞笑事件中其他 Agent 的代称为当前系统配置的真实名字 ───
            names_map = {
                "小向": settings_data.get("agent_vectorizer_name") or "小向",
                "小图": settings_data.get("agent_graph_name") or "小图",
                "小聚": settings_data.get("agent_summary_name") or "小聚",
                "小预": settings_data.get("agent_precompute_name") or "小预",
                "小貔": settings_data.get("agent_chat_name") or "小咨",
                "小咨": settings_data.get("agent_chat_name") or "小咨",
                "法老": settings_data.get("agent_legal_name") or "法老",
                "小律": settings_data.get("agent_service_name") or "小律",
            }
            for default_name, real_name in names_map.items():
                clean_real = real_name.split(" ")[0].split("(")[0].split("（")[0]
                event = event.replace(default_name, clean_real)

            return {
                "status": "funny",
                "funny_event": event,
                "current_project": None,
                "current_task": None
            }
        
        # 普通闲置或睡觉
        status = random.choice(["idle", "sleeping"])
        return {
            "status": status,
            "funny_event": None,
            "current_project": None,
            "current_task": None
        }

    from core.redis_client import get_agent_active
    active_chat = get_agent_active("chat")
    active_legal = get_agent_active("legal")
    active_service = get_agent_active("service")
    active_planner = get_agent_active("planner")
    active_checker = get_agent_active("checker")
    active_auditor = get_agent_active("auditor")

    agents = {
        "vectorizer": get_agent_status("vectorizer", active_vectorizer),
        "graph": get_agent_status("graph", active_graph),
        "summary": get_agent_status("summary", active_summary),
        "precompute": get_agent_status("precompute", active_precompute),
        "chat": get_agent_status("chat", active_chat),
        "legal": get_agent_status("legal", active_legal),
        "service": get_agent_status("service", active_service),
        "planner": get_agent_status("planner", active_planner),
        "checker": get_agent_status("checker", active_checker),
        "auditor": get_agent_status("auditor", active_auditor)
    }

    system_status = {
        "active_tasks": slow_queue_tasks + fast_queue_tasks,
        "active_level": active_level,
        "funny_level": active_level,
        "linvis_name": settings_data.get("linvis_name", "麟维斯"),
        "whiteboard_items": settings_data.get("whiteboard_items", "").split(",") if settings_data.get("whiteboard_items") else [],
        "visible_agents": settings_data.get("visible_agents", "").split(",") if settings_data.get("visible_agents") else [],
        "whiteboard": {
            "total_projects": total_projects,
            "total_files": total_files,
            "completed_percent": completed_percent,
            "total_chunks": total_chunks,
            "total_entities": total_entities,
            "slow_queue_tasks": slow_queue_tasks,
            "fast_queue_tasks": fast_queue_tasks
        }
    }
    
    # 将自定义的 agent 配置项注入 system_status
    for k, v in settings_data.items():
        if k.startswith("agent_"):
            system_status[k] = v

    return {
        "system_status": system_status,
        "agents": agents
    }

    # 8. 删除图谱数据库中的节点和关系
    try:
        from core.graph_rag import graph_engine
        graph_engine.delete_by_project_id(project_id)
    except Exception as e:
        logger.warning(f"删除 Neo4j 项目数据异常: {e}")

    # 记录操作日志
    from core.audit_log import log_operation
    log_operation(user["id"], "project_delete", f"彻底删除项目：{p['name']}")

    return {"message": f"项目 {p['name']} 已彻底删除，相关资源均已清空"}


@router.get("/{project_id}/graph/sample")
async def get_graph_sample(project_id: str, limit: int = 150, user: dict = Depends(get_current_user)):
    """
    获取知识图谱实体的部分样本数据，用于前端力导向图可视化渲染。
    为防止前端卡顿，限制最多返回 limit 个实体节点及其相关边。
    """
    require_project_access(project_id, user, write=False)
    from core.graph_rag import GraphRAGEngine
    import logging
    logger = logging.getLogger(__name__)
    
    engine = GraphRAGEngine()
    engine._ensure_connection()
    
    # 随机拉取节点和它们的相互关系
    query = """
    MATCH (n)-[r]->(m)
    WHERE n.project_id = $project_id AND m.project_id = $project_id
    WITH n, r, m LIMIT $limit
    RETURN n, r, m
    """
    
    try:
        res = engine._driver.session().run(query, project_id=project_id, limit=limit)
        nodes_dict = {}
        links = []
        
        for record in res:
            n = record["n"]
            m = record["m"]
            r = record["r"]
            
            if n.element_id not in nodes_dict:
                nodes_dict[n.element_id] = {
                    "id": n.element_id,
                    "name": n.get("name", "Unknown"),
                    "group": n.get("type", "Unknown")
                }
            if m.element_id not in nodes_dict:
                nodes_dict[m.element_id] = {
                    "id": m.element_id,
                    "name": m.get("name", "Unknown"),
                    "group": m.get("type", "Unknown")
                }
                
            links.append({
                "source": n.element_id,
                "target": m.element_id,
                "label": type(r).__name__  # Relationship type
            })
            
        return {
            "nodes": list(nodes_dict.values()),
            "links": links
        }
    except Exception as e:
        logger.error(f"Failed to load graph sample: {e}")
        return {"nodes": [], "links": []}


# ----------------- 持久化归档文档（仍使用 JSON 文件存储）-----------------
DOCUMENTS_DIR = Path(settings.DATA_DIR) / "documents"

class SavedDocument(BaseModel):
    id: str
    title: str
    content: str
    timestamp: int
    tokens: int
    sections: Optional[list] = []      # WHY: 大纲章节结构随文档一起持久化，用于还原编辑状态
    isAutoSave: Optional[bool] = False  # WHY: 区分自动保存与手动保存的归档记录

@router.get("/{project_id}/documents")
async def list_documents(project_id: str, user: dict = Depends(get_current_user)):
    """WHY: 只返回文档摘要（不含 content/sections 全文），避免浏览器 OOM。
    前端列表只需 id/title/timestamp/tokens/isAutoSave/sectionCount 即可渲染。
    用户点击加载时，再调 GET /{project_id}/documents/{doc_id} 按需拉取完整内容。
    """
    require_project_access(project_id, user, write=False)
    proj_dir = DOCUMENTS_DIR / project_id
    if not proj_dir.exists():
        return []
    docs = []
    for fp in proj_dir.glob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            docs.append({
                "id": data.get("id"),
                "title": data.get("title", ""),
                "timestamp": data.get("timestamp", 0),
                "tokens": data.get("tokens", 0),
                "isAutoSave": data.get("isAutoSave", False),
                "sectionCount": len(data.get("sections", [])),
            })
        except Exception:
            pass
    docs.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return docs


@router.get("/{project_id}/documents/{doc_id}")
async def get_document(project_id: str, doc_id: str, user: dict = Depends(get_current_user)):
    """WHY: 按需加载单个文档的完整内容（含 sections/content），
    仅在用户点击"加载"或"下载"时调用，避免列表页一次性加载全部文档。
    同时清洗已存在历史文档中的协同过程垃圾字。
    """
    require_project_access(project_id, user, write=False)
    fp = DOCUMENTS_DIR / project_id / f"{doc_id}.json"
    if not fp.exists():
        raise HTTPException(404, "文档不存在")
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        if data.get("content"):
            data["content"] = clean_collaborative_artifacts(data["content"])
        if data.get("sections"):
            for sec in data["sections"]:
                if isinstance(sec, dict) and "content" in sec and sec["content"]:
                    sec["content"] = clean_collaborative_artifacts(sec["content"])
        return data
    except Exception as e:
        raise HTTPException(500, f"加载并清洗文档失败: {str(e)}")


def clean_collaborative_artifacts(content: str) -> str:
    """
    清除文档中在协同起草、质疑、大BOSS裁决过程中产生的过程性引导和思考词，
    确保成品文档仅包含最终的裁决正文（或流中断时的第一起草稿），且不破坏开头的大纲标题。
    """
    if not content:
        return content
    import re
    from api.admin import _read_system_settings
    sys_settings = _read_system_settings()
    contrarian_name = sys_settings.get("collab_contrarian_name", "【协同】审查员")
    arbiter_name = sys_settings.get("collab_arbiter_name", "【协同】仲裁官")
    esc_contrarian = re.escape(contrarian_name)
    esc_arbiter = re.escape(arbiter_name)
    
    expert_match = re.search(r'(?:⚖️|\[段落起草专家\])', content)
    boss_match = re.search(fr'(?:👑|\[大BOSS\]|\[{esc_arbiter}\]).*?(?:最终措辞润色|逻辑修正)', content)
    
    if expert_match and boss_match and boss_match.start() > expert_match.start():
        boss_end_pattern = fr'(?:👑|\[大BOSS\]|\[{esc_arbiter}\]).*?(?:最终措辞润色|逻辑修正).*?(?:</p>|\n)\s*'
        end_match = re.search(boss_end_pattern, content, flags=re.DOTALL)
        if end_match:
            header_part = content[:expert_match.start()].strip()
            header_part = re.sub(r'(?:⚖️|\u2696|\uFE0F|\s|\*|<strong>|<p>|<hr\s*/?>)+$', '', header_part).strip()
            body_part = content[end_match.end():].strip()
            
            # 如果大BOSS最终输出非空，则返回最终成品
            text_len = len(re.sub(r'<[^>]*>', '', body_part).strip())
            if text_len > 5:
                separator = '\n\n' if not header_part.endswith('>') else ''
                return (header_part + separator + body_part).strip()
                
    # 如果大BOSS最终输出为空，或者仅有初稿，则退回到只切除起草专家引导语并保留初稿
    if expert_match:
        expert_end_pattern = r'(?:⚖️|\[段落起草专家\]).*?正在起草章节初稿.*?(?:</p>|\n)\s*'
        end_match = re.search(expert_end_pattern, content, flags=re.DOTALL)
        if end_match:
            header_part = content[:expert_match.start()].strip()
            header_part = re.sub(r'(?:⚖️|\u2696|\uFE0F|\s|\*|<strong>|<p>|<hr\s*/?>)+$', '', header_part).strip()
            
            draft_part = content[end_match.end():].strip()
            # 如果有小杠或大BOSS引导语，切断之后的废话
            contrarian_match = re.search(fr'(?:🤨|\[小杠\]|\[{esc_contrarian}\]|👑|\[大BOSS\]|\[{esc_arbiter}\]|---|<blockquote|<hr)', draft_part)
            if contrarian_match:
                draft_part = draft_part[:contrarian_match.start()].strip()
                draft_part = re.sub(r'(?:⚖️|\u2696|\uFE0F|\s|\*|<strong>|<p>|<hr\s*/?>)+$', '', draft_part).strip()
                
            separator = '\n\n' if not header_part.endswith('>') else ''
            return (header_part + separator + draft_part).strip()
            
    return content


@router.post("/{project_id}/documents")
async def save_document(project_id: str, doc: SavedDocument, user: dict = Depends(get_current_user)):
    require_project_access(project_id, user, write=True)
    
    # 全方位清洗文档数据，移除协同过程性废话
    if doc.content:
        doc.content = clean_collaborative_artifacts(doc.content)
    if doc.sections:
        for sec in doc.sections:
            if isinstance(sec, dict) and "content" in sec and sec["content"]:
                sec["content"] = clean_collaborative_artifacts(sec["content"])
                
    proj_dir = DOCUMENTS_DIR / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    fp = proj_dir / f"{doc.id}.json"
    fp.write_text(json.dumps(doc.dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    # WHY: 仅记录手动保存到审计日志，自动保存每2分钟一次会产生大量噪音
    if not doc.isAutoSave:
        from core.audit_log import log_operation
        section_count = len(doc.sections) if doc.sections else 0
        log_operation(user["id"], "document_save", f"保存文档：{doc.title}（{section_count}个章节, {doc.tokens}字）")

    return doc.dict()

@router.delete("/{project_id}/documents/{doc_id}")
async def delete_document(project_id: str, doc_id: str, user: dict = Depends(get_current_user)):
    require_project_access(project_id, user, write=True)
    fp = DOCUMENTS_DIR / project_id / f"{doc_id}.json"
    if fp.exists():
        fp.unlink()
    return {"message": "deleted"}

# ----------------- 项目级范文模板隔离存储（仍使用 JSON 文件存储）-----------------
# WHY: 每个项目拥有独立的范文大纲，新建项目默认为空。
#      范文数据存在 data/templates/{project_id}.json 中。
TEMPLATES_DIR = Path(settings.DATA_DIR) / "templates"

class TemplateData(BaseModel):
    title: str
    sections: list

@router.get("/{project_id}/template")
async def get_template(project_id: str, user: dict = Depends(get_current_user)):
    """WHY: 对超长章节内容截断后返回，防止 Tiptap 渲染 10 万字章节导致浏览器 OOM。
    截断不修改磁盘文件，仅影响 API 响应。
    同时清洗历史大纲中遗留的协同垃圾字。
    """
    require_project_access(project_id, user, write=False)
    fp = TEMPLATES_DIR / f"{project_id}.json"
    if not fp.exists():
        return {"title": "", "sections": []}
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        # WHY: 单个章节超过 8000 字会让 Tiptap 编辑器卡顿甚至 OOM。
        #      截断到 8000 字并附加提示，保护浏览器。
        _MAX_SECTION_CHARS = 8000
        sections = data.get("sections", [])
        _truncated = 0
        for s in sections:
            if isinstance(s, dict):
                content = s.get("content", "")
                if content:
                    content = clean_collaborative_artifacts(content)
                    s["content"] = content
                if len(content) > _MAX_SECTION_CHARS:
                    s["content"] = (
                        content[:_MAX_SECTION_CHARS]
                        + f"\n\n> ⚠️ 本章节原文共 {len(content):,} 字，"
                        f"为防止浏览器卡顿已截断显示前 {_MAX_SECTION_CHARS} 字。"
                        f"完整内容已保存，可通过导出获取。"
                    )
                    _truncated += 1
        if _truncated:
            print(
                f"✂️ Template 截断 | 项目={project_id} | "
                f"{_truncated}/{len(sections)} 个章节超限被截断",
                flush=True,
            )
        return data
    except Exception:
        return {"title": "", "sections": []}

@router.post("/{project_id}/template")
async def save_template(project_id: str, data: TemplateData, user: dict = Depends(get_current_user)):
    require_project_access(project_id, user, write=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    fp = TEMPLATES_DIR / f"{project_id}.json"
    
    # 强制在保存模板大纲时全方位清洗协同垃圾字
    sections = data.sections
    if sections:
        for s in sections:
            if isinstance(s, dict) and "content" in s and s["content"]:
                s["content"] = clean_collaborative_artifacts(s["content"])
                
    fp.write_text(json.dumps(data.dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return data.dict()

@router.get("/{project_id}/precompute_status")
async def get_precompute_status(project_id: str, user: dict = Depends(get_current_user)):
    """
    获取项目的预计算（向量化）进度。
    WHY: 用户上传大量文件后，前端需要显示整体百分比。
    """
    require_project_access(project_id, user, write=False)
    
    from pathlib import Path
    import os
    import hashlib
    from core.status_tracker import get_file_status, EXCLUDED_STATUSES

    project_dir = Path(settings.UPLOAD_DIR) / project_id
    if not project_dir.exists():
        return {"total": 0, "completed": 0, "excluded": 0, "percent": 0, "status": "completed"}
        
    total_files = 0
    completed_files = 0
    excluded_files = 0
    
    # 递归遍历项目目录（跳过隐藏文件和 .job_states 目录本身）
    for root, dirs, files in os.walk(str(project_dir)):
        if ".job_states" in dirs:
            dirs.remove(".job_states")
        if ".cache" in dirs:
            dirs.remove(".cache")
            
        for f in files:
            if f.startswith(".") or f.endswith(".lock"):
                continue
            
            # 计算 File ID (MD5)，逻辑需与 api/files.py 保持高度一致
            path = Path(root) / f
            rel_path = str(path.relative_to(Path(settings.UPLOAD_DIR)))
            file_id = hashlib.md5(f"{project_id}_{rel_path}".encode("utf-8")).hexdigest()
            
            status_data = get_file_status(project_id, file_id)
            st = status_data.get("status", "pending")
            
            # WHY: 使用共享常量排除不可用文件，保证与管理员看板口径完全一致
            if st in EXCLUDED_STATUSES:
                excluded_files += 1
                continue
            
            total_files += 1
            if st in ("vectorized", "graph_queued", "graph_extracting"):
                completed_files += 1
                
    percent = round(completed_files / total_files * 100, 2) if total_files > 0 else 100.0
    return {
        "total": total_files,
        "completed": completed_files,
        "excluded": excluded_files,
        "percent": percent,
        "status": "completed" if percent >= 100 else "processing"
    }


# ----------------- 活跃用户状态(心跳) -----------------

# 内存字典，用于记录项目中活跃用户的上一次心跳时间
# 格式: { project_id: { user_id: { "username": str, "avatar": str, "last_active": float } } }
ACTIVE_USERS: dict[str, dict[str, dict]] = {}
PRESENCE_TIMEOUT = 120  # 120 秒超时

class PresenceReport(BaseModel):
    active_tab: Optional[str] = ""
    active_sub_tab: Optional[str] = ""
    is_generating: Optional[bool] = False

class PresenceResponse(BaseModel):
    active_users: list[dict]

@router.post("/{project_id}/presence", response_model=PresenceResponse)
async def update_presence(project_id: str, report: PresenceReport, user: dict = Depends(get_current_user)):
    """
    接收用户在项目内的心跳请求，并返回当前该项目下的所有活跃用户（包括自己，供调试或前端过滤使用）。
    """
    require_project_access(project_id, user, write=False)
    logger.info(f"[update_presence] project_id={project_id} report={report.dict()} user={user.get('username')}")

    project_name = "在线法律助手"
    try:
        from core.project_access import _read_projects
        for p in _read_projects():
            if p["id"] == project_id:
                project_name = p.get("name", "未命名项目")
                break
    except Exception:
        pass

    try:
        from core.redis_client import set_agent_active, get_redis
        tab = report.active_tab
        sub_tab = report.active_sub_tab
        is_gen = report.is_generating
        
        r = get_redis()
        
        if tab == "智能助手":
            if is_gen:
                set_agent_active("chat", "正在思考并生成回答...", project_name, duration=90)
            else:
                set_agent_active("chat", "正在解答业务咨询", project_name, duration=90)
        elif tab == "法律事务专家":
            task_desc = f"正在起草/分析: {sub_tab}" if sub_tab else "正在进行行政事务分析"
            set_agent_active("legal", task_desc, project_name, duration=90)
        elif tab == "常法服务":
            set_agent_active("service", "正在处理日常业务工作", project_name, duration=90)
        elif tab == "合同审查":
            set_agent_active("service", "正在进行文档合规性审查", project_name, duration=90)
        elif tab == "定制文档":
            set_agent_active("service", "正在起草与编辑项目工作文档", project_name, duration=90)
    except Exception as presence_e:
        logger.warning(f"上报心跳同步 Agent 看板状态失败: {presence_e}")

    now = time.time()
    if project_id not in ACTIVE_USERS:
        ACTIVE_USERS[project_id] = {}

    ACTIVE_USERS[project_id][user["id"]] = {
        "id": user["id"],
        "username": user.get("username", "未知用户"),
        "avatar": user.get("avatar", ""),
        "last_active": now
    }

    # 清理超时用户
    active_list = []
    keys_to_remove = []
    for uid, info in ACTIVE_USERS[project_id].items():
        if now - info["last_active"] > PRESENCE_TIMEOUT:
            keys_to_remove.append(uid)
        else:
            if uid != user["id"]:  # 不包含自己
                active_list.append({
                    "id": info["id"],
                    "username": info["username"],
                    "avatar": info["avatar"]
                })

    for uid in keys_to_remove:
        del ACTIVE_USERS[project_id][uid]

    return {"active_users": active_list}


# ----------------- 公共文档引用管理 -----------------

class RefCreate(BaseModel):
    library_id: str
    file_ids: list[str] = []  # 空=引用全部文件


@router.post("/{case_id}/refs")
async def add_ref(case_id: str, data: RefCreate, user: dict = Depends(get_current_user)):
    """
    为案件添加其他公开项目/文档库的引用。
    WHY: 引用而非复制——公共文档或公开项目文档只存一份，多案件共享检索。
    """
    require_project_access(case_id, user, write=False)

    if data.library_id == case_id:
        raise HTTPException(400, "不能引用当前项目自身的文档")

    # 验证 library_id 是公开项目或公共文档库
    with get_db() as conn:
        lib = conn.execute(
            "SELECT project_type, visibility FROM projects WHERE id = ?", (data.library_id,)
        ).fetchone()
        if not lib:
            raise HTTPException(404, "目标项目不存在")
        
        lib_dict = dict(lib)
        if lib_dict.get("visibility") != "public" and lib_dict.get("project_type") != "library":
            raise HTTPException(400, "目标项目不是公开项目或公共文档库")

        # 防止重复引用同一个库
        existing = conn.execute(
            "SELECT id FROM project_refs WHERE case_id = ? AND library_id = ?",
            (case_id, data.library_id),
        ).fetchone()
        if existing:
            # 更新已有引用的 file_ids
            conn.execute(
                "UPDATE project_refs SET file_ids = ? WHERE id = ?",
                (json.dumps(data.file_ids), dict(existing)["id"]),
            )
            return {"message": "引用已更新", "ref_id": dict(existing)["id"]}

        ref_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None).isoformat()
        conn.execute(
            """INSERT INTO project_refs (id, case_id, library_id, file_ids, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (ref_id, case_id, data.library_id, json.dumps(data.file_ids), now),
        )
    return {"message": "引用添加成功", "ref_id": ref_id}


class BatchRef(BaseModel):
    library_id: str
    file_ids: list[str] = []

class BatchRefCreate(BaseModel):
    refs: list[BatchRef]

@router.post("/{case_id}/refs/batch")
async def add_ref_batch(case_id: str, data: BatchRefCreate, user: dict = Depends(get_current_user)):
    """批量为案件添加其他公开项目/文档库引用（支持跨库）。"""
    require_project_access(case_id, user, write=True)

    with get_db() as conn:
        for ref in data.refs:
            if ref.library_id == case_id:
                continue

            lib = conn.execute(
                "SELECT project_type, visibility FROM projects WHERE id = ?", (ref.library_id,)
            ).fetchone()
            if not lib:
                continue
            
            lib_dict = dict(lib)
            if lib_dict.get("visibility") != "public" and lib_dict.get("project_type") != "library":
                continue

            existing = conn.execute(
                "SELECT id, file_ids FROM project_refs WHERE case_id = ? AND library_id = ?",
                (case_id, ref.library_id),
            ).fetchone()

            if existing:
                existing_dict = dict(existing)
                old_ids = json.loads(existing_dict.get("file_ids", "[]"))
                new_ids = list(set(old_ids + ref.file_ids))
                conn.execute(
                    "UPDATE project_refs SET file_ids = ? WHERE id = ?",
                    (json.dumps(new_ids), existing_dict["id"]),
                )
            else:
                ref_id = uuid.uuid4().hex[:12]
                now = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None).isoformat()
                conn.execute(
                    """INSERT INTO project_refs (id, case_id, library_id, file_ids, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (ref_id, case_id, ref.library_id, json.dumps(ref.file_ids), now),
                )
    return {"message": "批量引用成功"}


@router.get("/{case_id}/recommend-refs")
async def recommend_refs(case_id: str, user: dict = Depends(get_current_user)):
    """根据已上传案件的文档内容，智能推荐公共文档库中的法律法规（最多10部）。"""
    require_project_access(case_id, user, write=False)

    project_name = "未命名项目"
    from core.project_access import _read_projects
    for p in _read_projects():
        if p["id"] == case_id:
            project_name = p.get("name", "未命名项目")
            break

    from qdrant_client import models
    from core.vector_store import _get_client, _collection_name, _DENSE_VECTOR_NAME, _SPARSE_VECTOR_NAME, _compute_sparse_vectors, _get_dense_model
    client = _get_client()

    case_text = ""
    try:
        results, _ = client.scroll(
            collection_name=_collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="project_id",
                        match=models.MatchValue(value=case_id)
                    )
                ],
                must_not=[
                    models.FieldCondition(
                        key="chunk_type",
                        match=models.MatchValue(value="doc_summary")
                    )
                ]
            ),
            limit=10,
            with_payload=True
        )
        if results:
            case_text = " ".join([p.payload.get("document", "") for p in results if p.payload])
    except Exception as e:
        logger.warning(f"获取案件特征文本失败: {e}")

    search_keyword = project_name
    if case_text or project_name:
        try:
            from core.llm_engine import stream_ollama
            query_text = f"项目名称：{project_name}。案情事实：{case_text[:1000]}"
            prompt = (
                f"请根据以下案件名称和事实，生成 1 个用于在法律法规库中检索相关法条的极其简短的关键词串（例如：'人身损害赔偿 侵权责任' 或 '交通事故 赔偿标准' 或 '保险理赔 告知义务'）。"
                f"严禁输出任何废话，直接输出一串空格分隔的检索词。\n\n"
                f"【案件】\n{query_text}\n\n"
                f"/no_think"
            )
            raw_stream = stream_ollama(
                prompt=prompt,
                model="qwen3.6:35b-q4",
                temperature=0.1,
                num_predict=32
            )
            keyword_parts = []
            async for token in raw_stream:
                keyword_parts.append(token)
            extracted = "".join(keyword_parts).strip()
            if extracted:
                import re
                extracted = re.sub(r'[^\w\s\u4e00-\u9fa5]', '', extracted)
                if len(extracted) > 2:
                    search_keyword = extracted
        except Exception as e:
            logger.warning(f"提炼检索词异常: {e}")

    with get_db() as conn:
        libs = conn.execute(
            "SELECT id, name FROM projects WHERE project_type = 'library'"
        ).fetchall()

    lib_map = {dict(l)["id"]: dict(l)["name"] for l in libs}
    recommended_files = []

    if lib_map:
        try:
            dense_model = _get_dense_model()
            query_dense = dense_model.encode([search_keyword], normalize_embeddings=True)[0].tolist()
            query_sparse = _compute_sparse_vectors([search_keyword])[0]
            
            lib_ids_list = list(lib_map.keys())
            qdrant_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="project_id",
                        match=models.MatchAny(any=lib_ids_list)
                    )
                ],
                must_not=[
                    models.FieldCondition(
                        key="chunk_type",
                        match=models.MatchValue(value="doc_summary")
                    )
                ]
            )
            
            search_res = client.query_points(
                collection_name=_collection_name,
                prefetch=[
                    models.Prefetch(query=query_dense, using=_DENSE_VECTOR_NAME, limit=40, filter=qdrant_filter),
                    models.Prefetch(query=query_sparse, using=_SPARSE_VECTOR_NAME, limit=40, filter=qdrant_filter),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=40,
                with_payload=True
            )
            
            file_scores = {}
            for i, pt in enumerate(search_res.points):
                payload = pt.payload or {}
                fid = payload.get("file_id")
                fname = payload.get("filename")
                lib_id = payload.get("project_id")
                if fid and fname and lib_id in lib_map:
                    score = 1.0 / (60.0 + i)
                    if fid not in file_scores:
                        file_scores[fid] = {
                            "id": fid,
                            "filename": fname,
                            "library_id": lib_id,
                            "library_name": lib_map[lib_id],
                            "score": score
                        }
                    else:
                        file_scores[fid]["score"] += score
                        
            sorted_files = sorted(file_scores.values(), key=lambda x: -x["score"])
            recommended_files = sorted_files[:10]
        except Exception as e:
            logger.warning(f"推荐法规向量检索失败: {e}")

    if not recommended_files and lib_map:
        import os
        for lib_id, lib_name in lib_map.items():
            lib_dir = Path(settings.UPLOAD_DIR) / lib_id
            if lib_dir.exists():
                for root, _, fnames in os.walk(str(lib_dir)):
                    for fname in fnames:
                        if fname.startswith("."): continue
                        fpath = os.path.join(root, fname)
                        rel_path = os.path.relpath(fpath, str(Path(settings.UPLOAD_DIR)))
                        import hashlib
                        file_id = hashlib.md5(f"{lib_id}_{rel_path}".encode("utf-8")).hexdigest()
                        recommended_files.append({
                            "id": file_id,
                            "filename": fname,
                            "library_id": lib_id,
                            "library_name": lib_name,
                            "score": 0
                        })
                        if len(recommended_files) >= 10: break
                    if len(recommended_files) >= 10: break
            if len(recommended_files) >= 10: break

    result = []
    for f in recommended_files:
        result.append({
            "id": f["id"],
            "filename": f["filename"],
            "library_id": f["library_id"],
            "library_name": f["library_name"]
        })
    return {"recommended": result}


@router.get("/{case_id}/refs")
async def list_refs(case_id: str, user: dict = Depends(get_current_user)):
    """获取案件的所有公共文档引用列表。"""
    require_project_access(case_id, user, write=False)
    with get_db() as conn:
        rows = conn.execute(
            """SELECT r.*, p.name AS library_name
               FROM project_refs r
               JOIN projects p ON r.library_id = p.id
               WHERE r.case_id = ?""",
            (case_id,),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["file_ids"] = json.loads(d.get("file_ids", "[]"))
        result.append(d)
    return result


@router.delete("/{case_id}/refs/{ref_id}")
async def remove_ref(case_id: str, ref_id: str, user: dict = Depends(get_current_user)):
    """移除一条公共文档引用（不删除实际文件）。"""
    require_project_access(case_id, user, write=False)
    with get_db() as conn:
        conn.execute(
            "DELETE FROM project_refs WHERE id = ? AND case_id = ?",
            (ref_id, case_id),
        )
    return {"message": "引用已移除"}


class ExcludeRefFilesRequest(BaseModel):
    file_ids: list[str] = []


@router.post("/{case_id}/exclude-ref-files")
async def exclude_ref_files(
    case_id: str,
    req: ExcludeRefFilesRequest,
    user: dict = Depends(get_current_user),
):
    """
    从案件的公共文档引用中排除指定文件。
    WHY: 不删除整条引用记录，只从 file_ids JSON 数组中移除指定 ID。
         如果移除后 file_ids 为空，则删除整条引用记录。
    """
    require_project_access(case_id, user, write=False)
    exclude_set = set(req.file_ids)

    with get_db() as conn:
        refs = conn.execute(
            "SELECT id, file_ids FROM project_refs WHERE case_id = ?",
            (case_id,),
        ).fetchall()

        for ref in refs:
            ref_dict = dict(ref)
            current_ids = json.loads(ref_dict.get("file_ids", "[]"))
            updated_ids = [fid for fid in current_ids if fid not in exclude_set]

            if not updated_ids:
                # 所有文件都被排除，删除整条引用
                conn.execute(
                    "DELETE FROM project_refs WHERE id = ?",
                    (ref_dict["id"],),
                )
            elif len(updated_ids) != len(current_ids):
                # 部分文件被排除，更新 file_ids
                conn.execute(
                    "UPDATE project_refs SET file_ids = ? WHERE id = ?",
                    (json.dumps(updated_ids), ref_dict["id"]),
                )

    return {"message": f"已排除 {len(exclude_set)} 个文件"}


@router.get("/{case_id}/ref-files")
async def list_ref_files(case_id: str, user: dict = Depends(get_current_user)):
    """
    获取所有公共文档库（library）的文件列表。
    WHY: 用户期望默认引用系统中所有的公共文档。
    """
    require_project_access(case_id, user, write=False)

    with get_db() as conn:
        # 获取所有公共文档库项目
        libraries = conn.execute(
            "SELECT id FROM projects WHERE project_type = 'library' AND visibility = 'public'"
        ).fetchall()

    import os, hashlib
    all_files = []
    for lib in libraries:
        lib_id = lib["id"]
        lib_dir = Path(settings.UPLOAD_DIR) / lib_id

        if not lib_dir.exists():
            continue

        for root, dirs, fnames in os.walk(str(lib_dir)):
            # 跳过隐藏目录
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in fnames:
                if fname.startswith("."):
                    continue
                fpath = os.path.join(root, fname)
                # WHY: file_id 必须与 files.py list_files 的生成公式一致
                #      即 md5("{project_id}_{相对于UPLOAD_ROOT的路径}")
                rel_path = os.path.relpath(fpath, str(Path(settings.UPLOAD_DIR)))
                file_id = hashlib.md5(
                    f"{lib_id}_{rel_path}".encode("utf-8")
                ).hexdigest()

                all_files.append({
                    "id": file_id,
                    "filename": fname,
                    "path": rel_path,
                    "size": os.path.getsize(fpath),
                    "library_id": lib_id,
                    "is_public": True,
                })

    return {"files": all_files}


# ----------------- 案件信息 AI 生成 -----------------

class CaseInfoRequest(BaseModel):
    file_ids: list[str] = []


PROJECT_INFO_PROMPT = """你是一名资深企业顾问。请根据以下项目文档内容，提取并总结生成一份标准的项目信息摘要。

请包含以下内容（如果文档中存在相关信息）：
1. **项目名称**：项目全称
2. **项目类型**：技术研发/管理规范/市场推广/工程建设等
3. **发起单位/关联主体**：项目相关的发起单位或主要合作方
4. **主导负责人**：文档中提及的负责人或相关联系人
5. **主要业务范围**：涉及的业务或技术领域
6. **项目时间线/周期**：项目的重要时间节点
7. **核心内容摘要**：文档所述事实概述（200字以内）
8. **关键数据指标**：提及的数量、金额或进度指标
9. **现存主要挑战/痛点**：目前面临的待解决问题或瓶颈
10. **拟采取的解决方案**：文档中提出的应对策略或计划
11. **主要交付物/成果**：预期的成果或已提交的产出
12. **参考规范/标准**：引用的行业政策或企业标准

如果某项信息在文档中未提及，请标注"（文档未提及）"。
请用清晰的结构化格式输出，使用 Markdown 格式。

--- 以下是项目文档内容 ---

{context}
"""


@router.post("/{case_id}/generate-case-info")
async def generate_case_info(
    case_id: str,
    req: CaseInfoRequest,
    user: dict = Depends(get_current_user),
):
    """
    从勾选文档中 AI 总结生成项目信息，SSE 流式输出。
    WHY: 项目信息需要从多份文档中提取关键要素，
         LLM 擅长跨文档归纳和结构化输出。
    """
    from fastapi.responses import StreamingResponse
    from core.vector_store import query_by_file_ids
    from core.llm_engine import stream_ollama
    from core.think_filter import filter_think_stream

    require_project_access(case_id, user, write=False)

    if not req.file_ids:
        raise HTTPException(400, "请至少勾选一个文档")

    logger.info(
        f"[项目信息生成] case={case_id}, file_ids({len(req.file_ids)})={req.file_ids[:5]}"
    )

    # WHY: 不传 project_id，因为勾选的文件可能跨项目（如公共文档）
    results = query_by_file_ids(
        query_text="项目基本信息 业务规范 交付要求 事实 结论",
        file_ids=req.file_ids,
        project_id="",
        n_results=30,
    )
    logger.info(f"[项目信息生成] 检索到 {len(results)} 条结果")
    context_parts = [r.get("content", "") for r in results if r.get("content")]
    context = "\n\n---\n\n".join(context_parts[:20])

    if not context.strip():
        raise HTTPException(
            400, "未能从勾选的文档中检索到有效内容，请确认文档已完成学习"
        )

    prompt = PROJECT_INFO_PROMPT.format(context=context) + "\n/no_think"

    async def event_stream():
        try:
            # WHY: 先发一个心跳，避免前端在 LLM 启动期间超时断连
            yield "data: {\"token\": \"\"}\n\n"
            raw_stream = stream_ollama(
                prompt=prompt,
                model="qwen3.6:35b-q4",
                temperature=0.3,
                num_ctx=16384,
                num_predict=4096,
            )
            async for token in filter_think_stream(raw_stream):
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"项目信息生成失败: {e}")
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

# ----------------- 常法服务扩展：客户档案与台账管理 (Client Profile & Renewal Ledger) -----------------
from typing import List

class ClientProfile(BaseModel):
    clientName: Optional[str] = ""
    industry: Optional[str] = ""
    stance: Optional[str] = ""
    clientType: Optional[str] = ""
    specialPoints: Optional[str] = ""
    searchLevel: Optional[str] = ""

@router.get("/{project_id}/client_profile")
async def get_client_profile(project_id: str, user: dict = Depends(get_current_user)):
    require_project_access(project_id, user, write=False)
    fp = DOCUMENTS_DIR / project_id / "client_profile.json"
    if not fp.exists():
        return {}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {}

@router.post("/{project_id}/client_profile")
async def save_client_profile(project_id: str, profile: ClientProfile, user: dict = Depends(get_current_user)):
    require_project_access(project_id, user, write=True)
    proj_dir = DOCUMENTS_DIR / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    fp = proj_dir / "client_profile.json"
    fp.write_text(json.dumps(profile.dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return profile.dict()

class RenewalLedgerItem(BaseModel):
    id: str
    clientName: str
    contractName: str
    startDate: str
    endDate: str
    annualFee: str
    paymentMethod: str
    contactPerson: str
    remark: Optional[str] = ""

@router.get("/{project_id}/renewal_ledger")
async def get_renewal_ledger(project_id: str, user: dict = Depends(get_current_user)):
    require_project_access(project_id, user, write=False)
    fp = DOCUMENTS_DIR / project_id / "renewal_ledger.json"
    if not fp.exists():
        return []
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return []

@router.post("/{project_id}/renewal_ledger")
async def save_renewal_ledger(project_id: str, items: List[RenewalLedgerItem], user: dict = Depends(get_current_user)):
    require_project_access(project_id, user, write=True)
    proj_dir = DOCUMENTS_DIR / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    fp = proj_dir / "renewal_ledger.json"
    fp.write_text(json.dumps([item.dict() for item in items], ensure_ascii=False, indent=2), encoding="utf-8")
    return [item.dict() for item in items]

class RetrospectiveRequest(BaseModel):
    content: str

@router.post("/{project_id}/retrospective/stream")
async def stream_retrospective(project_id: str, req: RetrospectiveRequest, user: dict = Depends(get_current_user)):
    require_project_access(project_id, user, write=True)
    
    prompt = (
        "你是一位资深的常年法律顾问。请根据以下用户提供的该客户近期合同审查中发现的【主要修改/起草要点摘要】，\n"
        "进行专业的合同审查复盘与高频风险问题梳理，并为客户提供合同模板优化建议。\n\n"
        "## 审查要点摘要\n"
        f"{req.content}\n\n"
        "## 任务要求\n"
        "请直接输出一份结构完整的《合同审查复盘及模板优化建议报告》，包含以下内容：\n"
        "1. 整体概述（本次复盘分析的基础、分析目的等）；\n"
        "2. 高频重复问题分类与风险度分层（例如管辖争议、违约责任、付款方式等，请列出发生概率与核心影响点）；\n"
        "3. 合同模板优化建议（请给出具体的可修改标准条款文字供客户更新）；\n"
        "4. 报告落款（写常法顾问律师团队）。\n\n"
        "请使用非常专业、干练的法律中文术语，且使用标准 Markdown 格式排版。"
    )

    async def event_stream():
        try:
            yield "data: {\"token\": \"\"}\n\n"
            raw_stream = stream_ollama(
                prompt=prompt,
                model="qwen3.6:35b-q4",
                temperature=0.3,
                num_ctx=16384,
                num_predict=4096,
            )
            async for token in filter_think_stream(raw_stream):
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"合同复盘生成失败: {e}")
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{case_id}/project-ref-files")
async def list_project_ref_files(case_id: str, user: dict = Depends(get_current_user)):
    """
    获取当前案件手动引用的其他公开项目文件列表（排除 library 文档库）。
    """
    require_project_access(case_id, user, write=False)

    with get_db() as conn:
        refs = conn.execute(
            "SELECT library_id, file_ids FROM project_refs WHERE case_id = ?",
            (case_id,)
        ).fetchall()

    project_files = []
    import os, hashlib
    with get_db() as conn:
        for ref in refs:
            lib_id = ref["library_id"]
            # 确认 library_id 项目不是 library 且是公开的
            lib_info = conn.execute(
                "SELECT name, project_type, visibility FROM projects WHERE id = ?",
                (lib_id,)
            ).fetchone()
            if not lib_info:
                continue
            lib_dict = dict(lib_info)
            if lib_dict.get("project_type") == "library" or lib_dict.get("visibility") != "public":
                continue

            file_ids_limit = json.loads(ref["file_ids"] or "[]")
            if not file_ids_limit:
                continue

            lib_dir = Path(settings.UPLOAD_DIR) / lib_id
            if not lib_dir.exists():
                continue

            for root, dirs, fnames in os.walk(str(lib_dir)):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for fname in fnames:
                    if fname.startswith("."):
                        continue
                    fpath = os.path.join(root, fname)
                    rel_path = os.path.relpath(fpath, str(Path(settings.UPLOAD_DIR)))
                    file_id = hashlib.md5(
                        f"{lib_id}_{rel_path}".encode("utf-8")
                    ).hexdigest()

                    if file_id in file_ids_limit:
                        project_files.append({
                            "id": file_id,
                            "filename": fname,
                            "path": rel_path,
                            "size": os.path.getsize(fpath),
                            "library_id": lib_id,
                            "library_name": lib_dict["name"],
                            "is_project_ref": True
                        })
    return {"files": project_files}



