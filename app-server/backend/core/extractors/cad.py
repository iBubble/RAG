import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def _extract_cad(file_path: str) -> str:
    """
    提取 CAD 图纸（DWG/DXF）中的注记文字。
    如果是 DWG，先用后端的 dwg2dxf 转换工具转成临时 DXF。
    """
    import ezdxf
    from ezdxf.recover import readfile
    import tempfile
    import subprocess
    import os

    path = Path(file_path)
    process_target = path
    temp_dir = None
    
    if path.suffix.lower() == ".dwg":
        tool_path = Path(__file__).parent.parent / "tools" / "dwg2dxf"
        if not tool_path.exists():
            logger.error("缺少 dwg2dxf 工具，无法解析 DWG 文本")
            return ""
            
        temp_dir = tempfile.TemporaryDirectory()
        temp_dxf = Path(temp_dir.name) / f"{path.stem}.dxf"
        
        cmd = [str(tool_path), "-o", str(temp_dxf), str(path)]
        env = os.environ.copy()
        env["DYLD_LIBRARY_PATH"] = str(tool_path.parent)
        
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if result.returncode != 0:
            logger.error(f"dwg2dxf 转换失败 ({path.name}): {result.stderr.strip()}")
            temp_dir.cleanup()
            return ""
            
        process_target = temp_dxf

    try:
        doc, auditor = readfile(str(process_target))
        msp = doc.modelspace()
        texts = []

        # 提取文本、尺寸标注和块属性
        for entity in msp.query('TEXT MTEXT DIMENSION INSERT'):
            try:
                etype = entity.dxftype()
                if etype in ('TEXT', 'MTEXT'):
                    text = entity.dxf.text
                    if text and str(text).strip():
                        texts.append(str(text).strip())
                elif etype == 'DIMENSION':
                    text = entity.dxf.get('text', '')
                    if not text and hasattr(entity.dxf, 'actual_measurement'):
                        text = str(round(entity.dxf.actual_measurement, 2))
                    if text and str(text).strip() and text != '<>':
                        texts.append(f"尺寸标注: {str(text).strip()}")
                elif etype == 'INSERT':
                    if entity.has_attribs:
                        for attrib in entity.attribs:
                            text = attrib.dxf.text
                            if text and str(text).strip():
                                texts.append(f"块属性: {str(text).strip()}")
            except Exception as e:
                logger.debug(f"CAD 实体提取异常: {e}")

        return "\n".join(texts)
    except Exception as e:
        logger.error(f"无法解析 CAD 文本 {file_path}: {e}")
        return ""
    finally:
        if temp_dir:
            temp_dir.cleanup()


