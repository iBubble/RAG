"""
将市监局全部近600部法律、法规、规章与最新文件，
全量精准归类至微信小程序「市监法规」20大完整条线分类中。
"""
import os
import shutil
from pathlib import Path

TARGET_ROOT = Path("/Volumes/macData/GenRAG_Files/uploads/cae3c576c743")
SRC_LAW = Path("/Volumes/macData/GenRAG_Files/uploads/fc28c7fff7bb")
SRC_RULE = Path("/Volumes/macData/GenRAG_Files/uploads/1c34280f1f56")
SRC_STD = Path("/Volumes/macData/GenRAG_Files/uploads/fe2982b3820e/01-市场监管执法与投诉处理规程")

# 20大条线匹配关键词映射规则（按优先级顺序判定）
RULES_20 = [
    ("11-特殊食品", ["保健食品", "特殊医学用途", "配方食品", "婴幼儿配方", "配方乳粉", "特殊食品"]),
    ("10-食品安全", ["食品安全", "食品生产", "食品经营", "餐饮服务", "食品召回", "食品抽检", "食品补充检验", "食品添加剂", "散装食品", "农产品质量"]),
    ("14-化妆品监管", ["化妆品", "牙膏"]),
    ("13-医疗器械", ["医疗器械"]),
    ("12-药品监管", ["药品", "中医药", "疫苗", "中药", "处方", "药事", "麻醉药品", "精神药品"]),
    ("16-特种设备", ["特种设备", "电梯", "起重机械", "锅炉", "压力容器", "气瓶", "客运索道", "大型游乐设施", "压力管道"]),
    ("18-认证认可", ["认证认可", "认证机构", "强制性产品认证", "资质认定", "认可监督", "管理体系认证", "绿色产品认证"]),
    ("17-标准管理", ["标准化", "标准管理", "地方标准", "团体标准", "企业标准", "行业标准", "国际标准", "国家标准管理"]),
    ("19-计量监管", ["计量法", "计量检定", "计量监督", "定量包装", "集贸市场计量", "计量器具", "计量标准", "校准", "能效标识"]),
    ("09-消费维权", ["消费者权益", "消协", "维权", "退货", "三包", "修理更换退货", "侵害消费者", "消费者保护"]),
    ("15-产品质量", ["产品质量", "工业产品", "生产许可证", "产品召回", "缺陷汽车", "缺陷消费品", "防伪", "商品质量", "棉花质量", "纤维质量"]),
    ("07-广告监管", ["广告法", "广告管理", "互联网广告", "医疗广告", "广告审查", "广告发布", "代言"]),
    ("05-价格监督", ["价格法", "价格管理", "明码标价", "价格欺诈", "收费", "罚没", "价格监督", "价格监测", "反价格垄断", "政府定价"]),
    ("03-反垄断", ["反垄断", "垄断协议", "市场支配地位", "经营者集中", "反垄断指南", "行政垄断"]),
    ("04-竞争执法", ["反不正当竞争", "不正当竞争", "促销", "传销", "直销", "商业秘密", "有奖销售", "商誉"]),
    ("06-知识产权", ["商标", "专利", "地理标志", "知识产权", "集成电路布图", "奥林匹克标志", "世界博览会标志", "知名品牌"]),
    ("08-市场合同", ["合同行政", "民法典.*合同", "拍卖", "网络交易", "买卖合同", "霸王条款", "合同违法", "二手车流通", "农贸市场"]),
    ("02-经营主体", ["公司法", "市场主体", "企业法人", "个体工商户", "合伙企业", "个人独资", "农民专业合作社", "外商投资", "电子营业执照", "注册资本", "经营异常", "失信名单", "无证无照", "歇业", "企业名称", "注销", "股权出质", "受益所有人", "营商环境"]),
    ("01-综合规定", ["行政处罚", "行政许可", "行政强制", "行政复议", "行政诉讼", "投诉举报", "执法人员", "裁量基准", "电子数据取证", "听证", "政务处分", "公务员法", "国家赔偿", "三项制度", "政府采购", "行刑衔接", "轻微违法", "取证规则"]),
    ("20-关联法规", ["刑法", "民事诉讼", "安全生产", "个人信息保护", "数据安全", "网络安全", "反电信网络诈骗", "劳动法", "劳动合同", "保守国家秘密", "突发事件", "国家安全", "档案法", "民法典"])
]

def build_all():
    src_files = {}
    for d in [SRC_LAW, SRC_RULE, SRC_STD]:
        if not d.exists():
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith((".md", ".txt")) and not f.startswith("."):
                    src_files[f] = Path(root) / f

    stats = {cat: 0 for cat, _ in RULES_20}
    total_assigned = 0

    for filename, full_path in src_files.items():
        assigned = False
        for cat, kws in RULES_20:
            if any(re.search(kw, filename) for kw in kws):
                target_dir = TARGET_ROOT / cat
                target_file = target_dir / filename
                if not target_file.exists():
                    shutil.copy2(full_path, target_file)
                stats[cat] += 1
                assigned = True
                break
        
        if not assigned:
            # 默认关联法规
            target_dir = TARGET_ROOT / "20-关联法规"
            target_file = target_dir / filename
            if not target_file.exists():
                shutil.copy2(full_path, target_file)
            stats["20-关联法规"] += 1

    print("\n================== 微信小程序「市监法规」20大条线分类统计 ==================")
    grand_total = 0
    for cat, _ in RULES_20:
        cdir = TARGET_ROOT / cat
        cnt = len([f for f in os.listdir(cdir) if not f.startswith(".")])
        print(f"📁 {cat}: {cnt} 篇规范法规")
        grand_total += cnt
    print("==========================================================================")
    print(f"🎉 20大条线全部建立完毕，全库归集法规总量: {grand_total} 篇！\n")

if __name__ == "__main__":
    import re
    build_all()
