import re

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
    return cleaned

def parse_header_title_docno(raw_lines):
    title_idx = -1
    for idx, line in enumerate(raw_lines[:6]):
        if any(keyword in line for keyword in ["书", "函", "表", "公告", "笔录", "清单", "单", "回证"]):
            if len(line) < 30:
                title_idx = idx
                break
    
    header_lines = []
    title_line = ""
    start_idx = 0
    
    if title_idx != -1:
        title_line = raw_lines[title_idx]
        header_lines = raw_lines[:title_idx]
        start_idx = title_idx + 1
    else:
        title_line = raw_lines[0]
        start_idx = 1
        
    doc_no = ""
    body_lines = []
    
    i = start_idx
    n = len(raw_lines)
    while i < n:
        line = raw_lines[i]
        if "〔" in line or "第" in line or "字〔" in line:
            combined = line
            if i + 1 < n and ("〕" in raw_lines[i+1] or "号" in raw_lines[i+1]):
                combined += raw_lines[i+1]
                i += 1
                if i + 1 < n and "号" in raw_lines[i+1]:
                    combined += raw_lines[i+1]
                    i += 1
            combined = re.sub(r'〔\s*〕', '〔&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;〕', combined)
            combined = re.sub(r'〔\s*', '〔&nbsp;&nbsp;&nbsp;&nbsp;', combined)
            combined = re.sub(r'\s*〕', '&nbsp;&nbsp;&nbsp;&nbsp;〕', combined)
            doc_no = combined
        else:
            body_lines.append(line)
        i += 1
    return header_lines, title_line, doc_no, body_lines

def parse_body_paragraphs(body_lines):
    final_body_paragraphs = []
    sign_lines = []
    footer_lines = []
    is_footer = False
    
    for line in body_lines:
        if any(k in line for k in ["印章", "市场监督管理局", "（印章）"]):
            sign_lines.append(line)
            continue
        if re.match(r'^(?:年|月|日|\d{4}年|\d{1,2}月|\d{1,2}日|\s*年\s*月\s*日\s*)$', line) or (len(line) < 15 and all(k in line for k in ["年", "月", "日"])):
            sign_lines.append(line)
            continue
            
        if "本文书一式" in line or "一份送达" in line or "一份归档" in line or line.startswith("注："):
            is_footer = True
            footer_lines.append(line)
            continue
            
        if is_footer:
            footer_lines.append(line)
        else:
            final_body_paragraphs.append(line)
            
    # 智能合并段落
    merged_paragraphs = []
    temp_paragraph = ""
    for idx, line in enumerate(final_body_paragraphs):
        if line.endswith("：") and len(line) < 18:
            if temp_paragraph:
                merged_paragraphs.append(temp_paragraph)
                temp_paragraph = ""
            merged_paragraphs.append(f"<strong>{line.rstrip('：')}</strong>")
            continue
            
        if any(line.startswith(k) for k in ["联系人：", "联系电话：", "联系地址：", "附件：", "附："]):
            if temp_paragraph:
                merged_paragraphs.append(temp_paragraph)
                temp_paragraph = ""
            line_clean = line.rstrip("：")
            merged_paragraphs.append(f"{line_clean}：________________________________")
            continue

        if not temp_paragraph:
            temp_paragraph = line
        else:
            prev_char = temp_paragraph.strip()[-1] if temp_paragraph.strip() else ""
            if prev_char not in ["。", "！", "？", "；"] or len(line) < 10:
                if prev_char in ["，", "、"] and line.startswith(prev_char):
                    temp_paragraph += line[1:]
                else:
                    temp_paragraph += line
            else:
                merged_paragraphs.append(temp_paragraph)
                temp_paragraph = line
                
    if temp_paragraph:
        merged_paragraphs.append(temp_paragraph)
    return merged_paragraphs, sign_lines, footer_lines

def format_document_to_html(page_text):
    raw_lines = clean_line_text(page_text)
    if not raw_lines:
        return ""
        
    header_lines, title_line, doc_no, body_lines = parse_header_title_docno(raw_lines)
    merged_paras, sign_lines, footer_lines = parse_body_paragraphs(body_lines)
    
    final_paras = []
    for p in merged_paras:
        if p.startswith("<strong>") and p.endswith("</strong>"):
            p_clean = re.sub(r'^[_\s]+', '________________', p.replace("<strong>", "").replace("</strong>", ""))
            final_paras.append(f'<p style="text-align: left; font-weight: bold; font-size: 14px; margin-bottom: 12px;">{p_clean}：</p>')
        elif any(p.startswith(k) for k in ["联系人：", "联系电话：", "联系地址：", "附件：", "附："]):
            final_paras.append(f'<p style="text-align: left; text-indent: 0; line-height: 2; margin: 4px 0;">{p}</p>')
        else:
            p_formatted = re.sub(r'_{2,}', '________________', p)
            final_paras.append(f'<p style="text-indent: 2em; text-align: justify; line-height: 2; font-size: 14px; margin-bottom: 12px;">{p_formatted}</p>')
            
    html_parts = []
    if header_lines:
        html_parts.append(f'<p style="text-align: center; font-size: 16px; font-family: SimSun, serif; margin: 0; font-weight: bold;">{"".join(header_lines)}</p>')
    html_parts.append(f'<h1 style="text-align: center; font-size: 26px; font-family: SimHei, sans-serif; font-weight: bold; margin-top: 12px; margin-bottom: 16px;">{title_line}</h1>')
    
    if doc_no:
        html_parts.append(f'<p style="text-align: center; font-size: 14px; font-family: SimSun, serif; margin-bottom: 24px;">{doc_no}</p>')
        
    html_parts.extend(final_paras)
    
    if sign_lines:
        dept = ""
        date_parts = []
        for s in sign_lines:
            if "局" in s:
                dept = s
            elif any(k in s for k in ["年", "月", "日"]):
                date_parts.append(s)
        if not dept:
            dept = "市场监督管理局"
        if "印章" not in dept:
            dept += "（印章）"
            
        date_str = "".join(date_parts).strip()
        date_str = re.sub(r'\s+', '', date_str)
        if not date_str or len(date_str) < 3:
            date_str = "____年____月____日"
        else:
            date_str = date_str.replace("年", "年 ").replace("月", "月 ").strip()
            date_str = re.sub(r'年', '年&nbsp;&nbsp;&nbsp;&nbsp;', date_str)
            date_str = re.sub(r'月', '月&nbsp;&nbsp;&nbsp;&nbsp;', date_str)
            if date_str == "年月日":
                date_str = "____年____月____日"
                
        sign_table = f"""<table noborder="true" style="width: 100%; margin-top: 60px; background: transparent; border: none;">
  <tbody>
    <tr>
      <td noborder="true" style="width: 45%;"></td>
      <td noborder="true" style="width: 55%; text-align: right; background: transparent; border: none; font-size: 14px; font-family: SimSun, serif; padding: 0; line-height: 1.8;">
        {dept}<br/>
        {date_str}
      </td>
    </tr>
  </tbody>
</table>"""
        html_parts.append(sign_table)
        
    if footer_lines:
        footer_text = "".join(footer_lines).replace("注：", "").strip()
        footer_text = re.sub(r'_{2,}', '______', footer_text)
        html_parts.append('<hr style="border: none; border-top: 1px solid #000000; margin-top: 60px; margin-bottom: 12px;" />')
        html_parts.append(f'<div style="font-size: 12px; line-height: 1.6; text-align: left; font-family: SimSun, serif; color: #333333;">注：{footer_text}</div>')
        
    return "\n".join(html_parts)
