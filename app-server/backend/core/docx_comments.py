"""
docx_comments.py — AI 审阅批注注入器。

轻量化搬运自 Kimi docx_lib/editing/comments.py 核心逻辑，
仅依赖 Python 标准库（zipfile + re），零额外依赖。

WHY: python-docx 不原生支持写批注。
     采用"后处理注入"策略：先 doc.save()，再解压 → 注入 XML → 重新打包。
     使用字符串操作而非 ElementTree，避免破坏 python-docx 已声明的命名空间前缀。
"""
from __future__ import annotations

import os
import re
import zipfile
import tempfile
import random
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 常量 ──
AUTHOR = "AI审校"
INITIALS = "AI"
MAX_COMMENTS = 15

def _enable_track_revisions(settings_xml: str) -> str:
    """在 word/settings.xml 中注入 w:trackRevisions 以开启修订留痕模式。"""
    if "trackRevisions" in settings_xml:
        return settings_xml
    return settings_xml.replace("</w:settings>", "  <w:trackRevisions/>\n</w:settings>")

def _process_track_changes(doc_xml: str) -> tuple[str, int]:
    """
    扫描并替换 w:p 段落中的修订语法。
    支持格式: [修改前: xxx -> 修改后: yyy]
    """
    change_counter = 1000
    pattern_gt = re.compile(r"\[修改前:\s*(.*?)\s*-\&gt;\s*修改后:\s*(.*?)\s*\]")
    pattern_raw = re.compile(r"\[修改前:\s*(.*?)\s*->\s*修改后:\s*(.*?)\s*\]")

    def _repl(m: re.Match) -> str:
        nonlocal change_counter
        old_text = m.group(1)
        new_text = m.group(2)
        cid = str(change_counter)
        change_counter += 1
        now_str = _utc_now()
        
        return (
            f'</w:t></w:r>'
            f'<w:del w:id="{cid}" w:author="{AUTHOR}" w:date="{now_str}">'
            f'<w:r><w:delText>{old_text}</w:delText></w:r>'
            f'</w:del>'
            f'<w:ins w:id="{cid}" w:author="{AUTHOR}" w:date="{now_str}">'
            f'<w:r><w:t>{new_text}</w:t></w:r>'
            f'</w:ins>'
            f'<w:r><w:t>'
        )

    doc_xml = pattern_gt.sub(_repl, doc_xml)
    doc_xml = pattern_raw.sub(_repl, doc_xml)
    return doc_xml, change_counter - 1000

# ── 触发规则：(判断函数, 批注文字) ──
# WHY: 规则保持克制，只标注"明确有问题"的段落，避免批注过多干扰阅读。
_TRIGGERS: list[tuple] = [
    (
        lambda t: any(
            kw in t for kw in ["[待补充]", "[待核实]", "[待填写]", "[待补]"]
        ),
        "⚠️ 此处数据待补充，请人工核实后删除占位符",
    ),
    (
        lambda t: "[插入图件" in t,
        "🖼️ 请手工插入图件，完成后删除此占位段落",
    ),
]


def _new_para_id() -> str:
    """生成 8 位大写十六进制 paraId，符合 OOXML 规范。"""
    return f"{random.randint(1, 0x7FFFFFFE):08X}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _para_visible_text(para_xml: str) -> str:
    """从段落 XML 字符串中提取所有 w:t 可见文本。"""
    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", para_xml))


def _scan_and_inject(doc_xml: str) -> tuple[str, list[dict]]:
    """
    扫描 document.xml 所有段落，命中触发规则后注入批注锚点。
    返回 (修改后的 XML 字符串, 批注元数据列表)

    OOXML 批注锚点结构（插入在段落内）：
      <w:commentRangeStart w:id="N"/>
      ... 原有 runs ...
      <w:commentRangeEnd w:id="N"/>
      <w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>
           <w:commentReference w:id="N"/></w:r>
    """
    comments: list[dict] = []
    cid_counter = 0

    # WHY: w:p 不会在 Word 文档中嵌套，DOTALL 安全
    para_re = re.compile(r"(<w:p[ >].*?</w:p>)", re.DOTALL)

    def _process_para(m: re.Match) -> str:
        nonlocal cid_counter
        if len(comments) >= MAX_COMMENTS:
            return m.group(0)

        para_str = m.group(0)
        text = _para_visible_text(para_str)

        # 空段落不注释
        if not text.strip():
            return para_str

        for trigger_fn, comment_text in _TRIGGERS:
            if trigger_fn(text):
                cid = str(cid_counter)
                cid_counter += 1

                range_start = f'<w:commentRangeStart w:id="{cid}"/>'
                range_end = (
                    f'<w:commentRangeEnd w:id="{cid}"/>'
                    f'<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>'
                    f'<w:commentReference w:id="{cid}"/></w:r>'
                )

                # 在 <w:p...> 开标签结束后插入 rangeStart
                gt_pos = para_str.index(">") + 1
                modified = (
                    para_str[:gt_pos]
                    + range_start
                    + para_str[gt_pos : -len("</w:p>")]
                    + range_end
                    + "</w:p>"
                )

                comments.append(
                    {
                        "id": cid,
                        "text": comment_text,
                        "para_id": _new_para_id(),
                        "timestamp": _utc_now(),
                    }
                )
                logger.debug(f"批注[{cid}] 注入: {text[:40]!r}")
                return modified

        return para_str

    modified_xml = para_re.sub(_process_para, doc_xml)
    return modified_xml, comments


def _build_comments_xml(comments: list[dict]) -> str:
    """
    构建 word/comments.xml 文件内容。
    WHY: 使用最小命名空间声明，确保 WPS/Word 均可正常读取。
    """
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    W14 = "http://schemas.microsoft.com/office/word/2010/wordml"

    def _escape(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    items: list[str] = []
    for c in comments:
        text_id = _new_para_id()
        items.append(
            f'  <w:comment w:id="{c["id"]}" w:author="{AUTHOR}" '
            f'w:initials="{INITIALS}" w:date="{c["timestamp"]}">\n'
            f'    <w:p w14:paraId="{c["para_id"]}" w14:textId="{text_id}">\n'
            f'      <w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>'
            f"<w:annotationRef/></w:r>\n"
            f'      <w:r><w:t>{_escape(c["text"])}</w:t></w:r>\n'
            f"    </w:p>\n"
            f"  </w:comment>"
        )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<w:comments xmlns:w="{W}" xmlns:w14="{W14}">\n'
        + "\n".join(items)
        + "\n</w:comments>"
    )


def _update_rels(rels_str: str) -> str:
    """向 _rels/document.xml.rels 添加 comments.xml 关联（不重复添加）。"""
    if "comments.xml" in rels_str:
        return rels_str

    existing_ids = [int(n) for n in re.findall(r'Id="rId(\d+)"', rels_str)]
    next_id = max(existing_ids, default=0) + 1
    new_rel = (
        f'  <Relationship Id="rId{next_id}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" '
        'Target="comments.xml"/>\n'
    )
    return rels_str.replace("</Relationships>", new_rel + "</Relationships>")


def _update_content_types(ct_str: str) -> str:
    """向 [Content_Types].xml 添加 comments.xml 内容类型（不重复添加）。"""
    if "/word/comments.xml" in ct_str:
        return ct_str
    override = (
        '  <Override PartName="/word/comments.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument'
        '.wordprocessingml.comments+xml"/>\n'
    )
    return ct_str.replace("</Types>", override + "</Types>")


def inject_ai_comments(docx_path: str) -> int:
    """
    对已生成的 .docx 注入 AI 审阅批注（后处理注入）。

    返回实际注入的批注数量（0 表示无触发段落或注入失败）。
    WHY: 批注注入失败不应影响正常下载，所有异常均被捕获记录。
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            extract_dir = Path(tmpdir) / "extracted"

            # ── 解压 ──
            with zipfile.ZipFile(docx_path, "r") as zf:
                zf.extractall(extract_dir)

            # ── 开启修订留痕 ──
            settings_path = extract_dir / "word" / "settings.xml"
            if settings_path.exists():
                settings_xml = settings_path.read_text(encoding="utf-8")
                settings_path.write_text(_enable_track_revisions(settings_xml), encoding="utf-8")

            # ── 扫描并注入批注锚点 ──
            doc_path = extract_dir / "word" / "document.xml"
            doc_xml = doc_path.read_text(encoding="utf-8")
            modified_xml, comments = _scan_and_inject(doc_xml)

            # ── 扫描并替换修订留痕 ──
            modified_xml, changes_count = _process_track_changes(modified_xml)

            if not comments and changes_count == 0:
                logger.info("AI批注与修订: 无触发段落与修改，跳过注入")
                return 0

            # ── 写回 document.xml ──
            doc_path.write_text(modified_xml, encoding="utf-8")

            if comments:
                logger.info(f"AI批注: 注入 {len(comments)} 条")
                # ── 写 word/comments.xml ──
                (extract_dir / "word" / "comments.xml").write_text(
                    _build_comments_xml(comments), encoding="utf-8"
                )

                # ── 更新 _rels ──
                rels_path = extract_dir / "word" / "_rels" / "document.xml.rels"
                rels_path.write_text(
                    _update_rels(rels_path.read_text(encoding="utf-8")),
                    encoding="utf-8",
                )

                # ── 更新 [Content_Types].xml ──
                ct_path = extract_dir / "[Content_Types].xml"
                ct_path.write_text(
                    _update_content_types(ct_path.read_text(encoding="utf-8")),
                    encoding="utf-8",
                )

            # ── 重新打包 ──
            # WHY: 必须先写临时文件再重命名，避免写入过程中读取原文件
            tmp_out = Path(docx_path).with_suffix(".comments_tmp.docx")
            with zipfile.ZipFile(tmp_out, "w", zipfile.ZIP_DEFLATED) as zout:
                for fp in sorted(extract_dir.rglob("*")):
                    if fp.is_file():
                        zout.write(fp, fp.relative_to(extract_dir))

            os.replace(tmp_out, docx_path)
            return len(comments)

    except Exception as exc:
        logger.error(f"AI批注注入异常（已跳过）: {exc}", exc_info=True)
        return 0
