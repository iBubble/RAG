import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import sys
import types

# 欺骗 Python，使 core.extractors 成为一个包，但跳过执行其 __init__.py
package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + '/core/extractors'
mock_package = types.ModuleType('core.extractors')
mock_package.__path__ = [package_dir]
sys.modules['core.extractors'] = mock_package

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("-> 开始隔离测试 core/extractors/ 子模块导入...", flush=True)

print("1. 导入 core.extractors.plain", flush=True)
import core.extractors.plain
print("-> OK", flush=True)

print("2. 导入 core.extractors.pdf", flush=True)
import core.extractors.pdf
print("-> OK", flush=True)

print("3. 导入 core.extractors.pdf_parser", flush=True)
import core.extractors.pdf_parser
print("-> OK", flush=True)

print("4. 导入 core.extractors.office", flush=True)
import core.extractors.office
print("-> OK", flush=True)

print("5. 导入 core.extractors.image", flush=True)
import core.extractors.image
print("-> OK", flush=True)

print("6. 导入 core.extractors.caj", flush=True)
import core.extractors.caj
print("-> OK", flush=True)

print("7. 导入 core.extractors.gis", flush=True)
import core.extractors.gis
print("-> OK", flush=True)

print("8. 导入 core.extractors.audio_video", flush=True)
import core.extractors.audio_video
print("-> OK", flush=True)

print("9. 导入 core.extractors.docling_parser", flush=True)
import core.extractors.docling_parser
print("-> OK", flush=True)

print("🎉 所有隔离子模块导入全部成功！", flush=True)
