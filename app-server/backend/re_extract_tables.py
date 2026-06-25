import json
import re
import os
import fitz
from pathlib import Path

# 投诉登记表高精度精修 HTML 模版
COMPLAINT_HTML = """<h1>投 诉 登 记 表</h1>
<table noborder="true" style="width: 100%; margin-bottom: 8px; font-size: 14px;">
  <tbody>
    <tr>
      <td noborder="true" style="text-align: left; background: transparent; border: none; padding: 0;">登记单位：________________________________</td>
      <td noborder="true" style="text-align: right; background: transparent; border: none; padding: 0;">编号：________________________________</td>
    </tr>
  </tbody>
</table>
<table border="1" style="width: 100%; border-collapse: collapse; border: 2px solid #000000; table-layout: fixed; font-size: 14px; text-align: center;">
  <colgroup>
    <col style="width: 10%;" />
    <col style="width: 15%;" />
    <col style="width: 25%;" />
    <col style="width: 15%;" />
    <col style="width: 17.5%;" />
    <col style="width: 17.5%;" />
  </colgroup>
  <tbody>
    <tr style="height: 40px;">
      <td rowspan="4" style="font-weight: bold; border: 1px solid #000000; padding: 8px; writing-mode: vertical-rl; text-orientation: upright; letter-spacing: 4px;">投诉人</td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">姓名</td>
      <td style="border: 1px solid #000000; padding: 8px;"></td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系电话</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="2"></td>
    </tr>
    <tr style="height: 40px;">
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">证件类型</td>
      <td style="border: 1px solid #000000; padding: 8px;"></td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">证件号码</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="2"></td>
    </tr>
    <tr style="height: 40px;">
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系地址</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="4"></td>
    </tr>
    <tr style="height: 40px;">
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">是否同意公示投诉信息</td>
      <td style="border: 1px solid #000000; padding: 8px;">□是&nbsp;&nbsp;&nbsp;&nbsp;□否</td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">是否同意委托调解</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="2">□是&nbsp;&nbsp;&nbsp;&nbsp;□否</td>
    </tr>
    <tr style="height: 40px;">
      <td rowspan="2" style="font-weight: bold; border: 1px solid #000000; padding: 8px; writing-mode: vertical-rl; text-orientation: upright; letter-spacing: 4px;">被投诉人</td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">名称（姓名）</td>
      <td style="border: 1px solid #000000; padding: 8px;"></td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系人</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="2"></td>
    </tr>
    <tr style="height: 40px;">
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">地址</td>
      <td style="border: 1px solid #000000; padding: 8px;"></td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系电话</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="2"></td>
    </tr>
    <tr style="height: 180px;">
      <td style="font-weight: bold; border: 1px solid #000000; padding: 12px; writing-mode: vertical-rl; text-orientation: upright; line-height: 1.5; letter-spacing: 2px;">消费者权益争议事实依据</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="5"></td>
    </tr>
    <tr style="height: 140px;">
      <td style="font-weight: bold; border: 1px solid #000000; padding: 12px; writing-mode: vertical-rl; text-orientation: upright; line-height: 1.5; letter-spacing: 2px;">投诉请求</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="5"></td>
    </tr>
    <tr style="height: 80px;">
      <td style="border: 1px solid #000000; padding: 12px; text-align: left; vertical-align: bottom;" colspan="3">
        投诉人（签字）：<br/><br/>
        <div style="text-align: right; padding-right: 20px;">年&nbsp;&nbsp;&nbsp;&nbsp;月&nbsp;&nbsp;&nbsp;&nbsp;日</div>
      </td>
      <td style="border: 1px solid #000000; padding: 12px; text-align: left; vertical-align: bottom;" colspan="3">
        经办人（签字）：<br/><br/>
        <div style="text-align: right; padding-right: 20px;">年&nbsp;&nbsp;&nbsp;&nbsp;月&nbsp;&nbsp;&nbsp;&nbsp;日</div>
      </td>
    </tr>
  </tbody>
</table>
<div style="margin-top: 12px; font-size: 12px; line-height: 1.6; text-align: left;">
  <div>注：1. 本表格适用于市场监督管理部门对消费者通过电话、信函、上门等方式提起投诉 of 消费者权益争议的登记。</div>
  <div>&nbsp;&nbsp;&nbsp;&nbsp;2. 消费者通过非现场方式提起投诉的，无须在投诉人一栏签字。</div>
  <div>&nbsp;&nbsp;&nbsp;&nbsp;3. 消费者权益争议事实依据应当包括：消费者购买、使用商品或者接受服务的时间、地点、内容、涉及金额、消费者权益争议情况等具体事实及相应证明材料。</div>
  <div>&nbsp;&nbsp;&nbsp;&nbsp;4. 投诉请求应当包括：消费者主张修理、重作、更换、退货、补足商品数量、退还货款和服务费用、赔偿损失等具体请求。</div>
</div>"""

# 举报登记表高精度精修 HTML 模版
REPORT_HTML = """<h1>举 报 登 记 表</h1>
<table noborder="true" style="width: 100%; margin-bottom: 8px; font-size: 14px;">
  <tbody>
    <tr>
      <td noborder="true" style="text-align: left; background: transparent; border: none; padding: 0;">登记单位：________________________________</td>
      <td noborder="true" style="text-align: right; background: transparent; border: none; padding: 0;">编号：________________________________</td>
    </tr>
  </tbody>
</table>
<table border="1" style="width: 100%; border-collapse: collapse; border: 2px solid #000000; table-layout: fixed; font-size: 14px; text-align: center;">
  <colgroup>
    <col style="width: 10%;" />
    <col style="width: 15%;" />
    <col style="width: 25%;" />
    <col style="width: 15%;" />
    <col style="width: 17.5%;" />
    <col style="width: 17.5%;" />
  </colgroup>
  <tbody>
    <tr style="height: 40px;">
      <td rowspan="2" style="font-weight: bold; border: 1px solid #000000; padding: 8px; writing-mode: vertical-rl; text-orientation: upright; letter-spacing: 4px;">举报人</td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">姓名</td>
      <td style="border: 1px solid #000000; padding: 8px;"></td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系电话</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="2"></td>
    </tr>
    <tr style="height: 40px;">
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系地址</td>
      <td style="border: 1px solid #000000; padding: 8px;"></td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">身份证件号码</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="2"></td>
    </tr>
    <tr style="height: 40px;">
      <td rowspan="2" style="font-weight: bold; border: 1px solid #000000; padding: 8px; writing-mode: vertical-rl; text-orientation: upright; letter-spacing: 4px;">被举报人</td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">名称（姓名）</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="4"></td>
    </tr>
    <tr style="height: 40px;">
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">地址</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="4"></td>
    </tr>
    <tr style="height: 200px;">
      <td style="font-weight: bold; border: 1px solid #000000; padding: 12px; writing-mode: vertical-rl; text-orientation: upright; line-height: 1.5; letter-spacing: 2px;">涉嫌违反市场监督管理法律、法规、规章的具体线索 and 相应的事实依据</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="5"></td>
    </tr>
    <tr style="height: 80px;">
      <td style="border: 1px solid #000000; padding: 12px; text-align: left; vertical-align: bottom;" colspan="3">
        举报人（签字）：<br/><br/>
        <div style="text-align: right; padding-right: 20px;">年&nbsp;&nbsp;&nbsp;&nbsp;月&nbsp;&nbsp;&nbsp;&nbsp;日</div>
      </td>
      <td style="border: 1px solid #000000; padding: 12px; text-align: left; vertical-align: bottom;" colspan="3">
        经办人（签字）：<br/><br/>
        <div style="text-align: right; padding-right: 20px;">年&nbsp;&nbsp;&nbsp;&nbsp;月&nbsp;&nbsp;&nbsp;&nbsp;日</div>
      </td>
    </tr>
  </tbody>
</table>
<div style="margin-top: 12px; font-size: 12px; line-height: 1.6; text-align: left;">
  <div>注：1. 本表格适用于市场监督管理部门对举报人通过电话、信函、上门等方式提起举报的登记。</div>
  <div>&nbsp;&nbsp;&nbsp;&nbsp;2. 举报人可以匿名举报，但应当提供具体涉嫌违法线索和相应的事实依据，并对举报内容的真实性负责。举报人实名举报的，还应当提供真实的身份信息。</div>
  <div>&nbsp;&nbsp;&nbsp;&nbsp;3. 通过非现场方式提出举报的，无须在举报人一栏签字。</div>
</div>"""

def table_to_html(cells):
    if not cells: return ""
    R, C = len(cells), len(cells[0])
    visited = [[False]*C for _ in range(R)]
    html = ['<table border="1" style="width:100%; border-collapse:collapse; border: 1px solid #000000; font-size: 12px;">', '<tbody>']
    for r in range(R):
        html.append('  <tr>')
        for c in range(C):
            if visited[r][c]: continue
            val = cells[r][c]
            if val is None:
                html.append('    <td style="border:1px solid #000000; padding:6px;"></td>')
                visited[r][c] = True
                continue
            colspan = 1
            for cc in range(c + 1, C):
                if cells[r][cc] is None and not visited[r][cc]: colspan += 1
                else: break
            rowspan = 1
            for rr in range(r + 1, R):
                all_none = True
                for cc in range(c, c + colspan):
                    if cells[rr][cc] is not None or visited[rr][cc]:
                        all_none = False
                        break
                if all_none: rowspan += 1
                else: break
            for rr in range(r, r + rowspan):
                for cc in range(c, c + colspan): visited[rr][cc] = True
            span_str = ""
            if colspan > 1: span_str += f' colspan="{colspan}"'
            if rowspan > 1: span_str += f' rowspan="{rowspan}"'
            val_clean = str(val).replace('\n', '<br/>').strip() if val else ""
            html.append(f'    <td{span_str} style="border:1px solid #000000; padding:6px; min-height: 24px;">{val_clean}</td>')
        html.append('  </tr>')
    html.append('</tbody>\n</table>')
    return '\n'.join(html)

def clean_line_text(text):
    lines = text.split('\n')
    cleaned = []
    for l in lines:
        l_strip = l.strip()
        if not l_strip:
            continue
        if re.match(r'^—\s*\d+\s*—$', l_strip):
            continue
        if "文书式样" in l_strip and len(l_strip) < 15:
            continue
        cleaned.append(l_strip)
    res = []
    last_empty = False
    for line in cleaned:
        if line == '':
            if not last_empty:
                res.append(line); last_empty = True
        else: res.append(line); last_empty = False
    return '\n'.join(res)

def refine_doc_name(original_name, page_html):
    # 提取 h1, p 或者 td 中的中文词组，优先改写为真正的文书标题
    if "文书式样" in original_name or re.match(r'^\d+\.文书式样', original_name):
        lines = re.findall(r'<(?:p|td|h1)[^>]*>(.*?)</(?:p|td|h1)>', page_html)
        cleaned_lines = []
        for l in lines:
            text = re.sub(r'<[^>]*>', '', l).replace(" ", "").replace("\u3000", "").strip()
            if text:
                cleaned_lines.append(text)
        keywords = ["表", "书", "笔录", "清单", "单", "函", "封条", "公告", "范本"]
        for l in cleaned_lines[:6]:
            if "文书式样" in l or "市场监督" in l or len(l) < 2 or len(l) > 30:
                continue
            if any(k in l for k in keywords):
                index_part = original_name.split('.', 1)[0] if '.' in original_name else ""
                return f"{index_part}. {l}" if index_part else l
    return original_name
def extract_pdf_rich(pdf_path):
    doc = fitz.open(pdf_path)
    catalog = []
    catalog_found = False
    for page_idx in range(min(6, len(doc))):
        page_text = doc[page_idx].get_text()
        if "目录" in page_text or "目 录" in page_text:
            matches = re.findall(r'(?:^\d+|\n\d+)[\.、\s]+([^\n\d]+)', page_text)
            if matches:
                catalog = [m.strip().split("（")[0].split("(")[0].strip() for m in matches if len(m.strip()) > 2 and m.strip() not in ["目录", "总体说明"]]
                catalog_found = True
                break
    if not catalog_found:
        for page_idx in range(len(doc)):
            page_text = doc[page_idx].get_text()
            first_lines = [l.strip() for l in page_text.split("\n") if l.strip()]
            if first_lines and 2 < len(first_lines[0]) < 40:
                catalog.append(first_lines[0])
                
    catalog_with_index = [f"{i+1}.{name}" for i, name in enumerate(catalog)]
    tables = []
    current_doc = None
    current_pages = []
    
    def process_page_to_html(page):
        tab_list = page.find_tables()
        if tab_list.tables:
            tab = tab_list.tables[0]
            bbox = tab.bbox
            header_lines = []
            footer_lines = []
            for b in page.get_text("blocks"):
                bx0, by0, bx1, by1, btext, _, _ = b
                if by1 < bbox[1]: header_lines.append(btext.strip())
                elif by0 > bbox[3]: footer_lines.append(btext.strip())
            header_html = "".join(["<p>" + h.replace('\n', '<br/>') + "</p>" for h in header_lines if h.strip()])
            table_html = table_to_html(tab.extract())
            footer_html = "".join(["<p>" + f.replace('\n', '<br/>') + "</p>" for f in footer_lines if f.strip()])
            return f"{header_html}\n{table_html}\n{footer_html}"
        else:
            page_text = page.get_text()
            lines = clean_line_text(page_text).split('\n')
            return "".join([f"<p>{line}</p>" for line in lines if line.strip()])

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_text = page.get_text()
        found_new = False
        for doc_name in catalog_with_index:
            clean_name = doc_name.split('.', 1)[1] if '.' in doc_name else doc_name
            if clean_name in page_text[:150]:
                if current_doc:
                    full_template = "\n".join(current_pages).strip()
                    if "投诉登记表" in current_doc or "式样一" in current_doc: full_template = COMPLAINT_HTML
                    elif "举报登记表" in current_doc or "式样二" in current_doc: full_template = REPORT_HTML
                    refined_name = refine_doc_name(current_doc, full_template)
                    tables.append({"name": refined_name, "template": full_template})
                current_doc = doc_name
                current_pages = [process_page_to_html(page)]
                found_new = True
                break
        if not found_new:
            if current_doc: current_pages.append(process_page_to_html(page))
            elif catalog_with_index:
                current_doc = catalog_with_index[0]
                current_pages = [process_page_to_html(page)]
                
    if current_doc:
        full_template = "\n".join(current_pages).strip()
        if "投诉登记表" in current_doc or "式样一" in current_doc: full_template = COMPLAINT_HTML
        elif "举报登记表" in current_doc or "式样二" in current_doc: full_template = REPORT_HTML
        refined_name = refine_doc_name(current_doc, full_template)
        tables.append({"name": refined_name, "template": full_template})
        
    doc.close()
    return tables

def main():
    templates = []
    files_to_process = [
        ("《市场监督管理部门处理投诉举报文书式样》.pdf", "市场监督管理投诉举报文书式样"),
        ("市场监督管理行政处罚文书格式范本（2021年修订版）.pdf.pdf", "市场监督管理行政处罚文书范本")
    ]
    for filename, category_name in files_to_process:
        if os.path.exists(filename):
            print(f"Processing {filename}...")
            tables = extract_pdf_rich(filename)
            templates.append({"name": category_name, "tables": tables})
            print(f"Extracted {len(tables)} tables for {category_name}.")
            
    if templates:
        output_file = Path("local_data/ai_templates.json")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(templates, f, ensure_ascii=False, indent=2)
        print("Successfully updated ai_templates.json with rich HTML structures.")

if __name__ == "__main__":
    main()
