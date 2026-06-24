from typing import List


def _table_to_markdown(title: str, unit: str,
                       headers: List[str], rows: List[List[str]]) -> str:
    """将结构化表格渲染为完整的 Markdown 表格文本。"""
    
    def _clean_cell(cell_val: str) -> str:
        s = str(cell_val).replace("\n", "<br>")
        s = s.replace("|", "&#124;")  # 用实体编码替换管道符最安全
        return s
        
    lines = []
    if title:
        lines.append(f"**{title}**")
    if unit:
        lines.append(f"（{unit}）")
        
    clean_headers = [_clean_cell(h) for h in headers]
    lines.append("| " + " | ".join(clean_headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(clean_headers)) + " |")
    for row in rows:
        # 补齐列数，防止列数不一致
        padded = list(row) + [""] * max(0, len(clean_headers) - len(row))
        clean_row = [_clean_cell(c) for c in padded[:len(clean_headers)]]
        lines.append("| " + " | ".join(clean_row) + " |")
    return "\n".join(lines)

