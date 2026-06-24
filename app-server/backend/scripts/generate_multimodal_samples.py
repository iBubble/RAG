import os
import subprocess
from gtts import gTTS

# 容器内的生成目录
output_dir = "/app/docs"
os.makedirs(output_dir, exist_ok=True)

# 1. 扶人案情当事人陈述录音 (MP3)
voice_1_text = "我当时骑着自行车经过中山路，看到前面的王奶奶自己摔倒在地上，我就好心过去把她扶起来，没想到她非要说是我撞倒了她。我真的没有撞她，我是做好人好事啊！"
# 2. 交通事故报案录音 (WAV)
voice_2_text = "喂，是110交警大队吗？在建设路这里发生了一起交通事故。一辆送外卖的摩托车在超车时距离过近，导致右侧骑电动自行车的老大爷受到惊吓侧翻摔倒了，现在受伤流血，你们快派人来处理一下。"

def main():
    print("开始生成多模态语音与视频测试样例...")
    
    # 临时 mp3 路径
    temp_mp3_1 = os.path.join(output_dir, "temp_voice1.mp3")
    temp_mp3_2 = os.path.join(output_dir, "temp_voice2.mp3")
    
    # 使用 gTTS 生成中文语音
    print("1. 正在调用 gTTS 生成当事人陈述录音 (中文)...")
    tts1 = gTTS(text=voice_1_text, lang='zh-cn')
    tts1.save(temp_mp3_1)
    
    print("2. 正在调用 gTTS 生成报案语音 (中文)...")
    tts2 = gTTS(text=voice_2_text, lang='zh-cn')
    tts2.save(temp_mp3_2)
    
    # 格式转换与视频合成
    # 音频 1: 直接重命名/复制为目标 MP3
    final_mp3 = os.path.join(output_dir, "典型案例_扶人当事人陈述录音.mp3")
    os.rename(temp_mp3_1, final_mp3)
    print(f"-> 生成音频成功: {final_mp3}")
    
    # 音频 2: 使用 ffmpeg 转换为标准 WAV
    final_wav = os.path.join(output_dir, "典型案例_超车侧翻事故现场报案录音.wav")
    print("3. 正在使用 ffmpeg 转换格式为 WAV...")
    cmd_wav = ["ffmpeg", "-y", "-i", temp_mp3_2, "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", final_wav]
    subprocess.run(cmd_wav, capture_output=True)
    print(f"-> 生成音频成功: {final_wav}")
    
    # 视频 1: 使用 ffmpeg 结合静态背景和报案语音合成 MP4 视频
    final_mp4 = os.path.join(output_dir, "典型案例_超车侧翻事故监控画面模拟.mp4")
    print("4. 正在使用 ffmpeg 合成模拟视频文件...")
    # ffmpeg 画图滤镜产生一个黑底带文字的视频
    cmd_video = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=640x480:d=15",
        "-i", temp_mp3_2,
        "-vf", "drawtext=text='Traffic Accident Video Simulation':fontcolor=white:fontsize=24:x=(w-text_w)/2:y=(h-text_h)/2",
        "-c:v", "libx264", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k", "-shortest",
        final_mp4
    ]
    subprocess.run(cmd_video, capture_output=True)
    print(f"-> 生成视频成功: {final_mp4}")
    
    # 清理临时文件
    if os.path.exists(temp_mp3_2):
        os.unlink(temp_mp3_2)
        
    print("所有音视频多模态测试数据生成完毕！")

if __name__ == "__main__":
    main()
