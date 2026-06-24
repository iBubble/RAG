import sys
import os
sys.path.append('/app/backend')
from core.extractors import extract_text

files_to_test = [
    '/app/docs/典型案例_扶人当事人陈述录音.mp3',
    '/app/docs/典型案例_超车侧翻事故现场报案录音.wav',
    '/app/docs/典型案例_超车侧翻事故监控画面模拟.mp4',
    '/app/docs/典型案例_扶人反被诉身体权纠纷民事判决书.md',
    '/app/docs/最高人民法院关于审理人身损害赔偿案件适用法律若干问题的解释(2022修正).md'
]

print("=== 开始测试新生成的多模态与文本案例提取效果 ===")
for fpath in files_to_test:
    print(f"\n--- 测试提取: {os.path.basename(fpath)} ---")
    if os.path.exists(fpath):
        try:
            res = extract_text(fpath)
            print(f"成功！提取内容字数: {len(res) if res else 0}")
            if res:
                print(f"【前200字预览】:\n{res[:200]}...")
        except Exception as e:
            print(f"提取失败！错误: {e}")
    else:
        print(f"文件不存在: {fpath}")
