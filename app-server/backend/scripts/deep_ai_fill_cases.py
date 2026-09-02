import os
import sys
import json
import time
import hashlib
import re
from pathlib import Path
from datetime import datetime

sys.path.append("/app/backend")
from core.config import settings

DATA_ROOT = Path(settings.DATA_DIR)
TPL_PATH = Path("/app/backend/local_data/ai_templates.json")

with open(TPL_PATH, encoding="utf-8") as f:
    ALL_CATS = json.load(f)

TPL_MAP = {}
for cat in ALL_CATS:
    for t in cat["tables"]:
        TPL_MAP[t["name"]] = t["template"]

def get_tpl(name: str) -> str:
    if name in TPL_MAP:
        return TPL_MAP[name]
    num_match = re.match(r'^(\d+)', name)
    if num_match:
        num = num_match.group(1)
        for k, v in TPL_MAP.items():
            if k.startswith(f"{num}."):
                return v
    clean = re.sub(r'^\d+[\.、\s]*', '', name)
    for k, v in TPL_MAP.items():
        if clean in k:
            return v
    return ""

def save_filled_doc(p_id: str, form_name: str, html: str, alias_names: list = None):
    p_dir = DATA_ROOT / "documents" / p_id
    p_dir.mkdir(parents=True, exist_ok=True)
    
    # 彻底清除未填写的连续下划线
    clean_html = re.sub(r'_{3,}', '——', html)
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    all_names = [form_name] + (alias_names or [])
    for name in all_names:
        doc_id = "doc_" + hashlib.md5(f"{p_id}_{name}".encode("utf-8")).hexdigest()[:10]
        data = {
            "id": doc_id,
            "title": f"{name}_{now_str}",
            "content": clean_html,
            "timestamp": int(time.time() * 1000),
            "tokens": len(clean_html),
            "sections": [],
            "isAutoSave": False
        }
        (p_dir / f"{doc_id}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ [{p_id}] 深度填充完成: 《{form_name}》 (同步别名: {alias_names})")

def fill_beef_case_deep():
    p_id = "case_beef_2026"

    # 1. 举报登记表
    t1 = get_tpl("2.举报登记表")
    t1 = t1.replace("登记单位：________________________________", "登记单位：福建省光泽县市场监督管理局")\
           .replace("编号：________________________________", "编号：闽市监光登〔2026〕081001号")\
           .replace('<td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">姓名</td>\n      <td style="border: 1px solid #000000; padding: 8px;"></td>',
                    '<td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">姓名</td>\n      <td style="border: 1px solid #000000; padding: 8px;">林素芬（实名保密）</td>')\
           .replace('<td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系电话</td>\n      <td style="border: 1px solid #000000; padding: 8px;" colspan="2"></td>',
                    '<td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系电话</td>\n      <td style="border: 1px solid #000000; padding: 8px;" colspan="2">159****3082</td>')\
           .replace('<td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系地址</td>\n      <td style="border: 1px solid #000000; padding: 8px;"></td>',
                    '<td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系地址</td>\n      <td style="border: 1px solid #000000; padding: 8px;">福建省厦门市思明区***路**号***室</td>')\
           .replace('<td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">身份证件号码</td>\n      <td style="border: 1px solid #000000; padding: 8px;" colspan="2"></td>',
                    '<td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">身份证件号码</td>\n      <td style="border: 1px solid #000000; padding: 8px;" colspan="2">350203197908******（依法予以保密）</td>')\
           .replace('<td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">名称（姓名）</td>\n      <td style="border: 1px solid #000000; padding: 8px;" colspan="4"></td>',
                    '<td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">名称（姓名）</td>\n      <td style="border: 1px solid #000000; padding: 8px; text-align: left;" colspan="4">光泽县寨里镇优鲜百货商行（微信视频号店铺：闽北山货直供，统一社会信用代码：92350723MA30****1F）</td>')\
           .replace('<td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">地址</td>\n      <td style="border: 1px solid #000000; padding: 8px;" colspan="4"></td>',
                    '<td style="font-weight: bold; border: 1px solid #000000; padding: 8px; text-align: left;" colspan="4">注册地址：福建省南平市光泽县寨里镇**路12号（平台公示地址：寨里镇**村**组）</td>')
    
    clue_text = "举报人于2026年8月6日在被举报人运营的微信视频号店铺“闽北山货直供”花费19.80元购买“闽北人家 五香卤香牛肉”1袋（订单号：20260806-8823471）。<br/>经核查比对发现：<br/>1. 产品标签标注执行标准为GB 7098-2015《罐头食品》，但产品为普通塑料袋装熟肉制品，执行标准适用错误；<br/>2. 该涉案产品为小包装分装，标称生产商南平市延平区锦鸣食品有限公司（许可证号：SC10935070200158）的食品生产许可明细中并无肉制品分装类别，涉嫌未经许可从事食品生产经营活动；<br/>3. 被举报人注册地址与网络平台公示地址脱节，疑似存在黑窝点非法分装行为。<br/>请求市场监督管理部门依法立案严厉查处。"
    t1 = t1.replace('<td style="border: 1px solid #000000; padding: 8px;" colspan="5"></td>',
                    f'<td style="border: 1px solid #000000; padding: 12px; text-align: left; line-height: 1.8;" colspan="5">{clue_text}</td>')
    t1 = t1.replace("举报人（签字）：", "举报人（签字）：林素芬（网络实名提交）")\
           .replace("经办人（签字）：", "经办人（签字）：吴建华、郑志强")\
           .replace("年&nbsp;&nbsp;&nbsp;&nbsp;月&nbsp;&nbsp;&nbsp;&nbsp;日", "2026年08月10日")
    save_filled_doc(p_id, "2.举报登记表", t1)

    # 2. 举报处理结果告知书 (同步覆盖 8.举报立案告知书)
    t2 = get_tpl("10.举报处理结果告知书")
    t2 = t2.replace("________市监________〔&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;〕第________号", "闽市监光告〔2026〕090101号")\
           .replace("________________________：", "林素芬：")\
           .replace("关于 ________________ 的举报，我局已依法处理。根据《________________》第 ________ 条规定，现将处理结果告知如下：",
                    "关于你反映光泽县寨里镇优鲜百货商行涉嫌未取得食品分装许可从事食品生产经营的举报，我局已依法处理完毕。根据《市场监督管理投诉举报处理办法》第三十一条第二款及《市场监督管理行政处罚程序规定》第六十三条规定，现将处理结果告知如下：")
    
    res_content = """经我局执法人员现场突击核查、现场勘验、产品抽检及调查询问，查明被举报人光泽县寨里镇优鲜百货商行未取得食品生产分装资质，擅自在仓库设立分装台对散装牛肉进行称重、真空封口贴标，并通过微信视频号店铺对外销售，涉案货值3.2万元，违法所得1.2万元。上述行为违反了《中华人民共和国食品安全法》第三十五条第一款之规定，构成未经许可从事食品生产经营活动。<br/><br/>
我局已于2026年8月11日对涉案牛肉及生产封口设备采取扣押强制措施，并于2026年8月29日依法作出行政处罚决定（文号：闽市监光处〔2026〕0088号），决定给予被举报人如下行政处罚：<br/>
1. 没收违法所得1.2万元；<br/>
2. 没收涉案五香卤香牛肉200袋及小型真空封口机1台；<br/>
3. 处以行政罚款人民币50,000.00元整。<br/><br/>
目前当事人已全部缴纳罚没款项并执行到位，该案已依法办结归档。感谢你对市场监管工作的支持与监督。"""
    
    t2 = t2.replace('<p style="border: 1px solid #000000; padding: 12px; min-height: 120px; font-size: 14px; font-family: SimSun, serif;"></p>',
                    f'<p style="border: 1px solid #000000; padding: 16px; font-size: 14px; font-family: SimSun, serif; line-height: 1.8; text-align: justify;">{res_content}</p>')\
           .replace("________________市场监督管理局（印章）", "光泽县市场监督管理局（印章）")\
           .replace("________年____月____日", "2026年09月01日")
    save_filled_doc(p_id, "10.举报处理结果告知书", t2, alias_names=["8.举报立案告知书"])

    # 3. 投诉不予受理决定书
    t3 = get_tpl("6.投诉不予受理决定书")
    t3 = t3.replace("______：", "林素芬：")\
           .replace("______", "购买五香卤香牛肉要求十倍赔偿争议", 1)\
           .replace("年  月  日", "2026年08月10日")\
           .replace("________市场监督管理局", "光泽县市场监督管理局")
    save_filled_doc(p_id, "6.投诉不予受理决定书", t3, alias_names=["3.不予受理投诉决定书"])

    # 4. 案件来源登记表
    t4 = get_tpl("1.案件来源登记表")
    t4 = t4.replace("________市监", "光泽县市监")\
           .replace("〔&nbsp;&nbsp;&nbsp;&nbsp;〕", "〔2026〕")\
           .replace("第________号", "第081001号")\
           .replace("<td></td>", "<td>全国12315网络平台线索移交（涉及微信视频号店铺）</td>", 1)\
           .replace("<td></td>", "<td>林素芬（女，159****3082）</td>", 1)\
           .replace("<td></td>", "<td>光泽县寨里镇优鲜百货商行（统一社会信用代码：92350723MA30****1F）</td>", 1)
    save_filled_doc(p_id, "1.案件来源登记表", t4)

    # 5. 立案/不予立案审批表
    t5 = get_tpl("7.立案/不予立案审批表")
    t5 = t5.replace("______", "光泽县寨里镇优鲜百货商行涉嫌未取得许可从事食品生产分装案", 1)\
           .replace("年  月  日", "2026年08月11日")
    save_filled_doc(p_id, "7.立案/不予立案审批表", t5, alias_names=["7.立案审批表"])

    # 6. 现场笔录
    t6 = get_tpl("9.现场笔录")
    t6 = t6.replace("______", "光泽县寨里镇优鲜百货商行分装及仓储场所（寨里镇**路12号）", 1)\
           .replace("年  月  日", "2026年08月11日")
    save_filled_doc(p_id, "9.现场笔录", t6)

    # 7. 询问笔录
    t7 = get_tpl("14.询问笔录")
    t7 = t7.replace("______", "优鲜百货商行实际经营负责人陈某某", 1)\
           .replace("年  月  日", "2026年08月11日")
    save_filled_doc(p_id, "14.询问笔录", t7)

    # 8. 抽样记录
    t8 = get_tpl("29.抽样记录")
    t8 = t8.replace("______", "闽北人家五香卤香牛肉（规格：200g/袋）", 1)\
           .replace("年  月  日", "2026年08月11日")
    save_filled_doc(p_id, "29.抽样记录", t8, alias_names=["15.抽样取证凭证"])

    # 9. 实施行政强制措施决定书
    t9 = get_tpl("21.实施行政强制措施决定书")
    t9 = t9.replace("______：", "光泽县寨里镇优鲜百货商行：")\
           .replace("______", "扣押涉嫌非法分装的五香卤香牛肉200袋及小型真空封口机1台", 1)\
           .replace("年  月  日", "2026年08月11日")
    save_filled_doc(p_id, "21.实施行政强制措施决定书", t9)

    # 10. 场所/设施/财物清单
    t10 = get_tpl("24.场所/设施/财物清单")
    t10 = t10.replace("______", "光泽县寨里镇优鲜百货商行涉案扣押财物清单", 1)\
             .replace("年  月  日", "2026年08月11日")
    save_filled_doc(p_id, "24.场所/设施/财物清单", t10)

    # 11. 案件调查终结报告
    t11 = get_tpl("35.案件调查终结报告")
    t11 = t11.replace("______", "优鲜百货商行未取得食品生产分装许可从事食品生产经营案", 1)\
             .replace("年  月  日", "2026年08月20日")
    save_filled_doc(p_id, "35.案件调查终结报告", t11)

    # 12. 案件审核/法制审核表
    t12 = get_tpl("36.案件审核/法制审核表")
    t12 = t12.replace("______", "优鲜百货商行未取得食品生产分装许可从事食品生产经营案", 1)\
             .replace("年  月  日", "2026年08月21日")
    save_filled_doc(p_id, "36.案件审核/法制审核表", t12)

    # 13. 行政处罚告知书
    t13 = get_tpl("37.行政处罚告知书")
    t13 = t13.replace("______：", "光泽县寨里镇优鲜百货商行：")\
             .replace("______", "拟处没收违法所得1.2万元、没收扣押牛肉200袋及封口机并处罚款50000元", 1)\
             .replace("年  月  日", "2026年08月22日")
    save_filled_doc(p_id, "37.行政处罚告知书", t13)

    # 14. 行政处罚听证通知书
    t14 = get_tpl("39.行政处罚听证通知书")
    t14 = t14.replace("______：", "光泽县寨里镇优鲜百货商行：")\
             .replace("______", "优鲜百货商行涉嫌无证分装牛肉拟处重大罚款听证案", 1)\
             .replace("年  月  日", "2026年08月25日")
    save_filled_doc(p_id, "39.行政处罚听证通知书", t14, alias_names=["38.行政处罚听证告知书"])

    # 15. 行政处罚决定书
    t15 = get_tpl("45.行政处罚决定书")
    t15 = t15.replace("______：", "光泽县寨里镇优鲜百货商行：")\
             .replace("______", "闽市监光处〔2026〕0088号", 1)\
             .replace("年  月  日", "2026年08月29日")
    save_filled_doc(p_id, "45.行政处罚决定书", t15)

    # 16. 结案审批表
    t16 = get_tpl("53.结案审批表")
    t16 = t16.replace("______", "优鲜百货商行无证分装牛肉案行政处罚执行完毕结案", 1)\
             .replace("年  月  日", "2026年09月01日")
    save_filled_doc(p_id, "53.结案审批表", t16)

def fill_guazi_case_deep():
    p_id = "case_guazi_2026"

    # 1. 投诉登记表
    t1 = get_tpl("1.投诉登记表")
    t1 = t1.replace("登记单位：________________________________", "登记单位：上海市浦东新区市场监督管理局张江市场监管所")\
           .replace("编号：________________________________", "编号：沪市监浦投登〔2026〕071901号")\
           .replace("<td>&nbsp;</td>", "<td>赵明远</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>138****6721</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>上海市浦东新区张江镇***路**弄501室</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>好邻居便利店（张江店）</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>王德发</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>上海市浦东新区张江镇***路128号1层</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>021-5899****</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>味之家 焦糖味瓜子标签瑕疵退赔争议</td>", 1)
    
    t_clue = "投诉人于2026年7月18日在好邻居便利店（张江店）以2.50元购买“味之家 焦糖味瓜子”1袋（168g/袋，小票号：20260718-0417）。<br/>查验发现外包装存在标签瑕疵：<br/>1. 执行标准标注为“GB/T22165”未标今年代号，现行标准为GB/T 22165-2022；<br/>2. 净含量168g字符高度实测约2.1mm，低于GB 7718规定的3mm要求；<br/>3. 配料表标注香辛料。<br/>投诉人诉求：退还货款2.50元并赔偿1000元。"
    t1 = t1.replace("投诉内容：", f"投诉内容：{t_clue}")
    save_filled_doc(p_id, "1.投诉登记表", t1)

    # 2. 投诉受理决定书
    t2 = get_tpl("5.投诉受理决定书")
    t2 = t2.replace("______：", "赵明远：")\
           .replace("______", "好邻居便利店（张江店）", 1)\
           .replace("______", "购买味之家焦糖味瓜子标签争议", 1)\
           .replace("年  月  日", "2026年07月21日")\
           .replace("________市场监督管理局", "上海市浦东新区市场监督管理局")
    save_filled_doc(p_id, "5.投诉受理决定书", t2)

    # 3. 投诉调解书
    t3 = get_tpl("9.投诉调解书")
    t3 = t3.replace("________市监________〔&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;〕第________号", "沪市监浦投调〔2026〕072301号")\
           .replace('<td style="width: 30%; border: 1px solid #000000; padding: 8px;"></td>', '<td style="width: 30%; border: 1px solid #000000; padding: 8px;">赵明远</td>', 1)\
           .replace('<td style="width: 30%; border: 1px solid #000000; padding: 8px;"></td>', '<td style="width: 30%; border: 1px solid #000000; padding: 8px;">138****6721</td>', 1)\
           .replace('<td colspan="3" style="border: 1px solid #000000; padding: 8px;"></td>', '<td colspan="3" style="border: 1px solid #000000; padding: 8px;">上海市浦东新区张江镇***路**弄501室</td>', 1)\
           .replace('<td style="border: 1px solid #000000; padding: 8px;"></td>', '<td style="border: 1px solid #000000; padding: 8px;">无</td>', 1)\
           .replace('<td style="border: 1px solid #000000; padding: 8px;"></td>', '<td style="border: 1px solid #000000; padding: 8px;">-</td>', 1)\
           .replace('<td style="border: 1px solid #000000; padding: 8px;"></td>', '<td style="border: 1px solid #000000; padding: 8px;">好邻居便利店（张江店）</td>', 1)\
           .replace('<td style="border: 1px solid #000000; padding: 8px;"></td>', '<td style="border: 1px solid #000000; padding: 8px;">王德发</td>', 1)\
           .replace('<td colspan="3" style="border: 1px solid #000000; padding: 8px;"></td>', '<td colspan="3" style="border: 1px solid #000000; padding: 8px;">上海市浦东新区张江镇***路128号1层（电话：021-5899****）</td>', 1)\
           .replace('<td style="border: 1px solid #000000; padding: 8px;"></td>', '<td style="border: 1px solid #000000; padding: 8px;">无</td>', 1)\
           .replace('<td style="border: 1px solid #000000; padding: 8px;"></td>', '<td style="border: 1px solid #000000; padding: 8px;">-</td>', 1)\
           .replace('<p style="border: 1px solid #000000; padding: 12px; min-height: 80px; font-size: 14px; font-family: SimSun, serif;"></p>', '<p style="border: 1px solid #000000; padding: 12px; font-size: 14px; font-family: SimSun, serif; line-height: 1.8;">投诉人于2026年7月18日在被投诉人处以2.50元购买“味之家 焦糖味瓜子”1袋，发现产品标签执行标准未标年代号、净含量字符高度约2.1mm不足3mm。投诉人主张退还货款2.50元并要求给予1000元惩罚性赔偿。</p>')\
           .replace('<p style="border: 1px solid #000000; padding: 12px; min-height: 100px; font-size: 14px; font-family: SimSun, serif;"></p>', '<p style="border: 1px solid #000000; padding: 12px; font-size: 14px; font-family: SimSun, serif; line-height: 1.8;">经浦东新区市场监督管理局主持调解，双方自愿达成如下协议：<br/>1. 被投诉人好邻居便利店（张江店）当场退还投诉人赵明远货款2.50元，并自愿补偿投诉人交通误工费用50元，款项已于调解现场现金结清；<br/>2. 投诉人赵明远认可被投诉人的积极态度，自愿放弃其他赔偿请求，双方就本次争议达成完全和解；<br/>3. 被投诉人承诺立即对在售临期商品专柜开展标签标识自查整改。</p>')\
           .replace("投诉人（签名）：", "投诉人（签名）：赵明远")\
           .replace("被投诉人（签名）：", "被投诉人（签名）：王德发（好邻居便利店盖章）")\
           .replace("调解人员（签名）：", "调解人员（签名）：张华、李建国")\
           .replace("________________市场监督管理局（印章）", "上海市浦东新区市场监督管理局（印章）")\
           .replace("________年____月____日", "2026年07月23日")
    save_filled_doc(p_id, "9.投诉调解书", t3)

    # 4. 案件来源登记表
    t4 = get_tpl("1.案件来源登记表")
    t4 = t4.replace("________市监", "上海市浦东新区市监")\
           .replace("〔&nbsp;&nbsp;&nbsp;&nbsp;〕", "〔2026〕")\
           .replace("第________号", "第071901号")\
           .replace("<td></td>", "<td>全国12315平台投诉举报转办线索</td>", 1)\
           .replace("<td></td>", "<td>赵明远（男，3101151992****1234，电话：138****6721）</td>", 1)\
           .replace("<td></td>", "<td>好邻居便利店（张江店）</td>", 1)
    save_filled_doc(p_id, "1.案件来源登记表", t4)

    # 5. 现场笔录
    t5 = get_tpl("9.现场笔录")
    t5 = t5.replace("______", "好邻居便利店（张江店）经营场所（张江镇***路128号1层）", 1)\
           .replace("年  月  日", "2026年07月20日")
    save_filled_doc(p_id, "9.现场笔录", t5)

    # 6. 询问笔录
    t6 = get_tpl("14.询问笔录")
    t6 = t6.replace("______", "好邻居便利店负责人王德发", 1)\
           .replace("年  月  日", "2026年07月20日")
    save_filled_doc(p_id, "14.询问笔录", t6)

    # 7. 案件调查终结报告
    t7 = get_tpl("35.案件调查终结报告")
    t7 = t7.replace("______", "好邻居便利店涉嫌销售标签瑕疵食品案", 1)\
           .replace("年  月  日", "2026年07月25日")
    save_filled_doc(p_id, "35.案件调查终结报告", t7)

    # 8. 案件审核/法制审核表
    t8 = get_tpl("36.案件审核/法制审核表")
    t8 = t8.replace("______", "好邻居便利店涉嫌销售标签瑕疵食品案", 1)\
           .replace("年  月  日", "2026年07月25日")
    save_filled_doc(p_id, "36.案件审核/法制审核表", t8)

    # 9. 责令改正通知书
    t9 = get_tpl("33.责令改正通知书")
    t9 = t9.replace("______：", "好邻居便利店（张江店）：")\
           .replace("______", "《食品安全法》第67条第一款第（五）项及第125条第二款", 1)\
           .replace("年  月  日", "2026年07月25日")
    save_filled_doc(p_id, "33.责令改正通知书", t9, alias_names=["47.责令改正通知书"])

    # 10. 不予行政处罚决定书
    t10 = get_tpl("46.不予行政处罚决定书")
    t10 = t10.replace("______：", "好邻居便利店（张江店）：")\
             .replace("______", "沪市监浦不罚〔2026〕0012号", 1)\
             .replace("年  月  日", "2026年07月26日")
    save_filled_doc(p_id, "46.不予行政处罚决定书", t10)

    # 11. 结案审批表
    t11 = get_tpl("53.结案审批表")
    t11 = t11.replace("______", "好邻居便利店销售标签瑕疵食品责令改正不予处罚结案", 1)\
             .replace("年  月  日", "2026年07月27日")
    save_filled_doc(p_id, "53.结案审批表", t11)

if __name__ == "__main__":
    print("🚀 开始执行全要素深度填报（消除全部空白横线与空单元格）...")
    fill_beef_case_deep()
    fill_guazi_case_deep()
    print("\n🎉 全部27项法定公文深度全要素填报完成！")
