"""
onnxruntime Import 阻断器。
WHY: 在 Mac Studio (Apple Silicon ARM64) 上，Docker 容器通过 Rosetta 2 / QEMU
     模拟 x86 环境。onnxruntime 的 C++ 底层在此模拟环境下加载偶发死锁或段错误
     （表现为 "onnxruntime cpuid_info warning: Unknown CPU vendor" 后 hang），
     导致整个进程无响应。
     我们的 RAG 管线完全基于 PyTorch 后端，无需 onnxruntime。
     此阻断器将 onnxruntime import 拦截为 ImportError，
     使 sentence_transformers 自动降级到纯 PyTorch 路径。

使用方法：在所有其他 import 之前导入本模块。
    import core.onnx_blocker  # noqa: F401
"""
import importlib.abc
import importlib.machinery
import sys


class _OnnxRuntimeBlocker(importlib.abc.MetaPathFinder):
    """拦截 onnxruntime 的 import，强制走 PyTorch 后端。

    WHY: 使用 importlib.abc.MetaPathFinder + find_spec() 替代已废弃的
         find_module() / load_module()（PEP 302），兼容 Python 3.12+。
    """
    _BLOCKED = ('onnxruntime', 'onnxruntime_extensions')

    def find_spec(self, fullname, path, target=None):
        if any(fullname == b or fullname.startswith(b + '.') for b in self._BLOCKED):
            # 返回一个 ModuleSpec，其 loader 会抛出 ImportError
            return importlib.machinery.ModuleSpec(fullname, _OnnxRuntimeLoader())
        return None


class _OnnxRuntimeLoader(importlib.abc.Loader):
    """配合 _OnnxRuntimeBlocker 使用的 Loader，始终抛出 ImportError。"""

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        raise ImportError(
            f'[ShengyaoRAG] {module.__name__} 已被阻断'
            f'（ARM/QEMU 环境不兼容，使用 PyTorch 后端替代）'
        )


# 模块导入时自动注册阻断器
sys.meta_path.insert(0, _OnnxRuntimeBlocker())
