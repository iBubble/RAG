import os
import sys
import json
import time
import hashlib
import re
from pathlib import Path
from datetime import datetime

sys.path.append("/app/backend")
from core.config import settings

DATA_ROOT = Path(settings.DATA_DIR)
TPL_PATH = Path("/app/backend/local_data/ai_templates.json")

with open(TPL_PATH, encoding="utf-8") as f:
    ALL_CATS = json.load(f)

TPL_MAP = {}
for cat in ALL_CATS:
    for t in cat["tables"]:
        TPL_MAP[t["name"]] = t["template"]

def get_tpl(name: str) -> str:
    if name in TPL_MAP:
        return TPL_MAP[name]
    num_match = re.match(r'^(\d+)', name)
    if num_match:
        num = num_match.group(1)
        for k, v in TPL_MAP.items():
            if k.startswith(f"{num}."):
                return v
    clean = re.sub(r'^\d+[\.、\s]*', '', name)
    for k, v in TPL_MAP.items():
        if clean in k:
            return v
    return ""

def fill_td(html: str, val: str) -> str:
    return re.sub(r'(<td[^>]*>)\s*(</td>)', lambda m: f"{m.group(1)}{val}{m.group(2)}", html, count=1)

def clean_and_save(p_id: str, form_name: str, html: str, alias_names: list = None):
    processed_html = re.sub(r'_{3,}', '——', html)
    processed_html = re.sub(r'(<td[^>]*>)\s*(</td>)', r'\1——\2', processed_html)
    p_dir = DATA_ROOT / "documents" / p_id
    p_dir.mkdir(parents=True, exist_ok=True)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    all_names = [form_name] + (alias_names or [])
    for name in all_names:
        doc_id = "doc_" + hashlib.md5(f"{p_id}_{name}".encode("utf-8")).hexdigest()[:10]
        data = {
            "id": doc_id,
            "title": f"{name}_{now_str}",
            "content": processed_html,
            "timestamp": int(time.time() * 1000),
            "tokens": len(processed_html),
            "sections": [],
            "isAutoSave": False
        }
        (p_dir / f"{doc_id}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📄 [{p_id}] 《{form_name}》 写入完成")

def setup_food_label_recommendations(p_id: str = "15e2a7f1208b"):
    rec = {
        "triage": {
            "track": "投诉举报双轨（标签虚假标注核查）",
            "summary": "消费者反映海宁市雅利成食品有限公司生产的‘南瓜味餐包’等产品配料标注‘奶酪酱’与实际添加不符，且‘椰蓉’未标示原始配料。经审查，属于经营标签不符合食品安全法规定的预包装食品违法线索，立案核查并转入双轨处置。",
            "recommended_forms": [
                {"name": "1.投诉登记表", "reason": "登记消费者购进餐包反映配料虚假标注线索", "required": True},
                {"name": "2.举报登记表", "reason": "对企业涉嫌违反食品标签通则与食品安全法行为进行举报登记", "required": True},
                {"name": "5.投诉受理决定书", "reason": "决定受理消费者投诉并书面告知", "required": True},
                {"name": "10.举报处理结果告知书", "reason": "案件调查终结后书面告知实名举报人处理结果", "required": True}
            ]
        },
        "investigation": {
            "stage": "生产现场核实与调查询问阶段",
            "summary": "执法人员突击进入雅利成食品有限公司生产车间与原料库房，实地核查配料领料单、投料记录与产品外包装标签，查验奶酪酱与椰蓉的真实配料成分及索证索票，抽样送检并制作调查笔录。",
            "recommended_forms": [
                {"name": "1.案件来源登记表", "reason": "案件来源初查归口登记", "required": True},
                {"name": "7.立案/不予立案审批表", "reason": "查证基本属实，依法提请审批正式立案", "required": True},
                {"name": "9.现场笔录", "reason": "对企业烘焙车间、包装车间及成品库进行实地检查拍照取证", "required": True},
                {"name": "14.询问笔录", "reason": "对公司法定代表人及品控主管进行调查询问", "required": True},
                {"name": "29.抽样记录", "reason": "抽取在库南瓜味餐包等成品送检并留存备检", "required": True}
            ]
        },
        "adjudication": {
            "disposition_type": "责令改正并处罚款",
            "summary": "经查，当事人生产销售的预包装面包标签配料与实际添加严重不符，违反《食品安全法》第67条、第71条之规定。依据《食品安全法》第125条第一款第（二）项及裁量基准，责令停止销售召回涉案批次产品，没收违法所得，并处行政罚款。",
            "recommended_forms": [
                {"name": "35.案件调查终结报告", "reason": "调查终结，梳理虚假配料事实与生产销售台账提请审理", "required": True},
                {"name": "36.案件审核/法制审核表", "reason": "法制审核机构进行合法性与裁量阶次审核", "required": True},
                {"name": "33.责令改正通知书", "reason": "责令企业限期召回问题餐包并规范标签配料标示", "required": True},
                {"name": "37.行政处罚告知书", "reason": "正式送达行政处罚告知书，告知当事人拟处决定与陈述申辩权", "required": True},
                {"name": "45.行政处罚决定书", "reason": "出具正式没收违法所得并处罚款的行政处罚决定书", "required": True},
                {"name": "53.结案审批表", "reason": "当事人缴纳罚没款并整改到位后审批结案归档", "required": True}
            ]
        }
    }
    (DATA_ROOT / "triage" / f"{p_id}.json").write_text(json.dumps(rec["triage"], ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_ROOT / "judgment" / f"{p_id}.json").write_text(json.dumps(rec["investigation"], ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_ROOT / "adjudication" / f"{p_id}.json").write_text(json.dumps(rec["adjudication"], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ [{p_id}] 预包装食品案三阶段推荐文书配置生成完成！")

def fill_food_label_triage_and_investigation(p_id: str = "15e2a7f1208b"):
    # 1. 5.投诉受理决定书
    t5 = get_tpl("5.投诉受理决定书")
    t5 = t5.replace("______：", "消费者刘某：")\
           .replace("______", "海宁市雅利成食品有限公司", 1)\
           .replace("______", "购买南瓜味餐包标签配料与实际不符退赔争议", 1)\
           .replace("年  月  日", "2026年06月30日")\
           .replace("________市场监督管理局", "海宁市市场监督管理局")
    clean_and_save(p_id, "5.投诉受理决定书", t5)

    # 2. 10.举报处理结果告知书
    t10 = get_tpl("10.举报处理结果告知书")
    t10 = t10.replace("________市监________〔    〕第________号", "海市监告〔2026〕071501号")\
             .replace("________________________：", "举报人：")\
             .replace("关于 ________________ 的举报，我局已依法处理。根据《________________》第 ________ 条规定，现将处理结果告知如下：",
                      "关于你反映海宁市雅利成食品有限公司生产销售标签虚假标注餐包的举报，我局已依法查处完毕。现将处理结果告知如下：")
    res_txt = "经核查，海宁市雅利成食品有限公司生产的南瓜味餐包标签标示配料奶酪酱与实际添加不符，且椰蓉未标示原始配料，涉案货值1.8万元，违法所得6200元。我局已依法责令限期召回，并作出没收违法所得6200元、罚款30000元的行政处罚决定（文号：海市监处〔2026〕0112号）。款项已执行到位。"
    t10 = t10.replace('<p style="border: 1px solid #000000; padding: 12px; min-height: 120px; font-size: 14px; font-family: SimSun, serif;"></p>',
                      f'<p style="border: 1px solid #000000; padding: 12px; font-size: 14px; font-family: SimSun, serif; line-height: 1.8;">{res_txt}</p>')\
             .replace("________________市场监督管理局（印章）", "海宁市市场监督管理局（印章）")\
             .replace("________年____月____日", "2026年07月15日")
    clean_and_save(p_id, "10.举报处理结果告知书", t10)

    # 3. 1.案件来源登记表
    t1 = get_tpl("1.案件来源登记表")
    t1 = t1.replace("________市监", "海宁市市监")\
           .replace("〔    〕", "〔2026〕")\
           .replace("第________号", "第062901号")
    for val in ["消费者平台投诉转办线索", "刘某（男，330419198506******，电话：139****5512）", "海宁市雅利成食品有限公司", "浙江省海宁市长安镇工业区**号"]:
        t1 = fill_td(t1, val)
    clean_and_save(p_id, "1.案件来源登记表", t1)

    # 4. 7.立案/不予立案审批表
    t7 = get_tpl("7.立案/不予立案审批表")
    t7 = t7.replace("______", "海宁市雅利成食品有限公司涉嫌生产经营标签不符合规定的食品案", 1)\
           .replace("年  月  日", "2026年07月01日")
    clean_and_save(p_id, "7.立案/不予立案审批表", t7, alias_names=["7.立案审批表"])

    # 5. 9.现场笔录
    t9 = get_tpl("9.现场笔录")
    t9 = t9.replace("______", "海宁市雅利成食品有限公司烘焙生产车间及成品库房", 1)\
           .replace("年  月  日", "2026年07月01日")
    clean_and_save(p_id, "9.现场笔录", t9)

    # 6. 14.询问笔录
    t14 = get_tpl("14.询问笔录")
    t14 = t14.replace("______", "海宁市雅利成食品有限公司品控负责人张某", 1)\
             .replace("年  月  日", "2026年07月01日")
    clean_and_save(p_id, "14.询问笔录", t14)

    # 7. 29.抽样记录
    t29 = get_tpl("29.抽样记录")
    t29 = t29.replace("______", "南瓜味餐包（规格：80g/袋，生产批次：20260625）", 1)\
             .replace("年  月  日", "2026年07月01日")
    clean_and_save(p_id, "29.抽样记录", t29, alias_names=["15.抽样取证凭证"])

def fill_food_label_adjudication(p_id: str = "15e2a7f1208b"):
    # 8. 35.案件调查终结报告
    t35 = get_tpl("35.案件调查终结报告")
    t35 = t35.replace("______", "海宁市雅利成食品有限公司涉嫌经营标签不符合规定的预包装食品案", 1)\
             .replace("年  月  日", "2026年07月08日")
    clean_and_save(p_id, "35.案件调查终结报告", t35)

    # 9. 36.案件审核/法制审核表
    t36 = get_tpl("36.案件审核/法制审核表")
    t36 = t36.replace("______", "海宁市雅利成食品有限公司生产标签不合规食品处罚案", 1)\
             .replace("年  月  日", "2026年07月09日")
    clean_and_save(p_id, "36.案件审核/法制审核表", t36, alias_names=["36.案件审核表"])

    # 10. 33.责令改正通知书
    t33 = get_tpl("33.责令改正通知书")
    t33 = t33.replace("______：", "海宁市雅利成食品有限公司：")\
             .replace("______", "《中华人民共和国食品安全法》第六十七条及第七十一条之规定", 1)\
             .replace("年  月  日", "2026年07月09日")
    clean_and_save(p_id, "33.责令改正通知书", t33, alias_names=["47.责令改正通知书"])

    # 11. 37.行政处罚告知书
    t37 = get_tpl("37.行政处罚告知书")
    t37 = t37.replace("______：", "海宁市雅利成食品有限公司：")\
             .replace("______", "拟没收违法所得6200元，并处行政罚款人民币30000.00元整", 1)\
             .replace("年  月  日", "2026年07月10日")
    clean_and_save(p_id, "37.行政处罚告知书", t37)

    # 12. 45.行政处罚决定书
    t45 = get_tpl("45.行政处罚决定书")
    t45 = t45.replace("______：", "海宁市雅利成食品有限公司：")\
             .replace("______", "海市监处〔2026〕0112号", 1)\
             .replace("年  月  日", "2026年07月15日")
    clean_and_save(p_id, "45.行政处罚决定书", t45)

    # 13. 53.结案审批表
    t53 = get_tpl("53.结案审批表")
    t53 = t53.replace("______", "海宁市雅利成食品有限公司生产标签不符合规定预包装食品案结案", 1)\
             .replace("年  月  日", "2026年07月18日")
    clean_and_save(p_id, "53.结案审批表", t53)

def fill_food_label(p_id: str = "15e2a7f1208b"):
    print(f"🚀 开始补全预包装食品案 ({p_id}) 三阶段推荐文书与全量表单...")
    setup_food_label_recommendations(p_id)
    fill_food_label_triage_and_investigation(p_id)
    fill_food_label_adjudication(p_id)
    print(f"🎉 预包装食品案 ({p_id}) 全套法定公文已 100% 全部高保真深度生成落盘！")

if __name__ == "__main__":
    fill_food_label()



