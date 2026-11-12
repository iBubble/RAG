import os
import subprocess
import tempfile
import logging
from pathlib import Path

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
        import torch
        from transformers import pipeline
        try:
            # 自动选择最快的推理后端
            device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
            model_name = os.environ.get("ASR_MODEL", "openai/whisper-tiny")
            logger.info(f"正在初始化 Whisper 本地语音识别模型 ({model_name}, Device: {device})...")
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


_ALLOWED_FFMPEG_BINS = ("/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg")
_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv"}


def _resolve_ffmpeg_bin() -> str:
    """严格从硬编码白名单中解析可信 ffmpeg 二进制路径。"""
    for candidate in _ALLOWED_FFMPEG_BINS:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError("未找到受信任的 ffmpeg 可执行程序")


def _extract_video_keyframes_text(ffmpeg_bin: str, resolved_path: Path, max_frames: int = 3) -> str:
    """
    提取视频代表性关键帧并调用图像多模态引擎（Vision LLM / OCR）进行画面内容与文字识别。
    WHY: 手机现场拍摄的视频常常包含画面证据（如产品标签、招牌、现场环境）或无语音对白，
         补充关键帧视觉识别可确保无声/画面型视频同样完成高质量知识库入库分析。
    """
    from .image import _extract_image

    frame_texts: list[str] = []
    with tempfile.TemporaryDirectory(prefix="rag_vframes_") as frame_dir:
        frame_pattern = os.path.join(frame_dir, "frame_%02d.jpg")
        cmd = [
            ffmpeg_bin, "-y",
            "-i", str(resolved_path),
            "-vf", "fps=1/3,scale='min(1280,iw)':-2",
            "-frames:v", str(max_frames),
            "-q:v", "3",
            frame_pattern,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
        if res.returncode != 0:
            # 短视频不足 3 秒时回退提取首帧
            fallback_frame = os.path.join(frame_dir, "frame_01.jpg")
            subprocess.run(
                [ffmpeg_bin, "-y", "-i", str(resolved_path), "-frames:v", "1", "-q:v", "3", fallback_frame],
                capture_output=True, text=True, timeout=60, check=False,
            )

        frame_files = sorted(Path(frame_dir).glob("frame_*.jpg"))
        for idx, frame_file in enumerate(frame_files[:max_frames], start=1):
            try:
                desc = _extract_image(str(frame_file))
                if desc and desc.strip() and "未识别到文字内容" not in desc:
                    frame_texts.append(f"【关键帧 {idx} 画面/文字识别】\n{desc.strip()}")
            except Exception as fe:
                logger.warning(f"关键帧 {idx} 视觉提取失败 ({resolved_path.name}): {fe}")

    return "\n\n".join(frame_texts)


def _extract_audio_video(file_path: str) -> str:
    """
    视频（.mp4, .mov, .webm, .mkv）及音频（.mp3, .wav, .m4a, .aac, .ogg, .flac）的多模态文本提取器。
    WHY: 音视频无法直接向量化。本提取器通过 ffmpeg 提取/重采样音频为标准 16kHz WAV，
         利用本地 Whisper ASR 引擎转写语音，并对视频补充关键帧视觉/OCR 联合分析入库。
    """
    resolved_path = Path(file_path).resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError("待解析媒体文件不存在")

    suffix = resolved_path.suffix.lower()
    is_video = suffix in _VIDEO_SUFFIXES
    ffmpeg_bin = _resolve_ffmpeg_bin()

    # 1. 建立临时 wav 文件保存重采样音频
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        temp_wav = tmp.name

    transcription = ""
    visual_summary = ""
    audio_note = ""

    try:
        if is_video:
            try:
                logger.info(f"正在提取视频关键帧并进行视觉/OCR分析: {resolved_path.name}")
                visual_summary = _extract_video_keyframes_text(ffmpeg_bin, resolved_path)
            except Exception as ve:
                logger.warning(f"视频关键帧分析降级跳过 ({resolved_path.name}): {ve}")

        logger.info(f"正在转换音视频格式并提取音轨: {resolved_path.name}")
        # ffmpeg 提取音频并重采样为 16kHz, 16-bit 单声道 WAV
        cmd = [
            ffmpeg_bin, "-y",
            "-i", str(resolved_path),
            "-vn",                  # 忽略视频轨道
            "-acodec", "pcm_s16le", # 16-bit 线性 PCM
            "-ar", "16000",         # 16kHz 采样率 (ASR 最佳采样率)
            "-ac", "1",             # 单声道
            temp_wav,
        ]

        # 执行 ffmpeg 转换，屏蔽子进程的标准输出以保持控制台整洁
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
        if result.returncode == 0 and os.path.exists(temp_wav) and os.path.getsize(temp_wav) > 1024:
            logger.info(f"音轨转换提取成功，正在执行 ASR 转写: {resolved_path.name}")
            asr = _get_asr_pipeline()
            import torch
            # 优化点：使用 torch.inference_mode() 避免计算和追踪梯度，以降低显存占用并提升推理响应速度
            with torch.inference_mode():
                # 增加 chunk_length_s=30 以启用长音频的滑动窗口转写，并通过 generate_kwargs 指定中文，避免错认成英文或输出空白/标点符号
                asr_res = asr(temp_wav, chunk_length_s=30, generate_kwargs={"language": "chinese"})
            transcription = asr_res.get("text", "").strip()
        else:
            if "does not contain any stream" in (result.stderr or "") or "Output file is empty" in (result.stderr or ""):
                audio_note = "该视频不包含音轨（静音现场视频）。"
            elif not is_video:
                raise RuntimeError("音频轨道转换失败")
            else:
                audio_note = "未提取到有效音轨。"

        sections: list[str] = [f"[{suffix[1:].upper()} 多模态媒体分析报告] 文件：{resolved_path.name}"]
        if visual_summary:
            sections.append(f"## 画面视觉与文字识别分析\n{visual_summary}")
        if transcription:
            logger.info(f"语音转写成功 ({resolved_path.name})，共 {len(transcription)} 字符")
            sections.append(f"## 语音对话 ASR 转写内容\n{transcription}")
        elif audio_note:
            sections.append(f"## 语音轨道说明\n{audio_note}")
        else:
            sections.append("## 语音轨道说明\n该媒体文件未识别到清晰的人声对话文字。")

        return "\n\n".join(sections)

    except Exception as e:
        logger.error(f"解析音视频文件失败 ({resolved_path.name}): {e}")
        return f"[{suffix[1:].upper()} 媒体解析异常] {resolved_path.name}\n状态说明：媒体文件已归档保存，自动提取阶段遇到异常。"

    finally:
        # 清理临时 wav 文件
        try:
            if os.path.exists(temp_wav):
                os.unlink(temp_wav)
        except OSError:
            pass
