import logging
import json
from pydantic import BaseModel, ValidationError
from typing import Type, Dict, Any, Optional

logger = logging.getLogger(__name__)

def generate_constrained_json(
    prompt: str,
    response_model: Type[BaseModel],
    system_prompt: Optional[str] = None,
    max_retries: int = 3,
    model_name: str = "qwen3.6:35b-q4"
) -> BaseModel:
    """
    通过 Ollama 的 format 字段（支持 JSON Schema），
    实现 100% 确定性字段类型的结构化约束生成，并实现异常捕获自动纠错。
    """
    from core.config import settings
    import httpx

    # Pydantic v2 中使用 model_json_schema 提取模型的 JSON Schema
    schema_dict = response_model.model_json_schema()
    
    _ollama_url = settings.OLLAMA_BASE_URL
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    for attempt in range(max_retries):
        response_content = ""
        try:
            # 构造 Ollama 请求，传入 format 参数以约束生成为指定的 JSON Schema
            payload = {
                "model": model_name,
                "messages": messages,
                "format": schema_dict,  # Ollama 支持直接传入 JSON schema 限制输出格式
                "options": {
                    "temperature": 0.0,  # 设为 0 以保证生成的确定性
                },
                "stream": False
            }
            
            logger.info(f"发送 Ollama 约束解码请求，模型: {model_name}, 尝试次数: {attempt + 1}")
            res = httpx.post(f"{_ollama_url}/api/chat", json=payload, timeout=90.0)
            res.raise_for_status()
            
            res_json = res.json()
            response_content = res_json["message"]["content"]
            
            # 解析并实例化 Pydantic 模型进行校验
            parsed_data = json.loads(response_content)
            instance = response_model(**parsed_data)
            logger.info("✅ Pydantic 约束解码及 Schema 自主校验 100% 成功！")
            return instance
            
        except (httpx.HTTPError, json.JSONDecodeError, ValidationError) as e:
            logger.warning(f"约束解码或校验不匹配 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                logger.error(f"约束解码重试耗尽，最终失败: {e}")
                raise e
            
            # 将具体的 ValidationError Trace 拼接入提示词回传，实现自主纠错重试
            error_msg = (
                f"上一次生成的内容未通过 Pydantic 校验，错误信息为:\n{str(e)}\n"
                f"请分析错误，重新生成绝对符合 JSON Schema 定义的格式数据。"
            )
            messages.append({"role": "assistant", "content": response_content})
            messages.append({"role": "user", "content": error_msg})
