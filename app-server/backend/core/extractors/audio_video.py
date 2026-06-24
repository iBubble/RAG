import os
import subprocess
import tempfile
import logging
from pathlib import Path
import torch
from transformers import pipeline

logger = logging.getLogger(__name__)

# 全局共享的 ASR pipeline 实例
_asr_pipeline = None

def _get_asr_pipeline():
    """
    延迟加载并缓存 ASR Pipeline
    WHY: 在模块加载时直接初始化会导致不必要的显存和内存占用。
         延迟加载能保证只有当处理音视频文件时才初始化 Whisper 模型。
    """
    global _asr_pipeline
    if _asr_pipeline is None:
        try:
            # 自动选择最快的推理后端
            device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
            model_name = os.environ.get("ASR_MODEL", "openai/whisper-tiny")
            logger.info(f"正在初始化 Whisper 本地语音识别模型 ({model_name}, Device: {device})...")
            # 优先使用离线模式，避免每次加载连接 HuggingFace 官网校验版本导致外网握手挂起
            try:
                _asr_pipeline = pipeline(
                    "automatic-speech-recognition",
                    model=model_name,
                    device=device,
                    local_files_only=True
                )
            except Exception as _offline_e:
                logger.warning(f"本地 Whisper 离线加载失败，尝试在线获取: {_offline_e}")
                _asr_pipeline = pipeline(
                    "automatic-speech-recognition",
                    model=model_name,
                    device=device
                )
            logger.info("Whisper 模型初始化成功")
        except Exception as e:
            logger.error(f"初始化 Whisper 模型失败: {e}")
            raise e
    return _asr_pipeline


def _extract_audio_video(file_path: str) -> str:
    """
    视频（.mp4, .mov）及音频（.mp3, .wav）的多模态文本提取器。
    WHY: 音视频无法直接向量化。本提取器通过 ffmpeg 提取/重采样音频为标准 16kHz WAV，
         并利用本地 Whisper ASR 引擎转写为文本，作为检索语料入库。
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    
    # 1. 建立临时 wav 文件保存重采样音频
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        temp_wav = tmp.name

    try:
        logger.info(f"正在转换音视频格式并提取音轨: {path.name}")
        # ffmpeg 提取音频并重采样为 16kHz, 16-bit 单声道 WAV
        cmd = [
            "ffmpeg", "-y",
            "-i", file_path,
            "-vn",                  # 忽略视频轨道
            "-acodec", "pcm_s16le", # 16-bit 线性 PCM
            "-ar", "16000",          # 16kHz 采样率 (ASR 最佳采样率)
            "-ac", "1",              # 单声道
            temp_wav
        ]
        
        # 执行 ffmpeg 转换，屏蔽子进程的标准输出以保持控制台整洁
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg 转换失败: {result.stderr}")
            
        logger.info(f"音轨转换提取成功，正在执行 ASR 转写: {path.name}")
        
        # 2. 调用 ASR 语音识别
        asr = _get_asr_pipeline()
        # 优化点：使用 torch.inference_mode() 避免计算和追踪梯度，以降低显存占用并提升推理响应速度
        with torch.inference_mode():
            # 增加 chunk_length_s=30 以启用长音频的滑动窗口转写，并通过 generate_kwargs 指定中文，避免错认成英文或输出空白/标点符号
            asr_res = asr(temp_wav, chunk_length_s=30, generate_kwargs={"language": "chinese"})
        transcription = asr_res.get("text", "").strip()
        
        if not transcription:
            logger.warning(f"语音识别结果为空: {path.name}")
            return f"[{suffix[1:].upper()} 媒体文件] {path.name}\n内容摘要：该音视频未识别到有效的人声对话文字。"
            
        logger.info(f"语音转写成功 ({path.name})，共 {len(transcription)} 字符")
        return f"[{suffix[1:].upper()} 媒体转写文本] {path.name}\n语音内容如下：\n{transcription}"

    except Exception as e:
        logger.error(f"解析音视频文件失败 ({path.name}): {e}")
        return f"[{suffix[1:].upper()} 媒体解析失败] {path.name}\n错误原因：{str(e)}"
        
    finally:
        # 清理临时 wav 文件
        try:
            if os.path.exists(temp_wav):
                os.unlink(temp_wav)
        except OSError:
            pass
