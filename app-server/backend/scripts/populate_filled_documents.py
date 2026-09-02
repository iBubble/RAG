import sys
import os
import json
import time
import re
from pathlib import Path
from datetime import datetime

sys.path.append("/app/backend")
from core.config import settings

DATA_ROOT = Path(settings.DATA_DIR)
TPL_PATH = Path("/app/backend/local_data/ai_templates.json")

def load_templates():
    with open(TPL_PATH, encoding="utf-8") as f:
        cats = json.load(f)
    tpl_map = {}
    for c in cats:
        for t in c["tables"]:
            tpl_map[t["name"]] = t["template"]
    return tpl_map

def save_doc(project_id: str, form_name: str, html_content: str):
    p_dir = DATA_ROOT / "documents" / project_id
    p_dir.mkdir(parents=True, exist_ok=True)
    
    doc_id = "doc_" + hashlib.md5(f"{project_id}_{form_name}".encode("utf-8")).hexdigest()[:10]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = f"{form_name}_{now_str}"
    
    doc_data = {
        "id": doc_id,
        "title": title,
        "content": html_content,
        "timestamp": int(time.time() * 1000),
        "tokens": len(html_content),
        "sections": [],
        "isAutoSave": False
    }
    (p_dir / f"{doc_id}.json").write_text(json.dumps(doc_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📄 [{project_id}] 成功保存已填报公文: 《{form_name}》")

import hashlib

def populate_case_guazi(tpl_map):
    p_id = "case_guazi_2026"
    
    # 1. 投诉登记表
    t_name = "1.投诉登记表"
    raw_tpl = tpl_map.get(t_name, "")
    c1 = raw_tpl.replace("<td>&nbsp;</td>", "<td>赵明远</td>", 1)\
                .replace("<td>&nbsp;</td>", "<td>138****6721</td>", 1)\
                .replace("<td>&nbsp;</td>", "<td>上海市浦东新区张江镇***路128号</td>", 1)\
                .replace("<td>&nbsp;</td>", "<td>好邻居便利店（张江店）</td>", 1)\
                .replace("<td>&nbsp;</td>", "<td>味之家 焦糖味瓜子标签瑕疵退赔争议</td>", 1)
    if "投诉内容" in c1:
        c1 = c1.replace("投诉内容：", "投诉内容：投诉人于2026年7月18日购买焦糖味瓜子1袋（金额2.50元），发现产品执行标准未标年代号、净含量字符高度约2.1mm不足3mm，要求退还货款2.50元并赔偿1000元。")
    save_doc(p_id, t_name, c1)

    # 2. 投诉受理决定书
    t_name = "5.投诉受理决定书"
    raw_tpl = tpl_map.get(t_name, "")
    c2 = raw_tpl.replace("______：", "赵明远：")\
                .replace("______", "好邻居便利店（张江店）", 1)\
                .replace("______", "味之家焦糖味瓜子消费退赔争议", 1)\
                .replace("年  月  日", "2026年07月21日")
    save_doc(p_id, t_name, c2)

    # 3. 案件来源登记表
    t_name = "1.案件来源登记表"
    raw_tpl = tpl_map.get(t_name, "")
    c3 = raw_tpl.replace("______", "沪市监浦案源〔2026〕071901号", 1)\
                .replace("<td></td>", "<td>全国12315平台转办投诉举报</td>", 1)\
                .replace("<td></td>", "<td>赵明远（138****6721）</td>", 1)\
                .replace("<td></td>", "<td>好邻居便利店（张江店）</td>", 1)
    c3 = re.sub(r'(<td[^>]*>)\s*&nbsp;\s*(</td>)', r'\1上海市浦东新区张江镇***路128号\2', c3, count=1)
    save_doc(p_id, t_name, c3)

    # 4. 现场笔录
    t_name = "9.现场笔录"
    raw_tpl = tpl_map.get(t_name, "")
    c4 = raw_tpl.replace("______", "好邻居便利店（张江店）", 1)\
                .replace("年  月  日", "2026年07月20日")
    save_doc(p_id, t_name, c4)

    # 5. 案件调查终结报告
    t_name = "35.案件调查终结报告"
    raw_tpl = tpl_map.get(t_name, "")
    c5 = raw_tpl.replace("______", "好邻居便利店涉嫌销售标签瑕疵食品案", 1)\
                .replace("年  月  日", "2026年07月25日")
    save_doc(p_id, t_name, c5)

    # 6. 责令改正通知书
    t_name = "47.责令改正通知书"
    raw_tpl = tpl_map.get(t_name, "")
    c6 = raw_tpl.replace("______：", "好邻居便利店（张江店）：")\
                .replace("______", "《食品安全法》第67条及第125条第2款", 1)\
                .replace("年  月  日", "2026年07月25日")
    save_doc(p_id, t_name, c6)

    # 7. 不予行政处罚决定书
    t_name = "46.不予行政处罚决定书"
    raw_tpl = tpl_map.get(t_name, "")
    c7 = raw_tpl.replace("______：", "好邻居便利店（张江店）：")\
                .replace("______", "沪市监浦不罚〔2026〕0012号", 1)\
                .replace("年  月  日", "2026年07月26日")
    save_doc(p_id, t_name, c7)

    # 8. 结案审批表
    t_name = "53.结案审批表"
    raw_tpl = tpl_map.get(t_name, "")
    c8 = raw_tpl.replace("______", "好邻居便利店销售标签瑕疵食品不予处罚结案", 1)\
                .replace("年  月  日", "2026年07月27日")
    save_doc(p_id, t_name, c8)

def populate_case_beef(tpl_map):
    p_id = "case_beef_2026"
    
    # 1. 举报登记表
    t_name = "2.举报登记表"
    raw_tpl = tpl_map.get(t_name, "")
    b1 = raw_tpl.replace("<td>&nbsp;</td>", "<td>林素芬（要求保密）</td>", 1)\
                .replace("<td>&nbsp;</td>", "<td>159****3082</td>", 1)\
                .replace("<td>&nbsp;</td>", "<td>光泽县寨里镇优鲜百货商行（视频号：闽北山货直供）</td>", 1)\
                .replace("<td>&nbsp;</td>", "<td>涉嫌未取得分装许可生产销售五香卤香牛肉</td>", 1)
    save_doc(p_id, t_name, b1)

    # 2. 举报立案告知书
    t_name = "8.举报立案告知书"
    raw_tpl = tpl_map.get(t_name, "")
    b2 = raw_tpl.replace("______：", "林素芬：")\
                .replace("______", "光泽县寨里镇优鲜百货商行涉嫌无证分装牛肉案", 1)\
                .replace("年  月  日", "2026年08月12日")
    save_doc(p_id, t_name, b2)

    # 3. 案件来源登记表
    t_name = "1.案件来源登记表"
    raw_tpl = tpl_map.get(t_name, "")
    b3 = raw_tpl.replace("______", "闽市监光案源〔2026〕081001号", 1)\
                .replace("<td></td>", "<td>全国12315网络平台线索移送</td>", 1)\
                .replace("<td></td>", "<td>林素芬（159****3082）</td>", 1)\
                .replace("<td></td>", "<td>光泽县寨里镇优鲜百货商行</td>", 1)
    save_doc(p_id, t_name, b3)

    # 4. 立案审批表
    t_name = "7.立案审批表"
    raw_tpl = tpl_map.get(t_name, "")
    b4 = raw_tpl.replace("______", "光泽县寨里镇优鲜百货商行涉嫌未取得许可从事食品生产案", 1)\
                .replace("年  月  日", "2026年08月11日")
    save_doc(p_id, t_name, b4)

    # 5. 现场笔录
    t_name = "9.现场笔录"
    raw_tpl = tpl_map.get(t_name, "")
    b5 = raw_tpl.replace("______", "光泽县寨里镇优鲜百货商行分装及仓储场所", 1)\
                .replace("年  月  日", "2026年08月11日")
    save_doc(p_id, t_name, b5)

    # 6. 实施行政强制措施决定书
    t_name = "21.实施行政强制措施决定书"
    raw_tpl = tpl_map.get(t_name, "")
    b6 = raw_tpl.replace("______：", "光泽县寨里镇优鲜百货商行：")\
                .replace("______", "扣押涉案分装牛肉200袋及真空封口机1台", 1)\
                .replace("年  月  日", "2026年08月11日")
    save_doc(p_id, t_name, b6)

    # 7. 案件调查终结报告
    t_name = "35.案件调查终结报告"
    raw_tpl = tpl_map.get(t_name, "")
    b7 = raw_tpl.replace("______", "优鲜百货商行未取得食品生产分装许可从事食品生产经营案", 1)\
                .replace("年  月  日", "2026年08月20日")
    save_doc(p_id, t_name, b7)

    # 8. 行政处罚告知书
    t_name = "37.行政处罚告知书"
    raw_tpl = tpl_map.get(t_name, "")
    b8 = raw_tpl.replace("______：", "光泽县寨里镇优鲜百货商行：")\
                .replace("______", "拟没收违法所得、没收扣押牛肉及封口机并处罚款50000元", 1)\
                .replace("年  月  日", "2026年08月22日")
    save_doc(p_id, t_name, b8)

    # 9. 行政处罚决定书
    t_name = "45.行政处罚决定书"
    raw_tpl = tpl_map.get(t_name, "")
    b9 = raw_tpl.replace("______", "闽市监光处〔2026〕0088号", 1)\
                .replace("______：", "光泽县寨里镇优鲜百货商行：")\
                .replace("年  月  日", "2026年08月29日")
    save_doc(p_id, t_name, b9)

    # 10. 结案审批表
    t_name = "53.结案审批表"
    raw_tpl = tpl_map.get(t_name, "")
    b10 = raw_tpl.replace("______", "优鲜百货商行无证分装牛肉案行政处罚执行完毕结案", 1)\
                 .replace("年  月  日", "2026年09月01日")
    save_doc(p_id, t_name, b10)

if __name__ == "__main__":
    print("🚀 开始自动预填充两大演示项目的核心公文表单...")
    tpls = load_templates()
    populate_case_guazi(tpls)
    populate_case_beef(tpls)
    print("\n🎉 两大演示项目全部公文表单高保真自动填报完成！")
