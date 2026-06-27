"""
Ollama Qwen3.6 推理引擎封装。
WHY: 将 Ollama REST API 的流式调用封装为干净的 async generator，
     供上层 API 路由组合 RAG 上下文后直接消费。
"""
from __future__ import annotations

import json
import logging
import asyncio
import os
import re
from typing import AsyncGenerator, Optional
import contextvars

import httpx
from core.config import settings

logger = logging.getLogger(__name__)

# WHY: qwen3.6 偶尔在生成尾部泄露 ChatML 控制 token，
#      在最底层用正则一次性清除，确保所有上层调用都安全。
_CTRL_TOKEN_RE = re.compile(
    r'<\|(?:endoftext|im_start|im_end|end)\|>'   # ChatML 特殊 token
    r'|(?:^|\n)(?:user|assistant|system)\s*$',     # 裸 role 标记（行尾残留）
    re.MULTILINE
)

# WHY: uvicorn 默认只路由自己的 access 日志到 stdout/stderr，
#      Python logging module 的自定义 logger 不会被 PM2 捕获。
#      手动配置 stream handler 确保预热/心跳日志可被运维监控。
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s: %(name)s - %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)

# 全局共享的 HTTP 客户端缓存，按事件循环隔离，提高高并发下的连接复用率且避免并发冲突
_loop_clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}

def get_client() -> httpx.AsyncClient:
    global _loop_clients
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        # 非异步上下文，返回一个临时 client
        return httpx.AsyncClient(
            timeout=httpx.Timeout(180.0),
            proxy=None,
            trust_env=False
        )

    # 自动清理已经关闭的事件循环对应的 client，防止连接与内存泄露
    for l in list(_loop_clients.keys()):
        if l.is_closed():
            _loop_clients.pop(l, None)

    if current_loop not in _loop_clients or _loop_clients[current_loop].is_closed:
        _loop_clients[current_loop] = httpx.AsyncClient(
            timeout=httpx.Timeout(180.0),
            proxy=None,
            trust_env=False,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
        )
    return _loop_clients[current_loop]


# ──────────────────────────────────────────────────────────
# GPU 推理优先级调度器
# WHY: Ollama 设置 NUM_PARALLEL=2 后能同时处理 2 个推理请求，
#      但超出 2 个时按 FIFO 排队，不区分请求紧急程度。
#      此调度器在应用层引入优先级堆，确保聊天/简单问题
#      总是优先于段落批量生成获得 GPU 推理槽位。
# ──────────────────────────────────────────────────────────
import heapq
from contextlib import asynccontextmanager

# 优先级常量（数值越小越优先）
PRIORITY_HIGH = 0   # 聊天、简单问答、角色推荐
PRIORITY_LOW  = 1   # 段落批量生成

class LLMPriorityScheduler:
    """
    基于最小堆的 GPU 推理优先级调度器。
    max_slots 应与 OLLAMA_NUM_PARALLEL 一致。
    """

    def __init__(self, max_slots: int = 2):
        self._max_slots = max_slots
        self._active = 0               # 当前占用的槽位数
        self._lock = asyncio.Lock()     # 保护内部状态的互斥锁
        self._waiters: list = []        # 最小堆: (priority, counter, event)
        self._counter = 0               # 单调递增计数器，防止同优先级饥饿

    @asynccontextmanager
    async def acquire(self, priority: int = PRIORITY_LOW):
        # 尝试获取槽位
        event: asyncio.Event | None = None
        async with self._lock:
            if self._active < self._max_slots:
                self._active += 1
            else:
                # 槽位满，加入等待堆
                event = asyncio.Event()
                self._counter += 1
                heapq.heappush(self._waiters, (priority, self._counter, event))

        if event is not None:
            # 等待被唤醒（由 release 触发）
            try:
                await event.wait()
            except asyncio.CancelledError:
                # WHY: 客户端在等待队列中断开连接，引发取消异常！
                async with self._lock:
                    if event.is_set():
                        # 已经被唤醒，槽位已交接给我！但我被取消了，需把槽位传递给下一个人或释放
                        if self._waiters:
                            _, _, next_event = heapq.heappop(self._waiters)
                            next_event.set()
                        else:
                            self._active -= 1
                    else:
                        # 还未被唤醒，直接将自己从等待堆中移除，防止将来把槽位传给死掉的我
                        self._waiters = [w for w in self._waiters if w[2] is not event]
                        heapq.heapify(self._waiters)
                raise

        try:
            yield
        finally:
            # 释放槽位，唤醒堆中最高优先级的等待者
            async with self._lock:
                if self._waiters:
                    _, _, next_event = heapq.heappop(self._waiters)
                    next_event.set()    # 唤醒下一个（不减 _active，槽位直接交接）
                else:
                    self._active -= 1

    @property
    def stats(self) -> dict:
        """返回调度器当前状态（用于 /llm/status 接口）。"""
        return {
            "active_slots": self._active,
            "max_slots": self._max_slots,
            "queued": len(self._waiters),
        }


# 模块级单例 — 全局唯一调度器
# WHY: max_slots 与 OLLAMA_NUM_PARALLEL / GPU_MAX_SLOTS 保持一致
llm_scheduler = LLMPriorityScheduler(max_slots=int(os.environ.get("GPU_MAX_SLOTS", "4")))

# Prompt 模板：将 RAG 检索到的上下文和用户指令组装成结构化提示词
PARAGRAPH_PROMPT = """你是一位高级技术文档撰写专家。
你正在为「{project_name}」撰写专业文档。
请根据以下参考资料，为标题「{title}」撰写一段专业、详实的正文内容。

## 参考资料
{context}

## 要求
1. 语言正式、书面化，文档风格应与参考资料保持一致
2. 必须基于所提供的参考资料，不得臆造数据
3. 所有内容必须严格围绕「{project_name}」展开，严禁引用其他无关项目的数据
4. 段落结构清晰，可适当使用 Markdown 格式（如**加粗**、编号列表等）
5. 字数要求：内容应丰富详实，一般不少于 300 字。
6. 直接输出正文内容，无需重复当前标题。
7. **严禁越界生成**：你的任务仅限于撰写当前指定标题的内容。如果当前标题是大章节标题（如“一、课程概述”），仅需写一段简短的引导性概述，概括本章将涵盖哪些方面（此情况不受 300 字下限约束），绝不能展开子节的详细内容。如果当前标题是子节标题（如“（一）课程信息”），则聚焦该子节的具体主题，绝不能重复大章节概述中已说过的话。
8. **严禁内容重复**：每个章节的内容必须具有独立性和针对性。不同章节之间严禁出现大段重复或高度相似的表述。如果前文已经提到某内容，请勿再次重述，改为补充新的细节或从不同角度展开。
9. **数据可视化规范**：仅当参考资料存在【真实的统计对比数字】时，才允许生成数据表格及对应可视化标记。严禁为纯文字特征描述生搬硬套生成图表，绝不允许重复输出与之前相同的内容。
10. **法规引用规范**：提及法律法规时，名称与文号保持与参考资料一致，请勿随意省略或编造更新文号。
11. **严禁提及来源文件名**：参考资料中的"[来源: xxx]"标注仅供你内部定位信息用，严禁在正文中出现任何文件名、文档名称或"来源"字样。
12. **严禁照抄文档结构标题**：参考资料中可能含有"单元1"、"单元2"、"第X章"、"第X节"等源文档组织标题，这些是资料的内部结构，**严禁将其原样写入正文**。请将资料中的知识提炼为流畅的叙述段落，而非复制文档目录结构。
"""

CHAT_PROMPT = """你是一位专业的知识库问答助手。
请根据以下参考资料回答用户的问题。如果参考资料中没有相关信息，请明确告知。

## 参考资料
{context}

## 用户问题
{question}
"""

# WHY: 双路 Prompt 引擎 — 同时注入「项目事实」和「范文风格样本」，
#      使生成内容在数据准确的同时，语气、结构、措辞向公司精品文档靠拢。
DUAL_TRACK_PROMPT = """你是一位高级技术文档撰写专家。
你正在为「{project_name}」撰写专业文档。
请根据以下【项目参考资料】和【写作风格范文】，为标题「{title}」撰写一段专业、详实的正文内容。

## 项目参考资料（事实来源，Track A）
{project_facts}

## 写作风格范文（语言风格参考，Track B）
{exemplar_content}

## 写作指令
1. **事实约束**：所有数据、数字、地名、规模参数必须来自【项目参考资料】，严禁捏造。优先查找【项目核心指标（全局）】中的数值
2. **地域约束**：你正在写「{project_name}」，范文仅供风格参考，范文中的地名、数据、项目名称必须替换为【项目参考资料】中对应的内容
3. **结构对齐**：严格对齐范文的段落数量和内容结构。范文有几段正文，你就写几段；范文没有表格，你就不加表格。字数篇幅应与范文基本相当，不得擅自注水扩写或大幅缩写
4. **风格模仿**：模仿【写作风格范文】的语言风格、专业深度和论证逻辑
5. **表格处理**：仅当范文中已包含表格时，才在对应位置生成表格并用项目数据填充。否则不得擅自添加
6. **图件占位**：仅当 Prompt 末尾附有【图件指令】时，才在正文末尾输出一个 [插入图件：...] 占位标记。没有图件指令时，严禁生成任何 [插入图件] 标记
7. 直接输出正文内容，无需重复当前标题。
8. **严禁越界生成**：你的任务仅限于撰写当前指定的标题的内容。即使你参考的范文中包含了后续章节的内容，也**绝不要**自动延伸生成下一节的内容。
9. **可视化规范**：严禁过度炫技。仅当范文中有真实的数值统计报表时，才保留表格。绝不可为文字特征描述凭空创造图表。
10. **格式规范**：你可以使用 Markdown 加粗格式增强可读性。但对于编号列表：如果范文中有列表，你可以保留并用项目资料替换；如果范文中没有，你也不得使用列表格式，无论资料多长。严禁生成流程图或 mermaid 代码块。
12. **严禁提及来源文件名**：参考资料中的"[来源: xxx]"标注仅供你内部定位信息用，严禁在正文中出现任何文件名、文档名称或"来源"字样。
13. **严禁照抄文档结构标题**：参考资料中可能含有"单元1"、"单元2"、"第X章"、"第X节"等源文档组织标题，这些是资料的内部结构，**严禁将其原样写入正文**。请将资料中的知识提炼为流畅的叙述段落。
"""

# WHY: 【Slot-Filling Phase 1】范文智能替换模式 — Few-shot Contrast 框架。
#      核心设计理念：将任务定义为"内容迁移"而非"从头编写"。
#      明确区分"结构标杆"（范文底稿，不可改变论述逻辑）和"事实来源"（项目数据，必须使用）。
#      这种对比框架能有效防止模型被参考资料中的无关数据干扰，始终锚定范文结构。
REPLACE_PROMPT = """你是一位专业的技术报告迁移专家。
你的任务是将一份【已有范文】的内容精确迁移到新项目「{project_name}」。

## 任务定义
范文来自一个类似项目，它的论述逻辑、段落结构和文体风格是你的标杆。
你要做的是：保持范文的论述框架不变，仅将其中的事实数据替换为新项目「{project_name}」的数据。
简单说：你是在"换皮"，不是在"重写"。

## 🔒 范文底稿（结构标杆 — 论述逻辑和段落数不可改变）
{exemplar_content}

## 📊 新项目「{project_name}」的参考资料（事实来源 — 必须使用以下数据替换范文中的对应项）
{project_facts}

## 迁移规则（按优先级排序）
1. **段落结构 1:1 映射**：范文有几段，输出就几段。范文的论述顺序（先政策背景→再省级部署→最后本地定位）必须原封不动保持。注：此约束针对文本段落和论述结构；若范文引用了表格名称（如"表X-X..."），在引用位置后附加对应的数据表格不算新增段落；若表格存在因 OCR 解析产生的重复列，应按规则7的指引处理
2. **替换目标**：地名、行政区划、项目名称、统计数据（面积/人口/金额/年份/百分比/坡度等）
3. **不替换的内容**：政策术语（如"藏粮于地""乡村振兴"）、法律法规名称和文号、技术标准编号
4. **数据优先级**：优先使用参考资料中的数值 → 若资料中确实缺失，可调用你的专业知识对通用性词汇进行合理补充 → **⚠️ 凡是范文中属于旧项目的特定数据（包括但不限于：村名、乡镇名、面积数值、人口数量、金额、工程编号、坐标、比例数据、建设规模等），必须按以下两步判定**：（1）在参考资料中**逐项查找**是否有对应的具体数据（数值、名称），若有则用参考资料中的数据替换范文；（2）若参考资料中**没有该项的具体数值或名称**——注意：图谱摘要中的概念性描述（如"关联了耕地面积""包含水田数据"）**不算具体数据**——则必须用「[待补充]」替换，严禁保留范文中旧项目的原始数据
4a. **⚠️ 完整表格数据提取（最高优先级）**：当参考资料中包含标记为「📊 精确匹配的完整表格」的 Markdown 表格时，该表格包含新项目的**逐行精确数据**（如各村的面积、各工程的编号/金额等）。你必须：（a）逐行扫描该表格，将每一行的数据对应到范文中的相应位置；（b）范文中引用表格的叙述段落（如"XX村耕地面积XX亩"），必须从该表格的对应行中提取具体数值填入；（c）范文中引用表格名称（如"表2-1项目区耕地现状统计表"）时，必须在叙述后输出完整的 Markdown 表格，表格数据**必须从参考资料的完整表格中逐行复制**，严禁填写[待补充]；（d）只有当完整表格中确实找不到对应行时，才可填写[待补充]
{knowledge_rule}
6. **严禁行为**：不得增删段落、不得改变论述逻辑、不得捏造核心项目数据
6a. **⚠️ 输出长度约束**：你的输出总字数必须与范文底稿大致相当（允许 ±20% 浮动）。范文只有一段话，你就只输出一段话。**严禁因参考资料数据丰富而自行增加段落或扩充内容**——参考资料的作用仅是提供数据替换来源，不是扩写依据
{table_constraint}
8. **公式处理**：范文中包含数学公式或计算表达式时，必须使用 LaTeX 语法编写，格式为 `$行内公式$` 或 `$$独立公式$$`。保持与范文相同的公式结构，仅替换其中的数值参数
9. **图件占位**：仅当 Prompt 末尾附有【图件指令】时，才在正文末尾输出 [插入图件：...] 占位标记
10. 直接输出迁移后的正文，无需重复标题，无需解释迁移过程
11. **严禁越界生成**：你的任务仅限于迁移当前指定章节的内容。即使范文中提到了后续章节的主题，也绝不要延伸生成下一节的内容
12. **严禁输出内部参考标记**：以下标记仅供你内部理解数据关系，绝不能出现在输出正文中：【补充关联信息】、【背景摘要】、【项目核心指标】、[来源: xxx]、任何带括号的关系描述（如"实体A（关系）实体B"格式）。输出中只允许出现自然语言正文
"""

# WHY: Phase 2 升级版——LLM 收到的不再是"一堆 RAG 长段落 + 请自己找数据"，
#      而是精确到每个变量的 old→new 对照表。任务从"阅读理解+写作"降维为"查表+填充"。
REPLACE_PROMPT_V2 = """你是一位专业的技术报告迁移专家。
你的任务是将一份【已有范文】的内容精确迁移到新项目「{project_name}」。

## 🔒 范文底稿（结构标杆 — 论述逻辑和段落数不可改变）
{exemplar_content}

## 🔄 替换映射表（已为你预配对好，直接按表逐项替换）
{slot_table}

## 📊 补充参考资料（映射表中标记[待补充]的变量，优先从这里查找）
{project_facts}

## 迁移规则（按优先级排序）
1. **严格按映射表替换**：表中每一条 old→new 都必须被执行，不遗漏不多替
2. **段落结构 1:1 保持**：范文有几段，输出就几段。论述顺序原封不动
3. **[待补充]处理**：映射表中标注"[待补充]"的项，先从补充参考资料中查找；仍找不到则保留[待补充]标记。**严禁用范文中旧项目的数据填充[待补充]**。此外，即使映射表中未列出的旧项目特定数字（如正文段落中的面积、金额、村名等），若在资料中找不到新项目对应值，也必须替换为[待补充]。例外：若新项目资料中的某项数据恰好与范文相同，则保留该数字
{knowledge_rule}
5. **严禁行为**：不得增删段落、不得改变论述逻辑、不得捏造核心项目数据
5a. **⚠️ 输出长度约束**：你的输出总字数必须与范文底稿大致相当（允许 ±20% 浮动）。范文只有一段话，你就只输出一段话。**严禁因参考资料数据丰富而自行增加段落或扩充内容**
{table_constraint}
7. **公式处理**：范文中包含数学公式或计算表达式时，必须使用 LaTeX 语法编写，格式为 `$行内公式$` 或 `$$独立公式$$`。保持与范文相同的公式结构，仅替换其中的数值参数
8. 直接输出迁移后的正文，无需重复标题，无需解释迁移过程
9. **严禁越界生成**：你的任务仅限于迁移当前指定章节的内容。即使范文中提到了后续章节的主题，也绝不要延伸生成下一节的内容
10. **严禁输出内部参考标记**：以下标记仅供你内部理解数据关系，绝不能出现在输出正文中：【补充关联信息】、【背景摘要】、【项目核心指标】、[来源: xxx]。输出中只允许出现自然语言正文
"""

# WHY: 范文精确复刻模式 — AI 自由度降到最低，逐句复制范文原文，
#      仅对地名和数字做精确查找替换，适用于各县报告格式完全统一的批量场景。
CLONE_PROMPT = """你是一台精密的文字替换引擎，不是写作助手。
你的唯一任务是：将下方【范文原文】中涉及特定地区的内容，精确替换为「{project_name}」的对应信息。

## 范文原文（必须 1:1 复刻的底稿）
{exemplar_content}

## 参考资料（{project_name}）
{project_facts}

## 铁律（违反任何一条即为失败）
1. 输出的段落数量、句子数量、标点符号位置必须与范文原文完全一致（注：根据规则 7 追加的图件占位符不计入比对）
2. 仅替换：地名、行政区划名、项目名称、统计数据（面积/人口/金额/年份/百分比）
3. 严禁增删任何句子、段落、表格行。范文有 N 句话，输出必须恰好 N 句
4. 范文中的专业术语、法规名称、技术标准编号保持不变
5. 如参考资料中无对应数据，用「[待补充]」占位，绝不捏造
6. 不输出标题，不输出解释，不输出任何你自己的话
7. **图件占位**：仅当 Prompt 末尾附有【图件指令】时，才在正文末尾输出一个 [插入图件：...] 占位标记。没有图件指令时，严禁生成任何 [插入图件] 标记
8. **公式处理**：范文中包含数学公式或计算表达式时，必须使用 LaTeX 语法编写，格式为 `$行内公式$` 或 `$$独立公式$$`。1:1 复刻公式结构，仅替换数值参数
9. **严禁输出内部参考标记**：以下标记仅供你内部理解数据关系，绝不能出现在输出正文中：【补充关联信息】、【背景摘要】、【项目核心指标】、[来源: xxx]。输出中只允许出现自然语言正文
"""

# WHY: 精确复刻模式的 Phase 2 版本。
#      利用预先抽取的 slot_table 进行查表替换，降低漏改和幻觉，
#      同时保持克隆模式 1:1 句子结构的铁律。
CLONE_PROMPT_V2 = """你是一台精密的文字替换引擎，不是写作助手。
你的唯一任务是：将下方【范文原文】中涉及特定地区的内容，按【替换映射表】精确替换为「{project_name}」的对应信息。

## 范文原文（必须 1:1 复刻的底稿）
{exemplar_content}

## 🔄 替换映射表（已为你预配对好，直接按表逐项替换）
{slot_table}

## 补充参考资料（用于查找映射表中标记[待补充]的变量）
{project_facts}

## 铁律（违反任何一条即为失败）
1. **严格按映射表替换**：表中每一条 old→new 都必须被执行，不遗漏不多替。若映射表中标注"[待补充]"，先从补充参考资料中查找；找不到则保留[待补充]标记
2. **绝对 1:1 结构**：输出的段落数量、句子数量、标点符号位置必须与范文原文完全一致
3. 严禁增删任何句子、段落、表格行。范文有 N 句话，输出必须恰好 N 句
4. 范文中的专业术语、法规名称、技术标准编号保持不变
5. 不输出标题，不输出解释，不输出任何你自己的话
6. **图件占位**：仅当 Prompt 末尾附有【图件指令】时，才在正文末尾输出一个 [插入图件：...] 占位标记。没有图件指令时，严禁生成任何 [插入图件] 标记
7. **公式处理**：范文中包含数学公式或计算表达式时，必须使用 LaTeX 语法编写，格式为 `$行内公式$` 或 `$$独立公式$$`。1:1 复刻公式结构，仅替换数值参数
8. **严禁输出内部参考标记**：以下标记仅供你内部理解数据关系，绝不能出现在输出正文中：【补充关联信息】、【背景摘要】、【项目核心指标】、[来源: xxx]。输出中只允许出现自然语言正文
"""


# ──────────────────────────────────────────────────────────
# 跨进程 GPU 推理限流（Redis 分布式信号量）
# WHY: asyncio.Semaphore(1) 只在单个 FastAPI 进程内有效，
#      Celery Worker（celery-slow, celery-fast）完全绕开此限制，
#      多进程同时调用 Ollama 导致 GPU OOM 或 503。
#      改用 Redis 原子计数器实现跨进程信号量，所有进程共享。
#      借鉴 RAGFlow 的 LoopLocalSemaphore + MAX_CONCURRENT_CHATS 方案。
# ──────────────────────────────────────────────────────────
import asyncio as _asyncio
import os as _os
import time as _time
import uuid as _uuid

# WHY: 与 Ollama 的 OLLAMA_NUM_PARALLEL 保持一致。
#      Mac Studio M4 Max 64GB 内存可支撑 4 个并发推理槽位。
_GPU_MAX_SLOTS = int(_os.environ.get("GPU_MAX_SLOTS", "4"))
_GPU_SLOT_KEY = "gpu:active_slots"
_GPU_SLOT_TTL = 300  # 5 分钟 TTL 防死锁（进程崩溃不会永久占用）


current_project_id = contextvars.ContextVar("current_project_id", default=None)

def get_project_priority(project_id: str | None = None) -> int:
    """获取项目的优先级（1、2、3），默认为 2。"""
    if project_id is None:
        try:
            project_id = current_project_id.get()
        except Exception:
            pass
    if not project_id:
        return 2
    try:
        from core.database import get_db
        with get_db() as conn:
            row = conn.execute("SELECT priority FROM projects WHERE id = ?", (project_id,)).fetchone()
            if row:
                return int(row[0])
    except Exception as e:
        logger.warning(f"获取项目 {project_id} 优先级失败: {e}")
    return 2


_active_slot_id = contextvars.ContextVar("active_slot_id", default=None)
_gpu_tokens_stack = contextvars.ContextVar("gpu_tokens_stack", default=None)
# 进程内信号量：当 Redis 不可用时作为本地限流的二次兜底屏障，防止并发冲垮 Ollama
_local_gpu_semaphore = _asyncio.Semaphore(_GPU_MAX_SLOTS)


class RedisGPUSemaphore:
    """
    基于 Redis 原子操作并具备优先级的跨进程 GPU 信号量。
    WHY: INCR/DECR 是原子操作，多进程安全。
         通过 Redis 计数器 gpu:waiting:priority:1 记录高优先级排队情况。
         当高优先级在排队时，低优先级（2、3级）会主动退避让出槽位。
    """
    def __init__(self, max_slots: int = _GPU_MAX_SLOTS, priority: int | None = None):
        self._max_slots = max_slots
        self._priority = priority if priority is not None else get_project_priority()

    async def __aenter__(self):
        # 1. 检查可重入性：若当前协程已持有槽位，直接放行
        current_stack = _gpu_tokens_stack.get()
        if current_stack and len(current_stack) > 0:
            info = {
                "token": None,
                "use_local": False,
                "slot_id": None,
                "is_reentrant": True
            }
            _gpu_tokens_stack.set(current_stack + [info])
            return self

        from core.redis_client import get_redis
        r = get_redis()
        
        # 2. Redis 不可用时，降级使用进程内本地信号量排队限制
        if not r:
            await _local_gpu_semaphore.acquire()
            token = _active_slot_id.set(None)
            info = {
                "token": token,
                "use_local": True,
                "slot_id": None
            }
            current_stack = _gpu_tokens_stack.get()
            if current_stack is None:
                _gpu_tokens_stack.set([info])
            else:
                _gpu_tokens_stack.set(current_stack + [info])
            return self

        pushed = False
        entered_ok = False
        info = {}
        try:
            slot_id = _uuid.uuid4().hex[:8]
            token = _active_slot_id.set(slot_id)
            
            # 将本次调用的元信息压入当前协程的栈中
            info = {
                "token": token,
                "use_local": False,
                "slot_id": slot_id
            }
            current_stack = _gpu_tokens_stack.get()
            if current_stack is None:
                _gpu_tokens_stack.set([info])
            else:
                _gpu_tokens_stack.set(current_stack + [info])
            pushed = True

            slot_key = f"gpu:slot:{slot_id}"
            
            # 记录高优先级等待数
            high_priority_waiting_key = "gpu:waiting:priority:1"

            if self._priority == 1:
                try:
                    r.incr(high_priority_waiting_key)
                    # 设 1 分钟 TTL 防排队数永久泄漏
                    r.expire(high_priority_waiting_key, 60)
                except Exception:
                    pass

            _backoff = 0.5
            while True:
                # 1. 普通优先级（2、3级）主动让步于正在等待的高优先级（1级）任务
                if self._priority > 1:
                    try:
                        waiting_count = r.get(high_priority_waiting_key)
                        if waiting_count and int(waiting_count) > 0:
                            # 挂起并等待，指数退避
                            await _asyncio.sleep(_backoff)
                            _backoff = min(_backoff * 2, 10)
                            continue
                    except Exception:
                        pass

                # 2. 尝试抢占槽位
                try:
                    # WHY: 统计所有处于有效生命周期内的 slot_key，防止由于进程被强杀导致的全局 active_slots 计数器永久泄漏。
                    #      最坏情况下锁只会被占用 _GPU_SLOT_TTL (5分钟) 时间，且会自动过期释放。
                    active_slots = r.keys("gpu:slot:*")
                    if len(active_slots) < self._max_slots:
                        # 成功抢占槽位，写入带 TTL 的 slot 键
                        r.setex(slot_key, _GPU_SLOT_TTL, "1")
                        if self._priority == 1:
                            val = r.decr(high_priority_waiting_key)
                            if val < 0:
                                r.set(high_priority_waiting_key, 0)
                        entered_ok = True
                        return self
                except Exception:
                    # 异常降级为本地信号量保护
                    if self._priority == 1:
                        try:
                            val = r.decr(high_priority_waiting_key)
                            if val < 0:
                                r.set(high_priority_waiting_key, 0)
                        except Exception:
                            pass
                    
                    await _local_gpu_semaphore.acquire()
                    info["use_local"] = True
                    entered_ok = True
                    return self

                await _asyncio.sleep(_backoff)
                _backoff = min(_backoff * 2, 10)
        except BaseException:
            # 异常/取消时清理排队计数并退栈还原，防止永久挂死
            if pushed and not entered_ok:
                stack = _gpu_tokens_stack.get()
                if stack:
                    new_stack = list(stack)
                    popped_info = new_stack.pop()
                    _active_slot_id.reset(popped_info["token"])
                    _gpu_tokens_stack.set(new_stack)
                    if popped_info.get("use_local"):
                        _local_gpu_semaphore.release()
            if self._priority == 1:
                try:
                    val = r.decr(high_priority_waiting_key)
                    if val < 0:
                        r.set(high_priority_waiting_key, 0)
                except Exception:
                    pass
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        stack = _gpu_tokens_stack.get()
        if not stack:
            return
            
        new_stack = list(stack)
        info = new_stack.pop()
        _gpu_tokens_stack.set(new_stack)
        
        # 若是重入锁，直接返回，不释放任何实际锁资源
        if info.get("is_reentrant"):
            return

        slot_id = info.get("slot_id")
        use_local = info.get("use_local", False)
        
        # 还原最外层 token
        if info.get("token"):
            try:
                _active_slot_id.reset(info["token"])
            except Exception:
                pass

        # 1. 释放本地信号量
        if use_local:
            _local_gpu_semaphore.release()

        # 2. 释放 Redis 槽位
        from core.redis_client import get_redis
        r = get_redis()
        if not r or not slot_id:
            return

        slot_key = f"gpu:slot:{slot_id}"
        try:
            r.delete(slot_key)
        except Exception:
            pass


# 模块级单例（向后兼容）
_gpu_semaphore = RedisGPUSemaphore(max_slots=_GPU_MAX_SLOTS)


async def stream_ollama(
    prompt: str,
    model: str = settings.DEFAULT_LLM_MODEL,
    temperature: float = 0.7,
    num_ctx: int = 32768,
    num_predict: int = 24576,
    images: Optional[list] = None,
) -> AsyncGenerator[str, None]:
    """
    通过 Ollama REST API 流式调用本地大模型。
    逐 chunk yield 原始文本（含可能的 <think> 标签）。
    WHY: 使用优先级 GPU 信号量保证跨进程 GPU 限流及优先级抢占。
         所有进程共享锁资源。
    """
    async with RedisGPUSemaphore(max_slots=_GPU_MAX_SLOTS):
        async for token in _stream_ollama_inner(prompt, model, temperature, num_ctx, num_predict, images):
            yield token


async def _stream_ollama_inner(
    prompt: str,
    model: str = settings.DEFAULT_LLM_MODEL,
    temperature: float = 0.7,
    num_ctx: int = 32768,
    num_predict: int = 24576,
    images: Optional[list] = None,
) -> AsyncGenerator[str, None]:
    """Ollama 流式调用的内部实现（被信号量包裹）。"""
    url = f"{settings.OLLAMA_BASE_URL}/api/generate"
    # 检测 /no_think 标志（由 generate.py 追加）
    do_raw_bypass = False
    if "/no_think" in prompt:
        prompt = prompt.replace("/no_think", "").strip()
        do_raw_bypass = True

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        # WHY: 较新版本的 Ollama 支持原生 think 参数控制推演。
        "think": False,
        "keep_alive": -1,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
            "num_ctx": num_ctx,
            "repeat_penalty": 1.0,
            "top_p": 0.9,
        }
    }

    if images:
        cleaned_images = []
        for img in images:
            if isinstance(img, str) and img.startswith("data:image"):
                if "," in img:
                    _, base64_data = img.split(",", 1)
                    cleaned_images.append(base64_data)
                else:
                    cleaned_images.append(img)
            else:
                cleaned_images.append(img)
        payload["images"] = cleaned_images

    # WHY: 在旧版 Ollama (如 0.21.0) 中，think: False 无效。
    #      针对 ChatML 格式的推演模型 (qwen3.6 系列)，
    #      我们可以通过 raw 模式强行在前缀注入 </think>\n 来打断模型思考，实现秒回文本！
    if do_raw_bypass and "qwen" in model.lower():
        raw_prompt = (
            f"<|im_start|>user\n{prompt}<|im_end|>\n"
            f"<|im_start|>assistant\n<think>\n</think>\n"
        )
        payload["prompt"] = raw_prompt
        payload["raw"] = True

    # WHY: Ollama 在 GPU 繁忙时偶发 503，加重试避免 0 字空白。
    import asyncio as _aio
    _max_retries = 3
    for _attempt in range(_max_retries):
        try:
            import time as _time
            client = get_client()
            _tok_n = 0
            # 增加对 <think>...</think> 思考链内容的过滤逻辑
            in_think = False
            think_buffer = ""
            _last_yield_time = _time.time()
            
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        token = data.get("response", "")
                        if token:
                            # 过滤 ChatML 格式 of 控制 token
                            token = _CTRL_TOKEN_RE.sub('', token)
                            if not token:
                                continue
                            
                            # 拼接思考状态机缓冲区以判断 think 标签
                            if not in_think:
                                think_buffer += token
                                if "<think>" in think_buffer:
                                    in_think = True
                                    # 将 <think> 之前的内容提取输出
                                    pre_think = think_buffer.split("<think>")[0]
                                    if pre_think:
                                        _tok_n += len(pre_think)
                                        _last_yield_time = _time.time()
                                        yield pre_think
                                    think_buffer = ""
                                else:
                                    # 没检测到 <think> 且缓冲区有一定长度时，安全释放前段
                                    if len(think_buffer) > 10:
                                        _tok_n += len(think_buffer)
                                        _last_yield_time = _time.time()
                                        yield think_buffer
                                        think_buffer = ""
                            else:
                                think_buffer += token
                                if "</think>" in think_buffer:
                                    in_think = False
                                    # 将 </think> 之后的内容提取输出
                                    post_think = think_buffer.split("</think>")[1]
                                    if post_think:
                                        _tok_n += len(post_think)
                                        _last_yield_time = _time.time()
                                        yield post_think
                                    think_buffer = ""
                                else:
                                    # 在 <think> 内的内容直接吞掉。但若距离上次发送已超 1 秒，输出不可见心跳包维持连接
                                    if _time.time() - _last_yield_time > 1.0:
                                        _last_yield_time = _time.time()
                                        yield "\u200b"

                        if data.get("done", False):
                            # 流结束时释防缓冲区内剩余内容（如果在 think 之外）
                            if not in_think and think_buffer:
                                yield think_buffer
                            if data.get("done_reason") == "length":
                                yield "\n\n> ⚠️ 输出已达最大字数限制。如需继续，请回复“继续”。"
                            return
                    except json.JSONDecodeError:
                        logger.warning(f"解析 Ollama 响应失败: {line[:100]}")
                        continue
            if _tok_n == 0:
                logger.warning(f"Ollama 返回 0 tokens (attempt {_attempt+1})")
                yield "⚠️ 大模型未生成有效回答，请尝试换一种方式提问，或切换到“深度思考”模式重试。"
            return
        except Exception as _e:
            _sc = getattr(getattr(_e, "response", None), "status_code", 0)
            if _sc == 503 and _attempt < _max_retries - 1:
                logger.warning(f"Ollama 503 (attempt {_attempt+1}), retrying...")
                await _aio.sleep(1 + _attempt)
                continue
            logger.exception("Ollama 调用失败")
            yield "❌ AI 服务暂时不可用，请稍后重试。"
            return


async def get_ollama_status() -> dict:
    """
    查询 Ollama 服务状态和已加载的模型列表。
    """
    try:
        client = get_client()
        resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        models = [
            {
                "name": m["name"],
                "size_gb": round(m["size"] / 1e9, 1),
                "family": m.get("details", {}).get("family", "unknown"),
                "parameter_size": m.get("details", {}).get("parameter_size", ""),
            }
            for m in data.get("models", [])
        ]
        return {"status": "online", "models": models}
    except Exception as e:
        logger.exception("Ollama 连接失败")
        return {"status": "offline", "models": [], "error": str(e)}

async def switch_ollama_model(new_model: str, previous_model: Optional[str] = None) -> dict:
    """
    手动卸载旧模型，并预加载新模型。
    """
    url = f"{settings.OLLAMA_BASE_URL}/api/generate"
    try:
        client = get_client()
        # 1. 卸载旧模型 (如果不同)
        if previous_model and previous_model != new_model:
            await client.post(url, json={
                "model": previous_model,
                "keep_alive": 0
            })
        
        # 2. 预加载新模型
        # 传一个空的请求即可让 Ollama 将模型加载到显存
        resp = await client.post(url, json={
            "model": new_model,
            "keep_alive": "10m"
        })
        resp.raise_for_status()
        return {"status": "success", "model": new_model}
    except Exception as e:
        logger.error(f"切换 Ollama 模型失败: {e}")
        return {"status": "error", "message": str(e)}


# ═══════════════════════════════════════════════════════════════
# 模型预热 & 定时心跳机制
# WHY: E2E 测试发现首次推理 TTFT 高达 85 秒（模型冷启动），
#      根因是 keep_alive=-1 在跨 Docker 网络调用 Ollama 时存在失效风险，
#      Ollama 可能因连接空闲超时而自动卸载 35B 模型。
#      解决方案：启动时主动预热 + 后台定时心跳，双重保障模型常驻 GPU 内存。
# ═══════════════════════════════════════════════════════════════

# WHY: 默认预热模型与 config 中默认大语言模型保持一致
DEFAULT_WARMUP_MODEL = settings.DEFAULT_LLM_MODEL

# WHY: 2 分钟间隔 — Vision 完成后最快 2 分钟内恢复 q4 可用。
#      Ollama 默认 keep_alive 是 5 分钟，2 分钟间隔提供 2.5x 安全余量。
HEARTBEAT_INTERVAL_SECONDS = 2 * 60


def is_heartbeat_enabled() -> bool:
    """
    检查是否启用了大模型心跳预热。
    优先读取 SQLite system_settings 数据库，未设置则默认返回 True。
    """
    try:
        from core.database import get_db
        with get_db() as conn:
            row = conn.execute("SELECT value FROM system_settings WHERE key = 'heartbeat_enabled'").fetchone()
            if row is not None:
                return row["value"] not in ("false", "0", "False")
    except Exception as e:
        logger.warning(f"读取数据库心跳设置失败: {e}")
    return False


async def unload_model(model: str = DEFAULT_WARMUP_MODEL):
    """
    命令 Ollama 立即卸载指定的模型，释放显存与内存资源。
    """
    url = f"{settings.OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": model,
        "prompt": "",
        "keep_alive": 0
    }
    try:
        client = get_client()
        logger.info(f"❄️ 正在命令 Ollama 卸载模型 {model}...")
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        logger.info(f"✅ 模型 {model} 已成功卸载并释放显存")
    except Exception as e:
        logger.warning(f"⚠️ 卸载模型失败: {e}")


async def warmup_model(model: str = DEFAULT_WARMUP_MODEL, force: bool = False) -> bool:
    """
    模型预热：向 Ollama 发送空 prompt + keep_alive=-1，
    强制将模型从硬盘加载到 GPU 内存（若尚未加载）。
    WHY: 空 prompt 不会触发推理计算，但会触发模型加载流程，
         约耗时 10-30 秒（取决于模型大小），远快于首次真实推理的 85 秒。
    """
    if not force and not is_heartbeat_enabled():
        logger.info(f"🔥 大模型心跳已被禁用，跳过本次预热 ({model})")
        return False
        
    url = f"{settings.OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": model,
        "prompt": "",
        "keep_alive": -1,
        "options": {
            "num_ctx": 16384
        }
    }
    try:
        client = get_client()
        logger.info(f"🔥 模型预热启动: {model}")
        resp = await client.post(url, json=payload, timeout=300.0)
        resp.raise_for_status()
        logger.info(f"✅ 模型预热完成: {model} 已常驻 GPU 内存")
        return True
    except Exception as e:
        # WHY: 预热失败不应阻断服务启动，仅记录警告
        logger.warning(f"⚠️ 模型预热失败（服务仍可启动，首次推理将触发冷加载）: {e}")
        return False


async def _heartbeat_loop(model: str, interval: int):
    """
    后台心跳循环：定期向 Ollama 发送 keep_alive 请求，
    防止模型因空闲超时被自动卸载。
    WHY: 这是一个无限循环的后台协程，通过 asyncio.create_task 启动，
         随 FastAPI 进程生命周期存在。
    """
    url = f"{settings.OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": model,
        "prompt": "",
        "keep_alive": -1,
        "options": {
            "num_ctx": 16384
        }
    }
    logger.info(f"💓 模型心跳守护已启动: {model}, 间隔 {interval}s")

    while True:
        await asyncio.sleep(interval)
        if not is_heartbeat_enabled():
            logger.debug("💓 大模型心跳守护已被禁用，跳过本次心跳")
            continue
        # WHY: Vision 模型处理期间跳过心跳，避免模型互踢
        if _is_vision_active():
            logger.info("💓 心跳跳过: Vision 模型正在处理中")
            continue
        try:
            client = get_client()
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            logger.debug(f"💓 心跳成功: {model} 仍在 GPU 内存中")
        except Exception as e:
            # WHY: 单次心跳失败不终止循环，下一轮重试即可
            logger.warning(f"💔 心跳失败（将在 {interval}s 后重试）: {e}")


_heartbeat_task: asyncio.Task | None = None

# WHY: Vision 模型处理期间暂停心跳，避免 qwen3.6 被加载后挤掉 Vision 模型。
#      Celery Worker 通过文件锁通知心跳协程暂停。
_VISION_LOCK_FILE = "/tmp/.vision_processing_lock"

def _is_vision_active() -> bool:
    """
    Check if vision processing is active via file lock.
    包含防死锁超时保护：如果锁文件超过 15 分钟未更新，认为进程已死，强制释放锁。
    """
    import os
    import time
    if not os.path.exists(_VISION_LOCK_FILE):
        return False
        
    try:
        mtime = os.path.getmtime(_VISION_LOCK_FILE)
        # 15分钟超时 (900秒)
        if time.time() - mtime > 900:
            logger.warning("⚠️ Vision 锁文件已过期 (>15分钟)，强制清理以防死锁")
            try:
                os.remove(_VISION_LOCK_FILE)
            except OSError:
                pass
            return False
        return True
    except Exception as e:
        logger.error(f"读取 Vision 锁状态失败: {e}")
        return False


async def start_model_heartbeat(model: str = DEFAULT_WARMUP_MODEL):
    """
    启动模型心跳后台任务（幂等：重复调用不会创建多个任务）。
    WHY: 在 FastAPI on_startup 中调用，确保整个服务生命周期内
         模型始终保持加载状态。
    """
    global _heartbeat_task
    if _heartbeat_task is not None and not _heartbeat_task.done():
        logger.info("💓 心跳任务已在运行，跳过重复启动")
        return

    _heartbeat_task = asyncio.create_task(
        _heartbeat_loop(model, HEARTBEAT_INTERVAL_SECONDS)
    )

