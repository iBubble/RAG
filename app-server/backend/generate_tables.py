import fitz
import re
import json
import os

def clean_text(text):
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line_strip = line.strip()
        # 过滤页码，如 — 1 —
        if re.match(r'^—\s*\d+\s*—$', line_strip):
            continue
        cleaned_lines.append(line_strip)
    
    # 合并连续的空行，使版式更加整洁紧凑
    res = []
    last_empty = False
    for line in cleaned_lines:
        if line == '':
            if not last_empty:
                res.append(line)
                last_empty = True
        else:
            res.append(line)
            last_empty = False
            
    return '\n'.join(res)

def process_complaints():
    doc = fitz.open("/app/backend/《市场监督管理部门处理投诉举报文书式样》.pdf")
    templates = []
    
    catalog = {
        1: "投诉登记表",
        2: "举报登记表",
        3: "投诉/举报分送通知书",
        4: "限期提供身份证明材料通知书",
        5: "投诉受理决定书",
        6: "投诉不予受理决定书",
        7: "投诉调解通知书",
        8: "投诉终止调解决定书",
        9: "投诉调解书",
        10: "举报处理结果告知书"
    }
    
    for page_idx in range(3, len(doc)):
        page = doc[page_idx]
        text = page.get_text()
        cleaned = clean_text(text)
        
        doc_num = page_idx - 2  # 页数 4 对应文书 1
        name = catalog.get(doc_num, f"文书式样{doc_num}")
        
        templates.append({
            "name": f"{doc_num}.{name}",
            "template": cleaned.strip()
        })
        
    return templates

def process_penalty():
    doc = fitz.open("/app/backend/市场监督管理行政处罚文书格式范本（2021年修订版）.pdf.pdf")
    templates = []
    
    catalog = [
        "1.案件来源登记表", "2.指定管辖通知书", "3.案件交办通知书", "4.案件移送函",
        "5.涉嫌犯罪案件移送书", "6.查封/扣押物品移送告知书", "7.立案/不予立案审批表",
        "8.行政处罚案件有关事项审批表", "9.现场笔录", "10.送达地址确认书",
        "11.证据提取单", "12.电子数据证据提取笔录", "13.询问通知书", "14.询问笔录",
        "15.限期提供材料通知书", "16.协助辨认/鉴别通知书", "17.协助调查函",
        "18.协助扣押通知书", "19.先行登记保存证据通知书", "20.解除先行登记保存证据通知书",
        "21.实施行政强制措施决定书", "22.延长行政强制措施期限决定书", "23.解除行政强制措施决定书",
        "24.场所/设施/财物清单", "25.封条", "26.实施行政强制措施场所/设施/财物委托保管书",
        "27.先行处置物品确认书", "28.先行处置物品公告", "29.抽样记录",
        "30.检测/检验/检疫/鉴定委托书", "31.检测/检验/检疫/鉴定期间告知书",
        "32.检测/检验/检疫/鉴定结果告知书", "33.责令改正通知书", "34.责令退款通知书",
        "35.案件调查终结报告", "36.案件审核/法制审核表", "37.行政处罚告知书",
        "38.陈述申辩笔录", "39.行政处罚听证通知书", "40.听证笔录", "41.听证报告",
        "42.行政处罚案件集体讨论记录", "43.行政处理决定审批表", "44.当场行政处罚决定书",
        "45.行政处罚决定书", "46.不予行政处罚决定书", "47.延期/分期缴纳罚款通知书",
        "48.行政处罚决定履行催告书", "49.强制执行申请书", "50.送达回证",
        "51.行政处罚文书送达公告", "52.涉案物品处理记录", "53.结案审批表",
        "54.卷宗封面", "55.卷内文件目录", "56.卷内备考表"
    ]
    
    current_doc = None
    current_text_lines = []
    
    for page_idx in range(4, len(doc)):
        page = doc[page_idx]
        text = page.get_text()
        cleaned = clean_text(text)
        
        found_new = False
        for doc_name in catalog:
            clean_name = doc_name.split('.', 1)[1] if '.' in doc_name else doc_name
            # 如果这一页开头匹配到了新文书的标题
            if clean_name in cleaned[:150]:
                if current_doc:
                    templates.append({
                        "name": current_doc,
                        "template": "\n".join(current_text_lines).strip()
                    })
                current_doc = doc_name
                current_text_lines = [cleaned]
                found_new = True
                break
        
        if not found_new:
            if current_doc:
                current_text_lines.append(cleaned)
            else:
                current_doc = catalog[0]
                current_text_lines = [cleaned]
                
    if current_doc:
        templates.append({
            "name": current_doc,
            "template": "\n".join(current_text_lines).strip()
        })
        
    return templates

if __name__ == "__main__":
    complaints = process_complaints()
    penalty = process_penalty()
    
    data = [
        {
            "name": "市场监督管理投诉举报文书式样",
            "tables": complaints
        },
        {
            "name": "市场监督管理行政处罚文书范本",
            "tables": penalty
        }
    ]
    
    # 创建后端 local_data 目录并持久化 JSON
    output_dir = "/app/backend/local_data"
    os.makedirs(output_dir, exist_ok=True)
    output_json_path = os.path.join(output_dir, "ai_templates.json")
    
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully generated ai_templates.json with {len(complaints)} complaints forms and {len(penalty)} penalty forms.")
