"""
依据微信小程序「市场法查查」8大业务条线分类，
将市场监管核心法律法规与最新规章精准分类归集到 cae3c576c743 项目中。
"""
import os
import shutil
from pathlib import Path

TARGET_ROOT = Path("/Volumes/macData/GenRAG_Files/uploads/cae3c576c743")
SRC_LAW = Path("/Volumes/macData/GenRAG_Files/uploads/fc28c7fff7bb")
SRC_RULE = Path("/Volumes/macData/GenRAG_Files/uploads/1c34280f1f56")
SRC_STD_CUSTOM = Path("/Volumes/macData/GenRAG_Files/uploads/fe2982b3820e/01-市场监管执法与投诉处理规程")

# 分类映射规则（关键词与特定文件名）
RULES = {
    "01-综合规定": [
        "行政处罚", "行政许可", "行政强制", "行政复议", "行政诉讼", "监察法",
        "投诉举报", "程序规定", "裁量", "取证", "听证", "执法监督", "文书格式", "投诉处理指南"
    ],
    "02-经营主体": [
        "公司法", "公司登记", "市场主体", "个体工商户", "企业法人", "合伙企业",
        "农民专业合作社", "经营异常名录", "失信名单", "无证无照", "注册资本"
    ],
    "03-反垄断": [
        "反垄断", "垄断协议", "市场支配地位", "经营者集中", "行政性垄断", "公平竞争审查"
    ],
    "04-竞争执法": [
        "反不正当竞争", "促销", "传销", "直销", "商业秘密", "有奖销售"
    ],
    "05-价格监督": [
        "价格法", "价格管理", "明码标价", "价格欺诈", "收费", "罚没", "价格监督"
    ],
    "06-知识产权": [
        "商标", "专利", "地理标志", "知识产权", "集成电路布图", "奥林匹克标志", "特殊标志"
    ],
    "07-广告监管": [
        "广告法", "广告管理", "互联网广告", "医疗广告", "药品.*广告", "代言", "广告审查"
    ],
    "08-市场合同": [
        "合同行政", "合同法", "民法典.*合同", "拍卖", "网络交易", "买卖合同", "霸王条款"
    ],
}

def organize_laws():
    # 收集源文件
    src_files = {}
    for d in [SRC_LAW, SRC_RULE, SRC_STD_CUSTOM]:
        if not d.exists():
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith((".md", ".txt")) and not f.startswith("."):
                    src_files[f] = Path(root) / f

    stats = {cat: 0 for cat in RULES}
    copied_files = set()

    for filename, full_path in src_files.items():
        matched_cat = None
        for cat, kws in RULES.items():
            if any(kw in filename for kw in kws):
                matched_cat = cat
                break
        
        if matched_cat:
            target_file = TARGET_ROOT / matched_cat / filename
            if not target_file.exists():
                shutil.copy2(full_path, target_file)
            stats[matched_cat] += 1
            copied_files.add(filename)

    print("📊 市场法查查8大条线归集完成：")
    for cat, count in stats.items():
        print(f"  - {cat}: {count} 份核心法规")
    print(f"总计归集法律法规: {len(copied_files)} 份！")

if __name__ == "__main__":
    organize_laws()
