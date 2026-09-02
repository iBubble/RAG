import sys
import json
from pathlib import Path
sys.path.append("/app/backend")
from core.config import settings

DATA_ROOT = Path(settings.DATA_DIR)

CASE_RECOMMENDATIONS = {
    "case_guazi_2026": {
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
                {"name": "36.案件审核表", "reason": "法制审核机构对不予立案、不予处罚处理意见进行合法性审核", "required": True},
                {"name": "47.责令改正通知书", "reason": "责令便利店限期下架瑕疵批次瓜子并通知生产厂家规范标签标注", "required": True},
                {"name": "46.不予行政处罚决定书", "reason": "认定当事人违法行为轻微并及时改正，依法出具不予行政处罚决定", "required": True},
                {"name": "53.结案审批表", "reason": "责令改正到位且不予行政处罚决定生效后办理结案归档", "required": True}
            ]
        }
    },
    "case_beef_2026": {
        "triage": {
            "track": "举报查处轨（涉嫌无证生产分装）",
            "summary": "本案为林素芬通过微信视频号店铺购买“闽北人家 五香卤香牛肉”提出的举报及履职申请。依据令121号第13条，平台内经营者由平台公示地址（光泽县）管辖；举报人反映该小包装牛肉生产商许可证无肉制品分装类别，涉嫌未经许可从事食品生产经营，线索具体且涉嫌重大食品安全违法，依据令121号第9条，转行政执法轨立案查处。",
            "recommended_forms": [
                {"name": "2.举报登记表", "reason": "登记举报人提供的网购订单、视频号店铺信息及无分装资质线索", "required": True},
                {"name": "8.举报立案告知书", "reason": "经初步核查符合立案条件，书面告知实名举报人已立案查处", "required": True},
                {"name": "3.不予受理投诉决定书", "reason": "因涉及无证生产需行政查处，且举报人索要高额索赔无法调解，出具不予受理投诉决定", "required": False}
            ]
        },
        "investigation": {
            "stage": "深入现场勘验与强制措施阶段",
            "summary": "案涉微信视频号店铺涉嫌无实体经营场所、虚构生产许可或非法分装肉制品，违法性质恶劣。为防止当事人转移隐匿涉案牛肉及分装设备，依据《行政处罚程序规定》第28条、第37条，依法对注册地及仓储场所实施突击现场检查、采取查封扣押强制措施并抽样送检。",
            "recommended_forms": [
                {"name": "1.案件来源登记表", "reason": "案源归口登记，将视频号网络巡查与举报线索转入办案程序", "required": True},
                {"name": "7.立案审批表", "reason": "事实基本清楚且涉嫌严重违法，依法提请主管局长审批正式立案", "required": True},
                {"name": "9.现场笔录", "reason": "执法人员突击检查仓储场所，详细记录无证分装工具及牛肉库存情况", "required": True},
                {"name": "14.询问笔录", "reason": "调查询问店铺负责人，核实购进生熟肉原料、委托代工及实际销售金额", "required": True},
                {"name": "15.抽样取证凭证", "reason": "对涉案真空小包装牛肉抽样送检验机构开展安全指标检验", "required": True},
                {"name": "21.实施行政强制措施决定书", "reason": "依法扣押涉嫌非法分装的卤香牛肉200袋及封口机等生产工具", "required": True},
                {"name": "24.场所、设施、财物清单", "reason": "随强制措施决定书附具查封扣押财产详细清单与规格型号", "required": True}
            ]
        },
        "adjudication": {
            "disposition_type": "依法从重/一般处罚",
            "summary": "经查，生产商许可证无肉制品分装资质，销售者优鲜百货商行擅自分装并隐瞒实际经营场所，违反《食品安全法》第35条构成未经许可从事食品生产经营活动。涉案货值较高且存在安全隐患，依据《食品安全法》第122条第1款及裁量基准，依法没收涉案肉制品、封口设备及违法所得，并处以大额行政处罚罚款。",
            "recommended_forms": [
                {"name": "35.案件调查终结报告", "reason": "调查终结，汇总无证分装检验报告、出入库台账及询问笔录提请审理", "required": True},
                {"name": "36.案件审核表", "reason": "法制审核机构进行重大复杂行政处罚合法性审查并出具审核意见", "required": True},
                {"name": "37.行政处罚告知书", "reason": "正式向当事人送达拟处大额罚款告知书，告知其陈述、申辩权利", "required": True},
                {"name": "38.行政处罚听证告知书", "reason": "拟处罚款达到听证标准，依法告知当事人在法定期限内享有听证权", "required": True},
                {"name": "45.行政处罚决定书", "reason": "局长办公会审议通过后，依法正式出具没收违法所得并处行政罚款决定书", "required": True},
                {"name": "53.结案审批表", "reason": "当事人缴纳罚没款并完成执行后，按法定程序审批结案归档", "required": True}
            ]
        }
    }
}

def save_all_recommendations():
    for p_id, data in CASE_RECOMMENDATIONS.items():
        # 1. 保存 triage
        (DATA_ROOT / "triage" / f"{p_id}.json").write_text(
            json.dumps(data["triage"], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # 2. 保存 judgment (调查取证)
        (DATA_ROOT / "judgment" / f"{p_id}.json").write_text(
            json.dumps(data["investigation"], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # 3. 保存 adjudication (研判裁量)
        (DATA_ROOT / "adjudication" / f"{p_id}.json").write_text(
            json.dumps(data["adjudication"], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"✅ 已成功保存项目 {p_id} 的全套推荐文书与裁量推演结论！")

if __name__ == "__main__":
    save_all_recommendations()
