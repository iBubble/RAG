import sys
import os
sys.path.append('/app/backend')
from core.extractors import extract_text

wav_path = '/app/当事人陈述录音.wav'
mp4_path = '/app/现场监控视频录像.mp4'

print("--- 开始测试音频 WAV 提取 ---")
if os.path.exists(wav_path):
    txt_wav = extract_text(wav_path)
    print(f"音频提取文字结果:\n{txt_wav}")
else:
    print(f"错误: {wav_path} 不存在")

print("\n--- 开始测试视频 MP4 提取 ---")
if os.path.exists(mp4_path):
    txt_mp4 = extract_text(mp4_path)
    print(f"视频提取文字结果:\n{txt_mp4}")
else:
    print(f"错误: {mp4_path} 不存在")
