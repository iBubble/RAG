import re
import uuid
import tempfile
import os
from typing import List, Dict, Any
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends
from docx import Document
from core.auth_deps import get_current_user
from core.heading_utils import determine_level_from_text

router = APIRouter(prefix="/api/template", tags=["模板大纲抽取"])

@router.post("/parse")
async def parse_template_outline(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """
    极具破坏力的反向抽取引擎：读取任意一份政府/企业发文样稿（.docx），
    强力提取内部的骨架（各级大纲），自动摈弃正文废料，生成一份纯粹的 Json 骨架协议给前端。
    """
    if file.content_type not in [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ]:
        raise HTTPException(status_code=400, detail="必须上传 .docx 类型的 Word 文档模板")

    temp_path = os.path.join(tempfile.gettempdir(), f"template_{uuid.uuid4().hex}.docx")
    try:
        with open(temp_path, "wb") as f:
            f.write(await file.read())
            
        doc = Document(temp_path)
        sections = []
        seen_titles = set()  # WHY: 用于去重，防止 TOC 条目和正文标题产生重复
        
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # WHY: 过滤 Word 目录（TOC）区域的段落。
            #       TOC 条目使用 "TOC 1"/"TOC 2"/... 样式，它们是文档目录区的自动生成条目。
            #       如果不排除，会导致每个标题出现两次（一次在目录区、一次在正文区）。
            style_name = para.style.name
            if style_name.startswith("TOC") or style_name.startswith("toc"):
                continue
                
            level = 0
            # WHY: 正则编号优先于 Word 样式，因为很多文档样式不规范（全用 Heading 1）
            # 1. 首先用文本编号推断层级（最可靠）
            level = determine_level_from_text(text)

            # 2. 编号无法识别时，回退到 docx 原生样式
            if level == 0:
                if style_name.startswith("Heading"):
                    try:
                        level = int(style_name.replace("Heading", "").strip())
                    except ValueError:
                        level = 1
                elif "标题" in style_name:
                    try:
                        level = int(re.search(r'\d+', style_name).group())
                    except AttributeError:
                        level = 1
                
            # 只要被拦截判定为标题大纲，压入结果集 （只认 1-4级 的核心骨架）
            if 1 <= level <= 4:
                # WHY: 清洗标题文本 — 去掉制表符和末尾页码（来自 TOC 残留匹配）
                clean_title = re.sub(r'\t+\d*$', '', text).strip()
                
                # WHY: 去重 — 如果清洗后的标题已经出现过，跳过（保留首次出现）
                dedup_key = re.sub(r'\s+', '', clean_title)  # 忽略空格差异
                if dedup_key in seen_titles:
                    continue
                seen_titles.add(dedup_key)
                
                sections.append({
                    "id": str(uuid.uuid4()),  # 赋予唯一临时追踪符，用于 React Key
                    "title": clean_title,
                    "level": level,
                    "content": ""  # 剥离它的正文部分，变为纯净容器，等待大模型回填
                })
                
        return {"filename": file.filename, "sections": sections}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"抽拔骨架失败: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
