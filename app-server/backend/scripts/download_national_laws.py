import os
import shutil
import subprocess
from pathlib import Path

# 根目录与目标目录定位，指向 docs/flk/
PROJECT_ROOT = Path(__file__).resolve().parents[3]
LAWS_DIR = PROJECT_ROOT / "docs" / "flk" / "法律"
REGULATIONS_DIR = PROJECT_ROOT / "docs" / "flk" / "行政法规"

LAWS_DIR.mkdir(parents=True, exist_ok=True)
REGULATIONS_DIR.mkdir(parents=True, exist_ok=True)

TEMP_CLONE_DIR = PROJECT_ROOT / "temp_laws_repo"

def extract_title(content: str) -> str:
    """轻量级解析 Markdown YAML 头部中的 title 字段，避免引入 pyyaml 依赖"""
    if not content.startswith("---"):
        return ""
    parts = content.split("---", 2)
    if len(parts) < 3:
        return ""
    yaml_text = parts[1]
    for line in yaml_text.splitlines():
        if line.strip().startswith("title:"):
            title_val = line.split(":", 1)[1].strip()
            title_val = title_val.strip("\"'")
            return title_val
    return ""

def process_markdown_files(src_dir: Path, dest_dir: Path, category_name: str):
    """遍历源目录下的 .md 文件，提取 title 并复制重命名到目标目录"""
    if not src_dir.exists():
        print(f"[Warning] 源目录不存在: {src_dir}")
        return

    count = 0
    for file_path in src_dir.glob("*.md"):
        if file_path.name == "_index.md":
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
            title = extract_title(content)
            if not title:
                # 兜底使用原文件名
                title = file_path.stem
            
            # 去除文件名中不合法的字符
            for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
                title = title.replace(char, "_")
            
            dest_file = dest_dir / f"{title}.md"
            
            # 写入文件
            dest_file.write_text(content, encoding="utf-8")
            count += 1
        except Exception as e:
            print(f"[Warning] 处理文件 {file_path.name} 失败: {e}")
    
    print(f"[Success] 成功导入 [{category_name}] 数据: 共 {count} 篇文档")

def main():
    print("开始以极速模式同步国家核心法律法规数据库...")
    
    # 清理旧的临时目录
    if TEMP_CLONE_DIR.exists():
        shutil.rmtree(TEMP_CLONE_DIR)
        
    proxy_url = "http://127.0.0.1:7897"
    print(f"正在克隆 LawText/laws 静态数据源 (使用代理: {proxy_url})...")
    
    # 执行极简深度克隆，只拉取最新提交
    cmd = [
        "git", 
        "-c", f"http.proxy={proxy_url}", 
        "-c", f"https.proxy={proxy_url}", 
        "clone", "--depth", "1", 
        "https://github.com/LawText/laws.git", 
        str(TEMP_CLONE_DIR)
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("[Success] 成功拉取数据仓库。")
    except Exception as e:
        print(f"[Error] 克隆数据仓库失败: {e}")
        return

    # 分类处理
    print("正在提取并归档法律数据...")
    process_markdown_files(TEMP_CLONE_DIR / "content" / "法律", LAWS_DIR, "法律")
    
    print("正在提取并归档行政法规数据...")
    process_markdown_files(TEMP_CLONE_DIR / "content" / "行政法规", REGULATIONS_DIR, "行政法规")

    # 清理临时目录
    print("正在清理临时文件...")
    try:
        shutil.rmtree(TEMP_CLONE_DIR)
        print("[Success] 临时目录清理完毕。")
    except Exception as e:
        print(f"[Warning] 清理临时目录失败: {e}")
        
    print("\n🎉 国家法律与行政法规批量同步任务全部圆满完成！")

if __name__ == "__main__":
    main()
