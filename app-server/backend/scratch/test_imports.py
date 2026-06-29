import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("1. 尝试导入 plain...", flush=True)
from core.extractors.plain import _extract_txt
print("-> OK", flush=True)

print("2. 尝试导入 pdf...", flush=True)
from core.extractors.pdf import _extract_pdf
print("-> OK", flush=True)

print("3. 尝试导入 pdf_parser...", flush=True)
from core.extractors.pdf_parser import _extract_pdf_smart
print("-> OK", flush=True)

print("4. 尝试导入 office...", flush=True)
from core.extractors.office import _extract_unstructured
print("-> OK", flush=True)

print("5. 尝试导入 image...", flush=True)
from core.extractors.image import _extract_image
print("-> OK", flush=True)

print("6. 尝试导入 caj...", flush=True)
from core.extractors.caj import _extract_caj
print("-> OK", flush=True)

print("7. 尝试导入 gis...", flush=True)
from core.extractors.gis import _extract_shp
print("-> OK", flush=True)

print("8. 尝试导入 audio_video...", flush=True)
from core.extractors.audio_video import _extract_audio_video
print("-> OK", flush=True)

print("9. 尝试导入 docling_parser...", flush=True)
from core.extractors.docling_parser import extract_with_docling
print("-> OK", flush=True)

print("所有子模块导入测试完毕！", flush=True)
