"""
大模型与多模态视觉引擎配置管理仓
WHY: 集中管理主力大模型服务商与视觉识别模型的持久化配置，
     支持多服务商配置独立切换回填，支持 OpenAI-compatible 与 Ollama 双模协议自适应。
"""
import json
import logging
import time
import httpx
from typing import Dict, Any, Tuple
from core.database import get_db

logger = logging.getLogger(__name__)

DEFAULT_PROVIDERS = {
    "DeepSeek-R1 (离线规则研判内置引擎)": {
        "baseURL": "https://deepseek-api2.pages.dev/v1",
        "apiKey": "EMPTY",
        "model": "deepseek-r1",
        "timeoutSeconds": 300,
    },
    "通用 兼容 Gateway": {
        "baseURL": "http://40dd.shop:8001/v1",
        "apiKey": "EMPTY",
        "model": "qwen38-27b-q4",
        "timeoutSeconds": 300,
    },
    "Ollama 本地私有化部署": {
        "baseURL": "http://host.docker.internal:11434",
        "apiKey": "",
        "model": "qwen3.8:27b-q4",
        "timeoutSeconds": 180,
    },
}

DEFAULT_VISION_PROVIDERS = {
    "通用 兼容 Gateway": {
        "baseURL": "http://40dd.shop:8000/v1",
        "apiKey": "EMPTY",
        "model": "qwen3-vl-32b-awq",
        "timeoutSeconds": 300,
    },
    "Ollama 本地私有化部署": {
        "baseURL": "http://host.docker.internal:11434",
        "apiKey": "",
        "model": "qwen2.5vl:7b",
        "timeoutSeconds": 180,
    },
}

DEFAULT_VISION_CONFIG = {
    "mode": "standalone",  # "same_as_main" | "standalone"
    "active_provider": "通用 兼容 Gateway",
    "providers": DEFAULT_VISION_PROVIDERS.copy(),
    "provider": "通用 兼容 Gateway",
    "baseURL": "http://40dd.shop:8000/v1",
    "apiKey": "EMPTY",
    "model": "qwen3-vl-32b-awq",
    "timeoutSeconds": 300,
}

def get_llm_providers_data() -> Dict[str, Any]:
    """获取所有大模型服务商配置及当前激活的服务商"""
    with get_db() as conn:
        row = conn.execute("SELECT value FROM system_settings WHERE key = 'llm_providers_config'").fetchone()
        if row and row[0]:
            try:
                data = json.loads(row[0])
                if "providers" not in data:
                    data["providers"] = DEFAULT_PROVIDERS.copy()
                if "active_provider" not in data:
                    data["active_provider"] = "通用 兼容 Gateway"
                return data
            except Exception as e:
                logger.error(f"解析 llm_providers_config 失败: {e}")
    return {
        "active_provider": "通用 兼容 Gateway",
        "providers": DEFAULT_PROVIDERS.copy(),
    }

def save_llm_providers_data(active_provider: str, providers: Dict[str, Any]):
    """持久化保存大模型服务商配置"""
    payload = {
        "active_provider": active_provider,
        "providers": providers,
    }
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
            ("llm_providers_config", json.dumps(payload, ensure_ascii=False)),
        )

def get_vision_llm_data() -> Dict[str, Any]:
    """获取视觉多模态大模型配置"""
    with get_db() as conn:
        row = conn.execute("SELECT value FROM system_settings WHERE key = 'vision_llm_config'").fetchone()
        if row and row[0]:
            try:
                data = json.loads(row[0])
                if "providers" not in data or not data["providers"]:
                    data["providers"] = DEFAULT_VISION_PROVIDERS.copy()
                if "active_provider" not in data:
                    data["active_provider"] = data.get("provider", "通用 兼容 Gateway")
                return data
            except Exception as e:
                logger.error(f"解析 vision_llm_config 失败: {e}")
    return DEFAULT_VISION_CONFIG.copy()

def save_vision_llm_data(config: Dict[str, Any]):
    """持久化保存视觉多模态大模型配置"""
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
            ("vision_llm_config", json.dumps(config, ensure_ascii=False)),
        )

def get_active_llm_config() -> Dict[str, Any]:
    """获取当前生效的主力大模型配置"""
    data = get_llm_providers_data()
    active_name = data.get("active_provider", "通用 兼容 Gateway")
    providers = data.get("providers", {})
    cfg = providers.get(active_name, DEFAULT_PROVIDERS.get(active_name, {}))
    return {
        "provider": active_name,
        "baseURL": cfg.get("baseURL", "http://host.docker.internal:11434"),
        "apiKey": cfg.get("apiKey", ""),
        "model": cfg.get("model", "qwen3.8:27b-q4"),
        "timeoutSeconds": int(cfg.get("timeoutSeconds", 300)),
    }

def get_active_vision_config() -> Dict[str, Any]:
    """获取当前生效的视觉多模态大模型配置"""
    vision_data = get_vision_llm_data()
    if vision_data.get("mode") == "same_as_main":
        main_cfg = get_active_llm_config()
        return {
            "mode": "same_as_main",
            "provider": main_cfg["provider"],
            "baseURL": main_cfg["baseURL"],
            "apiKey": main_cfg["apiKey"],
            "model": main_cfg["model"],
            "timeoutSeconds": main_cfg["timeoutSeconds"],
        }
    active_name = vision_data.get("active_provider", vision_data.get("provider", "通用 兼容 Gateway"))
    providers = vision_data.get("providers", {})
    cfg = providers.get(active_name, {})
    if not cfg:
        cfg = {
            "baseURL": vision_data.get("baseURL", "http://40dd.shop:8000/v1"),
            "apiKey": vision_data.get("apiKey", ""),
            "model": vision_data.get("model", "qwen3-vl-32b-awq"),
            "timeoutSeconds": int(vision_data.get("timeoutSeconds", 300)),
        }
    return {
        "mode": "standalone",
        "provider": active_name,
        "baseURL": cfg.get("baseURL", "http://40dd.shop:8000/v1"),
        "apiKey": cfg.get("apiKey", ""),
        "model": cfg.get("model", "qwen3-vl-32b-awq"),
        "timeoutSeconds": int(cfg.get("timeoutSeconds", 300)),
    }

def normalize_endpoint(base_url: str, is_openai_chat: bool = True) -> str:
    """归一化服务端点 URL"""
    url = base_url.strip().rstrip("/")
    if is_openai_chat:
        if url.endswith("/chat/completions"):
            return url
        elif url.endswith("/v1"):
            return f"{url}/chat/completions"
        else:
            return f"{url}/v1/chat/completions"
    return url

async def test_llm_connection(base_url: str, api_key: str, model: str, is_vision: bool = False) -> Tuple[bool, str, float]:
    """
    轻量探活测试 Gateway 或本地模型的连通性与时延。
    返回: (是否成功, 诊断信息, 响应耗时秒数)
    """
    start_time = time.time()
    headers = {"Content-Type": "application/json"}
    clean_key = (api_key or "").strip()
    if clean_key and clean_key.upper() != "EMPTY":
        headers["Authorization"] = f"Bearer {clean_key}"

    # 判断是否为 Ollama 本地端点
    is_ollama = "11434" in base_url or "/api/" in base_url

    try:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            if is_ollama:
                # Ollama 探活：调用 /api/tags 或 /api/generate
                tag_url = f"{base_url.rstrip('/')}/api/tags"
                r = await client.get(tag_url)
                elapsed = time.time() - start_time
                if r.status_code == 200:
                    return True, f"Ollama 连通正常，共检测到 {len(r.json().get('models', []))} 个本地模型", elapsed
                return False, f"Ollama 响应异常 (HTTP {r.status_code})", elapsed
            else:
                # OpenAI 兼容 Gateway 探活：优先以极轻量的 /models 端点进行毫秒级嗅探（零占用 GPU 排队）
                clean_url = base_url.strip().rstrip("/")
                for suffix in ["/chat/completions", "/completions"]:
                    if clean_url.endswith(suffix):
                        clean_url = clean_url[:-len(suffix)]
                
                models_url = f"{clean_url}/models" if "/v1" in clean_url else f"{clean_url}/v1/models"
                try:
                    r_models = await client.get(models_url, headers=headers)
                    elapsed = time.time() - start_time
                    if r_models.status_code == 200:
                        return True, "Gateway 连通正常 (API端点响应健康)", elapsed
                except Exception:
                    pass

                # 若 /models 接口受限，平滑降级为发送 1 token 极简探测
                chat_url = normalize_endpoint(base_url, is_openai_chat=True)
                test_prompt = "Hi"
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": test_prompt}],
                    "max_tokens": 1,
                    "stream": False,
                }
                r = await client.post(chat_url, json=payload, headers=headers)
                elapsed = time.time() - start_time
                if r.status_code == 200:
                    return True, "Gateway 连通正常，模型响应成功", elapsed
                else:
                    err_msg = r.text[:120]
                    return False, f"HTTP {r.status_code}: {err_msg}", elapsed
    except httpx.TimeoutException:
        return False, "连接超时 (10秒未响应)", time.time() - start_time
    except Exception as e:
        return False, f"连接失败: {str(e)}", time.time() - start_time


async def fetch_remote_models(base_url: str, api_key: str = "") -> Tuple[bool, list[str], str]:
    """
    自适应请求远程端点（OpenAI /models 或 Ollama /api/tags），获取可用模型名称列表。
    返回: (是否成功, 模型名称列表, 消息提示)
    """
    clean_url = (base_url or "").strip().rstrip("/")
    if not clean_url:
        return False, [], "服务端点 URL 不能为空"

    # 清理掉 chat/completions 等后缀
    for suffix in ["/chat/completions", "/completions"]:
        if clean_url.endswith(suffix):
            clean_url = clean_url[:-len(suffix)]

    headers = {"Content-Type": "application/json"}
    clean_key = (api_key or "").strip()
    if clean_key and clean_key.upper() != "EMPTY":
        headers["Authorization"] = f"Bearer {clean_key}"

    # 尝试探测的端点候选列表
    endpoints_to_try = []
    if "/v1" in clean_url:
        endpoints_to_try.append(f"{clean_url}/models")
    else:
        endpoints_to_try.append(f"{clean_url}/v1/models")
        endpoints_to_try.append(f"{clean_url}/api/tags")
        endpoints_to_try.append(f"{clean_url}/models")

    # 如果本身是 11434 端口的 Ollama，优先放 /api/tags
    if "11434" in clean_url:
        endpoints_to_try = [f"{clean_url}/api/tags", f"{clean_url}/v1/models"]

    models: list[str] = []
    last_err = ""

    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        for ep in endpoints_to_try:
            try:
                r = await client.get(ep, headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    # 1. 尝试 OpenAI 标准格式: {"data": [{"id": "model_name"}, ...]}
                    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                        for item in data["data"]:
                            if isinstance(item, dict) and item.get("id"):
                                models.append(str(item["id"]))
                    # 2. 尝试 Ollama / llama.cpp 格式: {"models": [{"name": "model_name"}, ...]}
                    if not models and isinstance(data, dict) and "models" in data and isinstance(data["models"], list):
                        for item in data["models"]:
                            if isinstance(item, dict):
                                m_name = item.get("name") or item.get("model")
                                if m_name:
                                    models.append(str(m_name))

                    if models:
                        # 去重并保持顺序
                        seen = set()
                        deduped = [m for m in models if not (m in seen or seen.add(m))]
                        return True, deduped, f"成功拉取到 {len(deduped)} 个可用模型"
                else:
                    last_err = f"HTTP {r.status_code}: {r.text[:80]}"
            except Exception as e:
                last_err = str(e)
                continue

    return False, [], f"未能从远端端点解析到模型列表: {last_err or '连接失败或端点不支持 /models'}"

