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

def update_recommendations():
    # 1. 瓜子案推荐
    guazi_rec = {
        "triage": {
            "track": "投诉轨（标签瑕疵调解）",
            "summary": "本案为赵明远针对好邻居便利店销售的“味之家 焦糖味瓜子”提出的投诉举报。经审验，配料表标注香辛料符合GB/T 12729.1标准原料规范；执行标准未标年代号与净含量字符高度不足属于令49号第37条及《食品安全法》第125条第2款规定的标签瑕疵，不影响食品安全且不误导消费者。其索赔诉求属民事维权，依据令121号第9条，立投诉轨受理调解。",
            "recommended_forms": [
                {"name": "1.投诉登记表", "reason": "记录投诉人基本信息、被投诉便利店及购买2.5元瓜子退赔诉求", "required": True},
                {"name": "5.投诉受理决定书", "reason": "符合投诉受理条件，在收到之日起7个工作日内作出并送达投诉人", "required": True},
                {"name": "9.投诉调解书", "reason": "组织双方就退换货及标签瑕疵进行民事争议调解制作调解文书", "required": False}
            ]
        },
        "investigation": {
            "stage": "案源初查核实阶段",
            "summary": "本案系消费者因标签年代号缺失与字符高度不足提起的初查核查。涉案瓜子为临期专柜折价销售商品，货值金额微小（2.50元）。当前依据《行政处罚程序规定》第18条重点核验经营者进货查验记录、索证索票情况及库存，核查是否符合令49号第37条瑕疵轻微情形。",
            "recommended_forms": [
                {"name": "1.案件来源登记表", "reason": "案件线索初查登记，启动15日内立案审查核实程序", "required": True},
                {"name": "9.现场笔录", "reason": "对好邻居便利店现场进行实地检查，清点临期专柜瓜子库存并拍照取证", "required": True},
                {"name": "14.询问笔录", "reason": "对便利店店长及理货员制作调查询问笔录，核实进货来源与查验义务履行情况", "required": True}
            ]
        },
        "adjudication": {
            "disposition_type": "责令改正免罚（不予行政处罚）",
            "summary": "涉案产品执行标准未标年代号、净含量字符高度不足，确属食品标签瑕疵。鉴于当事人履行了进货查验义务，未造成食品安全危害后果且无误导主观故意，依据《食品安全法》第125条第2款、《行政处罚法》第33条第1款及裁量基准，依法裁量为责令改正，不予行政处罚并结案；不予重大违法举报奖励。",
            "recommended_forms": [
                {"name": "35.案件调查终结报告", "reason": "初查终结，梳理进货凭证与现场检查事实，建议责令改正不予立案", "required": True},
                {"name": "36.案件审核/法制审核表", "reason": "法制审核机构对不予立案、不予处罚处理意见进行合法性审核", "required": True},
                {"name": "33.责令改正通知书", "reason": "责令便利店限期下架瑕疵批次瓜子并通知生产厂家规范标签标注", "required": True},
                {"name": "46.不予行政处罚决定书", "reason": "认定当事人违法行为轻微并及时改正，依法出具不予行政处罚决定", "required": True},
                {"name": "53.结案审批表", "reason": "责令改正到位且不予行政处罚决定生效后办理结案归档", "required": True}
            ]
        }
    }

    # 2. 牛肉案推荐
    beef_rec = {
        "triage": {
            "track": "举报查处轨（涉嫌无证生产分装）",
            "summary": "本案为林素芬通过微信视频号店铺购买“闽北人家 五香卤香牛肉”提出的举报及履职申请。依据令121号第13条，平台内经营者由平台公示地址（光泽县）管辖；举报人反映该小包装牛肉生产商许可证无肉制品分装类别，涉嫌未经许可从事食品生产经营，线索具体且涉嫌重大食品安全违法，依据令121号第9条，转行政执法轨立案查处。",
            "recommended_forms": [
                {"name": "2.举报登记表", "reason": "登记举报人提供的网购订单、视频号店铺信息及无分装资质线索", "required": True},
                {"name": "10.举报处理结果告知书", "reason": "书面告知实名举报人案件已受理并立案查处", "required": True},
                {"name": "6.投诉不予受理决定书", "reason": "因涉及无证生产需行政查处，且属于虚假非民事争议，出具不予受理投诉决定", "required": False}
            ]
        },
        "investigation": {
            "stage": "深入现场勘验与强制措施阶段",
            "summary": "案涉微信视频号店铺涉嫌无实体经营场所、虚构生产许可或非法分装肉制品，违法性质恶劣。为防止当事人转移隐匿涉案牛肉及分装设备，依据《行政处罚程序规定》第28条、第37条，依法对注册地及仓储场所实施突击现场检查、采取查封扣押强制措施并抽样送检。",
            "recommended_forms": [
                {"name": "1.案件来源登记表", "reason": "案源归口登记，将视频号网络巡查与举报线索转入办案程序", "required": True},
                {"name": "7.立案/不予立案审批表", "reason": "事实基本清楚且涉嫌严重违法，依法提请主管局长审批正式立案", "required": True},
                {"name": "9.现场笔录", "reason": "执法人员突击检查仓储场所，详细记录无证分装工具及牛肉库存情况", "required": True},
                {"name": "14.询问笔录", "reason": "调查询问店铺负责人，核实购进生熟肉原料、委托代工及实际销售金额", "required": True},
                {"name": "29.抽样记录", "reason": "对涉案真空小包装牛肉抽样送检验机构开展安全指标检验", "required": True},
                {"name": "21.实施行政强制措施决定书", "reason": "依法扣押涉嫌非法分装的卤香牛肉200袋及封口机等生产工具", "required": True},
                {"name": "24.场所/设施/财物清单", "reason": "随强制措施决定书附具查封扣押财产详细清单与规格型号", "required": True}
            ]
        },
        "adjudication": {
            "disposition_type": "依法从重/一般处罚",
            "summary": "经查，生产商许可证无肉制品分装资质，销售者优鲜百货商行擅自分装并隐瞒实际经营场所，违反《食品安全法》第35条构成未经许可从事食品生产经营活动。涉案货值较高且存在安全隐患，依据《食品安全法》第122条第1款及裁量基准，依法没收涉案肉制品、封口设备及违法所得，并处以大额行政处罚罚款。",
            "recommended_forms": [
                {"name": "35.案件调查终结报告", "reason": "调查终结，汇总无证分装检验报告、出入库台账及询问笔录提请审理", "required": True},
                {"name": "36.案件审核/法制审核表", "reason": "法制审核机构进行重大复杂行政处罚合法性审查并出具审核意见", "required": True},
                {"name": "37.行政处罚告知书", "reason": "正式向当事人送达拟处大额罚款告知书，告知其陈述、申辩权利", "required": True},
                {"name": "39.行政处罚听证通知书", "reason": "拟处罚款达到听证标准，依法组织行政处罚听证会并送达通知书", "required": True},
                {"name": "45.行政处罚决定书", "reason": "局长办公会审议通过后，依法正式出具没收违法所得并处行政罚款决定书", "required": True},
                {"name": "53.结案审批表", "reason": "当事人缴纳罚没款并完成执行后，按法定程序审批结案归档", "required": True}
            ]
        }
    }

    for p_id, rec in [("case_guazi_2026", guazi_rec), ("case_beef_2026", beef_rec)]:
        (DATA_ROOT / "triage" / f"{p_id}.json").write_text(json.dumps(rec["triage"], ensure_ascii=False, indent=2), encoding="utf-8")
        (DATA_ROOT / "judgment" / f"{p_id}.json").write_text(json.dumps(rec["investigation"], ensure_ascii=False, indent=2), encoding="utf-8")
        (DATA_ROOT / "adjudication" / f"{p_id}.json").write_text(json.dumps(rec["adjudication"], ensure_ascii=False, indent=2), encoding="utf-8")
    print("✅ 推荐表单数据与56项规范名称精确对齐完成！")

def save_doc(p_id: str, form_name: str, html: str):
    p_dir = DATA_ROOT / "documents" / p_id
    p_dir.mkdir(parents=True, exist_ok=True)
    doc_id = "doc_" + hashlib.md5(f"{p_id}_{form_name}".encode("utf-8")).hexdigest()[:10]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # 写入规范标题与兼容标题
    data = {
        "id": doc_id,
        "title": f"{form_name}_{now_str}",
        "content": html,
        "timestamp": int(time.time() * 1000),
        "tokens": len(html),
        "sections": [],
        "isAutoSave": False
    }
    (p_dir / f"{doc_id}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📄 [{p_id}] 高保真填报公文: 《{form_name}》")

def fill_guazi_all():
    p_id = "case_guazi_2026"
    
    # 1. 投诉登记表
    t1 = get_tpl("1.投诉登记表")
    t1 = t1.replace("<td>&nbsp;</td>", "<td>赵明远</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>138****6721</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>上海市浦东新区张江镇***路**弄501室</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>好邻居便利店（张江店）</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>王德发</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>上海市浦东新区张江镇***路128号1层</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>021-5899****</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>味之家 焦糖味瓜子标签瑕疵退赔争议</td>", 1)\
           .replace("投诉内容：", "投诉内容：投诉人于2026年7月18日在好邻居便利店（张江店）以2.50元购买“味之家 焦糖味瓜子”1袋（168g/袋），发现产品外包装标签存在如下问题：1.配料表标注香辛料；2.执行标准标注GB/T22165未标年代号；3.净含量字符高度实测约2.1mm，低于法定的3mm标准。投诉人诉求：退还货款2.50元并赔偿1000元。")
    save_doc(p_id, "1.投诉登记表", t1)

    # 2. 投诉受理决定书
    t2 = get_tpl("5.投诉受理决定书")
    t2 = t2.replace("______：", "赵明远：")\
           .replace("______", "好邻居便利店（张江店）", 1)\
           .replace("______", "购买味之家焦糖味瓜子标签争议", 1)\
           .replace("年  月  日", "2026年07月21日")\
           .replace("________市场监督管理局", "上海市浦东新区市场监督管理局")
    save_doc(p_id, "5.投诉受理决定书", t2)

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
    save_doc(p_id, "9.投诉调解书", t3)

    # 4. 案件来源登记表
    t4 = get_tpl("1.案件来源登记表")
    t4 = t4.replace("________市监", "上海市浦东新区市监")\
           .replace("〔&nbsp;&nbsp;&nbsp;&nbsp;〕", "〔2026〕")\
           .replace("第________号", "第071901号")\
           .replace("<td></td>", "<td>全国12315平台投诉举报转办线索</td>", 1)\
           .replace("<td></td>", "<td>赵明远（男，3101151992****1234，电话：138****6721）</td>", 1)\
           .replace("<td></td>", "<td>好邻居便利店（张江店）</td>", 1)
    save_doc(p_id, "1.案件来源登记表", t4)

    # 5. 现场笔录
    t5 = get_tpl("9.现场笔录")
    t5 = t5.replace("______", "好邻居便利店（张江店）经营场所（张江镇***路128号1层）", 1)\
           .replace("年  月  日", "2026年07月20日")
    save_doc(p_id, "9.现场笔录", t5)

    # 6. 询问笔录
    t6 = get_tpl("14.询问笔录")
    t6 = t6.replace("______", "好邻居便利店负责人王德发", 1)\
           .replace("年  月  日", "2026年07月20日")
    save_doc(p_id, "14.询问笔录", t6)

    # 7. 案件调查终结报告
    t7 = get_tpl("35.案件调查终结报告")
    t7 = t7.replace("______", "好邻居便利店涉嫌销售标签瑕疵食品案", 1)\
           .replace("年  月  日", "2026年07月25日")
    save_doc(p_id, "35.案件调查终结报告", t7)

    # 8. 案件审核/法制审核表
    t8 = get_tpl("36.案件审核/法制审核表")
    t8 = t8.replace("______", "好邻居便利店涉嫌销售标签瑕疵食品案", 1)\
           .replace("年  月  日", "2026年07月25日")
    save_doc(p_id, "36.案件审核/法制审核表", t8)

    # 9. 责令改正通知书
    t9 = get_tpl("33.责令改正通知书")
    t9 = t9.replace("______：", "好邻居便利店（张江店）：")\
           .replace("______", "《食品安全法》第67条第一款第（五）项及第125条第二款", 1)\
           .replace("年  月  日", "2026年07月25日")
    save_doc(p_id, "33.责令改正通知书", t9)

    # 10. 不予行政处罚决定书
    t10 = get_tpl("46.不予行政处罚决定书")
    t10 = t10.replace("______：", "好邻居便利店（张江店）：")\
             .replace("______", "沪市监浦不罚〔2026〕0012号", 1)\
             .replace("年  月  日", "2026年07月26日")
    save_doc(p_id, "46.不予行政处罚决定书", t10)

    # 11. 结案审批表
    t11 = get_tpl("53.结案审批表")
    t11 = t11.replace("______", "好邻居便利店销售标签瑕疵食品责令改正不予处罚结案", 1)\
             .replace("年  月  日", "2026年07月27日")
    save_doc(p_id, "53.结案审批表", t11)

def fill_beef_all():
    p_id = "case_beef_2026"
    
    # 1. 举报登记表
    b1 = get_tpl("2.举报登记表")
    b1 = b1.replace("<td>&nbsp;</td>", "<td>林素芬（要求保密）</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>159****3082</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>福建省厦门市思明区***路**号</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>光泽县寨里镇优鲜百货商行（视频号店铺：闽北山货直供）</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>福建省南平市光泽县寨里镇**路12号</td>", 1)\
           .replace("<td>&nbsp;</td>", "<td>涉嫌未取得食品分装资质生产销售五香卤香牛肉案</td>", 1)
    save_doc(p_id, "2.举报登记表", b1)

    # 2. 举报处理结果告知书
    b2 = get_tpl("10.举报处理结果告知书")
    b2 = b2.replace("______：", "林素芬：")\
           .replace("______", "光泽县寨里镇优鲜百货商行涉嫌无证分装牛肉", 1)\
           .replace("年  月  日", "2026年08月12日")
    save_doc(p_id, "10.举报处理结果告知书", b2)

    # 3. 投诉不予受理决定书
    b3 = get_tpl("6.投诉不予受理决定书")
    b3 = b3.replace("______：", "林素芬：")\
           .replace("______", "购买五香卤香牛肉要求十倍赔偿争议", 1)\
           .replace("年  月  日", "2026年08月10日")
    save_doc(p_id, "6.投诉不予受理决定书", b3)

    # 4. 案件来源登记表
    b4 = get_tpl("1.案件来源登记表")
    b4 = b4.replace("________市监", "光泽县市监")\
           .replace("〔&nbsp;&nbsp;&nbsp;&nbsp;〕", "〔2026〕")\
           .replace("第________号", "第081001号")\
           .replace("<td></td>", "<td>全国12315网络平台线索移交（涉及微信视频号平台店铺）</td>", 1)\
           .replace("<td></td>", "<td>林素芬（电话：159****3082）</td>", 1)\
           .replace("<td></td>", "<td>光泽县寨里镇优鲜百货商行</td>", 1)
    save_doc(p_id, "1.案件来源登记表", b4)

    # 5. 立案/不予立案审批表
    b5 = get_tpl("7.立案/不予立案审批表")
    b5 = b5.replace("______", "光泽县寨里镇优鲜百货商行涉嫌未取得许可从事食品生产案", 1)\
           .replace("年  月  日", "2026年08月11日")
    save_doc(p_id, "7.立案/不予立案审批表", b5)

    # 6. 现场笔录
    b6 = get_tpl("9.现场笔录")
    b6 = b6.replace("______", "光泽县寨里镇优鲜百货商行分装及仓储场所（寨里镇**路12号）", 1)\
           .replace("年  月  日", "2026年08月11日")
    save_doc(p_id, "9.现场笔录", b6)

    # 7. 询问笔录
    b7 = get_tpl("14.询问笔录")
    b7 = b7.replace("______", "优鲜百货商行经营者陈某某", 1)\
           .replace("年  月  日", "2026年08月11日")
    save_doc(p_id, "14.询问笔录", b7)

    # 8. 抽样记录
    b8 = get_tpl("29.抽样记录")
    b8 = b8.replace("______", "闽北人家五香卤香牛肉（200g/袋）", 1)\
           .replace("年  月  日", "2026年08月11日")
    save_doc(p_id, "29.抽样记录", b8)

    # 9. 实施行政强制措施决定书
    b9 = get_tpl("21.实施行政强制措施决定书")
    b9 = b9.replace("______：", "光泽县寨里镇优鲜百货商行：")\
           .replace("______", "扣押涉嫌非法分装的五香卤香牛肉200袋及小型真空封口机1台", 1)\
           .replace("年  月  日", "2026年08月11日")
    save_doc(p_id, "21.实施行政强制措施决定书", b9)

    # 10. 场所/设施/财物清单
    b10 = get_tpl("24.场所/设施/财物清单")
    b10 = b10.replace("______", "扣押涉案牛肉及分装设备清单", 1)\
             .replace("年  月  日", "2026年08月11日")
    save_doc(p_id, "24.场所/设施/财物清单", b10)

    # 11. 案件调查终结报告
    b11 = get_tpl("35.案件调查终结报告")
    b11 = b11.replace("______", "优鲜百货商行未取得食品生产分装许可从事食品生产经营案", 1)\
             .replace("年  月  日", "2026年08月20日")
    save_doc(p_id, "35.案件调查终结报告", b11)

    # 12. 案件审核/法制审核表
    b12 = get_tpl("36.案件审核/法制审核表")
    b12 = b12.replace("______", "优鲜百货商行未取得食品生产分装许可从事食品生产经营案", 1)\
             .replace("年  月  日", "2026年08月21日")
    save_doc(p_id, "36.案件审核/法制审核表", b12)

    # 13. 行政处罚告知书
    b13 = get_tpl("37.行政处罚告知书")
    b13 = b13.replace("______：", "光泽县寨里镇优鲜百货商行：")\
             .replace("______", "拟没收违法所得、没收涉案牛肉200袋及分装封口机1台并处以罚款50000元", 1)\
             .replace("年  月  日", "2026年08月22日")
    save_doc(p_id, "37.行政处罚告知书", b13)

    # 14. 行政处罚听证通知书
    b14 = get_tpl("39.行政处罚听证通知书")
    b14 = b14.replace("______：", "光泽县寨里镇优鲜百货商行：")\
             .replace("______", "涉嫌未经许可从事食品生产经营拟处大额行政处罚案", 1)\
             .replace("年  月  日", "2026年08月25日")
    save_doc(p_id, "39.行政处罚听证通知书", b14)

    # 15. 行政处罚决定书
    b15 = get_tpl("45.行政处罚决定书")
    b15 = b15.replace("______：", "光泽县寨里镇优鲜百货商行：")\
             .replace("______", "闽市监光处〔2026〕0088号", 1)\
             .replace("年  月  日", "2026年08月29日")
    save_doc(p_id, "45.行政处罚决定书", b15)

    # 16. 结案审批表
    b16 = get_tpl("53.结案审批表")
    b16 = b16.replace("______", "优鲜百货商行无证分装牛肉案行政处罚执行完毕结案", 1)\
             .replace("年  月  日", "2026年09月01日")
    save_doc(p_id, "53.结案审批表", b16)

if __name__ == "__main__":
    print("🚀 开始执行两大演示项目全量高保真文书对齐与深度填充...")
    update_recommendations()
    fill_guazi_all()
    fill_beef_all()
    print("\n🎉 两大演示项目共27项高保真法定公文全量深度填报完成！")
