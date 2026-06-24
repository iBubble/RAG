import re
import json

def markdown_to_docrequest_json(title: str, sections: list) -> str:
    req = {"title": title, "sections": []}
    
    for sec in sections:
        level = getattr(sec, "level", 1)
        sec_title = getattr(sec, "title", "Untitled Section")
        content = getattr(sec, "content", "")
        
        blocks = []
        if content:
            # Simple content parsing: split into paragraphs by double newline
            # Also extract Markdown tables if they start with |
            lines = content.split('\n')
            current_p = []
            
            in_table = False
            table_rows = []
            
            for line in lines:
                striped = line.strip()
                if striped.startswith("|"):
                    if not in_table:
                        # Flush paragraph
                        if current_p:
                            blocks.append({"type": "paragraph", "text": " ".join(current_p)})
                            current_p = []
                        in_table = True
                    # parsing row
                    row = [col.strip() for col in striped.strip("|").split("|")]
                    # skip markdown separation like |---|
                    if len(row) > 0 and all(all(c in "- :" for c in r) for r in row) and striped.count("-") >= 3:
                        continue
                    table_rows.append(row)
                elif striped.startswith("[可视化：") or striped.startswith("[可视化:"):
                    # chart match
                    if current_p:
                        blocks.append({"type": "paragraph", "text": " ".join(current_p)})
                        current_p = []
                    
                    chart_title = "Data Chart"
                    m = re.search(r'可视化[：:](.*?)\]', striped)
                    if m: chart_title = m.group(1).strip()
                    c_type = "pie" if "占比" in chart_title or "分布" in chart_title else "bar"
                    blocks.append({
                        "type": "chart", 
                        "chartType": c_type,
                        "chartTitle": chart_title
                    })
                else:
                    if in_table:
                        in_table = False
                        blocks.append({"type": "table", "rows": table_rows})
                        table_rows = []
                    
                    if striped == "":
                        if current_p:
                            blocks.append({"type": "paragraph", "text": " ".join(current_p)})
                            current_p = []
                    else:
                        current_p.append(striped)
            
            if current_p:
                blocks.append({"type": "paragraph", "text": " ".join(current_p)})
            if in_table and table_rows:
                blocks.append({"type": "table", "rows": table_rows})
        
        req["sections"].append({
            "title": sec_title,
            "level": level,
            "blocks": blocks
        })
        
    return json.dumps(req, ensure_ascii=False)
