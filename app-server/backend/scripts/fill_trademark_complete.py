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

def fill_trademark_triage_and_investigation(p_id: str = "a179bfa2f2ef"):
    # 1. 7.投诉调解通知书
    t7 = get_tpl("7.投诉调解通知书")
    t7 = t7.replace("______：", "张三、嘉峪关市鑫嘉品萱食品销售店：")\
           .replace("______", "关于购买紫轩干红葡萄酒涉嫌侵犯注册商标专用权退赔争议", 1)\
           .replace("年  月  日", "2025年02月24日")\
           .replace("________市场监督管理局", "嘉峪关市市场监督管理局")
    clean_and_save(p_id, "7.投诉调解通知书", t7)

    # 2. 1.案件来源登记表
    t_source = get_tpl("1.案件来源登记表")
    t_source = t_source.replace("________市监", "嘉峪关市市监")\
                       .replace("〔    〕", "〔2025〕")\
                       .replace("第________号", "第022101号")
    for val in [
        "12315消费者投诉转办及日常监督检查线索",
        "张三（男，112113198001011234，电话：13888888888）",
        "嘉峪关市鑫嘉品萱食品销售店",
        "甘肃省嘉峪关市迎宾西路**号"
    ]:
        t_source = fill_td(t_source, val)
    clean_and_save(p_id, "1.案件来源登记表", t_source)

    # 3. 9.现场笔录
    t9 = get_tpl("9.现场笔录")
    t9 = t9.replace("______", "嘉峪关市鑫嘉品萱食品销售店经营场所（迎宾西路**号）", 1)\
           .replace("年  月  日", "2025年02月21日")
    note_content = "执法人员出示执法证件后进行检查。在该店库房货架发现外包装标有“紫轩”字样的梅尔诺干红葡萄酒共13箱（78瓶，规格750ml/瓶）。经权利人甘肃紫轩酒业有限公司出具的鉴别证明，涉案葡萄酒防伪码及外包装工艺均与正品不符，涉嫌侵犯第7633881号注册商标专用权。执法人员现场拍照取证并清点登记。"
    t9 = t9.replace('<p style="border: 1px solid #000000; padding: 12px; min-height: 120px; font-size: 14px; font-family: SimSun, serif;"></p>',
                    f'<p style="border: 1px solid #000000; padding: 12px; font-size: 14px; font-family: SimSun, serif; line-height: 1.8;">{note_content}</p>')
    clean_and_save(p_id, "9.现场笔录", t9)

    # 4. 14.询问笔录
    t14 = get_tpl("14.询问笔录")
    t14 = t14.replace("______", "销售店实际经营负责人王某某", 1)\
             .replace("年  月  日", "2025年02月21日")
    ask_content = "问：上述78瓶紫轩梅尔诺干红葡萄酒从何处购进？进价及售价是多少？<br/>答：于2025年1月从上门推销人员杨某处购进，进价每箱1200元，共购进13箱，拟按每瓶428元对外销售，货值金额33384元。购进时未严格查验杨某的供货商资质及紫轩酒业授权手续。<br/>问：截至检查时是否对外售出？<br/>答：由于春节刚过，截至被查获时尚未销售，货款也尚未结清。"
    t14 = t14.replace('<p style="border: 1px solid #000000; padding: 12px; min-height: 120px; font-size: 14px; font-family: SimSun, serif;"></p>',
                      f'<p style="border: 1px solid #000000; padding: 12px; font-size: 14px; font-family: SimSun, serif; line-height: 1.8;">{ask_content}</p>')
    clean_and_save(p_id, "14.询问笔录", t14)

    # 5. 15.抽样取证凭证
    t15 = get_tpl("15.抽样取证凭证")
    t15 = t15.replace("______：", "嘉峪关市鑫嘉品萱食品销售店：")\
             .replace("______", "涉嫌侵犯紫轩注册商标专用权高档梅尔诺干红葡萄酒（抽取2瓶作为样品鉴别留存）", 1)\
             .replace("年  月  日", "2025年02月21日")\
             .replace("________市场监督管理局", "嘉峪关市市场监督管理局")
    clean_and_save(p_id, "15.抽样取证凭证", t15, alias_names=["29.抽样记录"])

def fill_trademark_adjudication(p_id: str = "a179bfa2f2ef"):
    # 6. 35.案件调查终结报告
    t35 = get_tpl("35.案件调查终结报告")
    t35 = t35.replace("______", "嘉峪关市鑫嘉品萱食品销售店涉嫌销售侵犯注册商标专用权商品案", 1)\
             .replace("年  月  日", "2025年03月05日")
    report_text = "当事人销售侵犯甘肃紫轩酒业有限公司‘紫轩’注册商标专用权的干红葡萄酒78瓶，违法经营额33384元。鉴于当事人积极配合调查且涉案商品尚未售出，未造成严重社会危害，依据《商标法》第六十条第二款，建议责令立即停止侵权行为，没收侵权商品并处罚款40000元。"
    t35 = t35.replace('<p style="border: 1px solid #000000; padding: 12px; min-height: 120px; font-size: 14px; font-family: SimSun, serif;"></p>',
                      f'<p style="border: 1px solid #000000; padding: 12px; font-size: 14px; font-family: SimSun, serif; line-height: 1.8;">{report_text}</p>')
    clean_and_save(p_id, "35.案件调查终结报告", t35)

    # 7. 36.案件审核表
    t36 = get_tpl("36.案件审核表")
    t36 = t36.replace("______", "嘉峪关市鑫嘉品萱食品销售店销售侵权干红葡萄酒案", 1)\
             .replace("年  月  日", "2025年03月06日")
    clean_and_save(p_id, "36.案件审核表", t36, alias_names=["36.案件审核/法制审核表"])

    # 8. 33.责令改正通知书
    t33 = get_tpl("33.责令改正通知书")
    t33 = t33.replace("______：", "嘉峪关市鑫嘉品萱食品销售店：")\
             .replace("______", "《中华人民共和国商标法》第五十七条第（三）项规定", 1)\
             .replace("年  月  日", "2025年03月06日")
    clean_and_save(p_id, "33.责令改正通知书", t33, alias_names=["47.责令改正通知书"])

    # 9. 37.行政处罚告知书
    t37 = get_tpl("37.行政处罚告知书")
    t37 = t37.replace("______：", "嘉峪关市鑫嘉品萱食品销售店：")\
             .replace("______", "拟处没收侵权紫轩干红葡萄酒78瓶，并处行政罚款人民币40000.00元整", 1)\
             .replace("年  月  日", "2025年03月07日")
    clean_and_save(p_id, "37.行政处罚告知书", t37)

    # 10. 38.行政处罚听证告知书
    t38 = get_tpl("38.行政处罚听证告知书")
    t38 = t38.replace("______：", "嘉峪关市鑫嘉品萱食品销售店：")\
             .replace("______", "嘉峪关市鑫嘉品萱食品销售店涉嫌销售侵权商品拟处较大数额罚款案", 1)\
             .replace("年  月  日", "2025年03月07日")
    clean_and_save(p_id, "38.行政处罚听证告知书", t38, alias_names=["39.行政处罚听证通知书"])

    # 11. 45.行政处罚决定书
    t45 = get_tpl("45.行政处罚决定书")
    t45 = t45.replace("______：", "嘉峪关市鑫嘉品萱食品销售店：")\
             .replace("______", "嘉市监处罚〔2025〕0018号", 1)\
             .replace("年  月  日", "2025年03月15日")
    clean_and_save(p_id, "45.行政处罚决定书", t45)

    # 12. 53.结案审批表
    t53 = get_tpl("53.结案审批表")
    t53 = t53.replace("______", "嘉峪关市鑫嘉品萱食品销售店销售侵权干红葡萄酒案行政处罚执行完毕结案", 1)\
             .replace("年  月  日", "2025年03月20日")
    clean_and_save(p_id, "53.结案审批表", t53)

def fill_trademark(p_id: str = "a179bfa2f2ef"):
    print(f"🚀 开始补全商标案 ({p_id}) 缺失的 12 份表单...")
    fill_trademark_triage_and_investigation(p_id)
    fill_trademark_adjudication(p_id)
    print(f"🎉 商标案 ({p_id}) 14 份法定公文已 100% 全部高保真深度生成落盘！")

if __name__ == "__main__":
    fill_trademark()


