import json
import os
import re
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from core.auth_deps import get_current_user

router = APIRouter(prefix="/api/admin/ai-templates", tags=["AI Templates"])

TEMPLATE_FILE = Path(__file__).parent.parent / "local_data" / "ai_templates.json"

def load_templates():
    if not TEMPLATE_FILE.exists():
        return []
    try:
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_templates(data):
    TEMPLATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TEMPLATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

class UpdateTableRequest(BaseModel):
    categoryName: str
    tableName: str
    newTemplate: str

class AddTableRequest(BaseModel):
    categoryName: str
    tableName: str

class DeleteTableRequest(BaseModel):
    categoryName: str
    tableName: str

class DeleteCategoryRequest(BaseModel):
    categoryName: str

@router.post("/extract")
async def extract_templates(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="无权限：仅管理员可提取模板")

    filename = file.filename
    category_name = filename.rsplit(".", 1)[0]
    
    temp_path = Path(f"local_data/temp_{filename}")
    try:
        with open(temp_path, "wb") as f:
            f.write(await file.read())
            
        # 导入 re_extract_tables 里面的核心逻辑
        import sys
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if backend_dir not in sys.path:
            sys.path.append(backend_dir)
        from re_extract_tables import extract_pdf_rich
        
        tables = extract_pdf_rich(str(temp_path))
        
        templates_data = load_templates()
        existing_idx = -1
        for idx, cat in enumerate(templates_data):
            if cat.get("name") == category_name:
                existing_idx = idx
                break
                
        new_category = {
            "name": category_name,
            "tables": tables
        }
        
        if existing_idx != -1:
            templates_data[existing_idx] = new_category
        else:
            templates_data.append(new_category)
            
        save_templates(templates_data)
        return {"success": True, "categoryName": category_name, "tablesCount": len(tables)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF 模板提取失败: {str(e)}")
    finally:
        if temp_path.exists():
            temp_path.unlink()

@router.get("")
async def get_all_templates(user: dict = Depends(get_current_user)):
    return load_templates()

@router.put("/update-table")
async def update_table(req: UpdateTableRequest, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="无权限：仅管理员可编辑模板")
        
    data = load_templates()
    found = False
    for cat in data:
        if cat.get("name") == req.categoryName:
            for tbl in cat.get("tables", []):
                if tbl.get("name") == req.tableName:
                    tbl["template"] = req.newTemplate
                    found = True
                    break
            if found:
                break
                
    if not found:
        raise HTTPException(status_code=404, detail="未找到指定的分类或模板子表")
        
    save_templates(data)
    return {"success": True, "message": "模板更新成功"}

@router.post("/add-table")
async def add_table(req: AddTableRequest, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="无权限：仅管理员可新增模板")
        
    data = load_templates()
    found = False
    for cat in data:
        if cat.get("name") == req.categoryName:
            if any(tbl.get("name") == req.tableName for tbl in cat.get("tables", [])):
                raise HTTPException(status_code=400, detail="同名模板子表已存在")
            cat.setdefault("tables", []).append({
                "name": req.tableName,
                "template": f"【{req.tableName}】\n在此处输入表格的默认结构和样板文字..."
            })
            found = True
            break
            
    if not found:
        raise HTTPException(status_code=404, detail="未找到指定的模板分类")
        
    save_templates(data)
    return {"success": True, "message": "模板子表添加成功"}

@router.delete("/delete-table")
async def delete_table(req: DeleteTableRequest, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="无权限：仅管理员可删除模板")
        
    data = load_templates()
    found = False
    for cat in data:
        if cat.get("name") == req.categoryName:
            tables = cat.get("tables", [])
            new_tables = [tbl for tbl in tables if tbl.get("name") != req.tableName]
            if len(new_tables) < len(tables):
                cat["tables"] = new_tables
                found = True
            break
            
    if not found:
        raise HTTPException(status_code=404, detail="未找到指定的分类或模板子表")
        
    save_templates(data)
    return {"success": True, "message": "模板子表删除成功"}

@router.delete("/delete-category")
async def delete_category(req: DeleteCategoryRequest, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="无权限：仅管理员可删除大类")
        
    data = load_templates()
    new_data = [cat for cat in data if cat.get("name") != req.categoryName]
    if len(new_data) == len(data):
        raise HTTPException(status_code=404, detail="未找到指定的模板大类")
        
    save_templates(new_data)
    return {"success": True, "message": "大类分类删除成功"}
