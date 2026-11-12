/**
 * 食品生产企业监督检查要点数据与预置评定库（14大类，79项）
 * 依据：《食品生产经营监督检查要点表》（表1-1）与《食品安全法》《GB 14881》
 */

export interface InspectionPreset {
  status: 'compliant' | 'warning' | 'non_compliant' | 'not_applicable';
  label: string;
  risk: '低风险' | '中风险' | '高风险' | '无风险';
  finding: string;
  suggestion: string;
}

export interface InspectionItem {
  id: string;
  itemNo: string;
  content: string;
  isKey: boolean;
  categorySeq: number;
  categoryName: string;
  location: string;
  presetPass: InspectionPreset;
  presetIssue: InspectionPreset;
}

export interface InspectionCategory {
  seq: number;
  name: string;
  location: string;
  itemCount: number;
  keyCount: number;
  items: InspectionItem[];
}

export interface EvaluationRecord {
  itemNo: string;
  photoUrl?: string;
  photoName?: string;
  evaluatedAt?: string;
  status: 'compliant' | 'warning' | 'non_compliant' | 'not_applicable';
  finding: string;
  suggestion: string;
  risk: '低风险' | '中风险' | '高风险' | '无风险';
  isAiEvaluated: boolean;
  isCustomModified?: boolean;
}

export const FOOD_INSPECTION_CATEGORIES: InspectionCategory[] = [
  {
    "seq": 1,
    "name": "食品生产者资质",
    "location": "企业档案室 / 综合管理办公室",
    "itemCount": 3,
    "keyCount": 3,
    "items": [
      {
        "id": "item_1_1",
        "itemNo": "*1.1",
        "content": "具有合法主体资质，生产许可证在有效期内。",
        "isKey": true,
        "categorySeq": 1,
        "categoryName": "食品生产者资质",
        "location": "企业档案室 / 综合管理办公室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核验企业食品生产许可证原件（SC10653011100888），许可明细包含当前生产类别，在有效期内，住所及法定代表人与营业执照一致。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_1_2",
        "itemNo": "*1.2",
        "content": "生产的食品、食品添加剂在许可范围内。",
        "isKey": true,
        "categorySeq": 1,
        "categoryName": "食品生产者资质",
        "location": "企业档案室 / 综合管理办公室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "核对正在生产的食品品种、外包装执行标准与生产许可证明细表，均在准予许可范围内，未见超范围生产现象。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_1_3",
        "itemNo": "*T.1",
        "content": "实际生产的特殊食品按规定注册或备案，注册证书或备案凭证符合要求。",
        "isKey": true,
        "categorySeq": 1,
        "categoryName": "食品生产者资质",
        "location": "企业档案室 / 综合管理办公室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "经核查，企业未生产保健食品或婴幼儿配方食品等特殊食品，生产台账与备案品类一致，属于合理项。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      }
    ]
  },
  {
    "seq": 2,
    "name": "生产环境条件（厂区、车间、设施、设备）",
    "location": "厂区外围 / 生产车间 / 洗消间",
    "itemCount": 11,
    "keyCount": 1,
    "items": [
      {
        "id": "item_2_1",
        "itemNo": "2.1",
        "content": "厂区无扬尘、无积水，厂区、车间卫生整洁。",
        "isKey": false,
        "categorySeq": 2,
        "categoryName": "生产环境条件（厂区、车间、设施、设备）",
        "location": "厂区外围 / 生产车间 / 洗消间",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "厂区道路全部硬化，无扬尘、无大面积积水；生产车间地面干净干燥，排污槽流水通畅无污垢积存。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_2_2",
        "itemNo": "*2.2",
        "content": "厂区、车间与有毒、有害场所及其他污染源保持规定的距离或具备有效防范措施。",
        "isKey": true,
        "categorySeq": 2,
        "categoryName": "生产环境条件（厂区、车间、设施、设备）",
        "location": "厂区外围 / 生产车间 / 洗消间",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "厂区周围 50 米范围内未见暴露垃圾堆、化工排污口等污染源，车间密闭性良好，具备有效防尘隔绝防护措施。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_2_3",
        "itemNo": "2.3",
        "content": "设备布局和工艺流程、主要生产设备设施与准予食品生产许可时保持一致。",
        "isKey": false,
        "categorySeq": 2,
        "categoryName": "生产环境条件（厂区、车间、设施、设备）",
        "location": "厂区外围 / 生产车间 / 洗消间",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核对车间生产流水线布局与设备设施配置，人流、物流通道清晰，与食品生产许可核查图纸完全一致。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】2号输送机传动轴处有少量润滑油滴漏，设备点检记录卡最近3日未填写。建议：立即清理润滑油污并紧固防漏密封圈，严格执行设备每日点检制度。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_2_4",
        "itemNo": "2.4",
        "content": "卫生间保持清洁，未与食品生产、包装或贮存等区域直接连通。",
        "isKey": false,
        "categorySeq": 2,
        "categoryName": "生产环境条件（厂区、车间、设施、设备）",
        "location": "厂区外围 / 生产车间 / 洗消间",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "卫生间设于生产车间外部独立区域，未与生产、包装或贮存区连通，自动闭门器与强排风扇运转良好，室内清洁无异味。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】原料仓库 B 区部分面粉托盘直接靠墙堆放，离墙间距不足 10cm，且温湿度记录表最近两天未签字更新。建议：按照 GB 14881 规范调整原料堆垛间距（离地离墙≥10cm），补全日常巡查温湿度记录。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_2_5",
        "itemNo": "2.5",
        "content": "有更衣、洗手、干手、消毒等卫生设备设施，满足正常使用。",
        "isKey": false,
        "categorySeq": 2,
        "categoryName": "生产环境条件（厂区、车间、设施、设备）",
        "location": "厂区外围 / 生产车间 / 洗消间",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "更衣室内配备足够数量的衣柜与紫外消毒灯；洗手池配备非手动感应水龙头、洗手液、自动热风干手器及 75% 酒精消毒喷雾，运行正常。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现 1 号更衣室洗手池感应龙头出水异常，洗手液瓶已空未及时补充，干手纸巾盒缺纸。建议：立即修复感应龙头，定人定时巡查并补充洗手消毒耗材。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_2_6",
        "itemNo": "2.6",
        "content": "通风、防尘、排水、照明、温控等设备设施正常运行，存放垃圾、废弃物的设备设施标识清晰，有效防护。",
        "isKey": false,
        "categorySeq": 2,
        "categoryName": "生产环境条件（厂区、车间、设施、设备）",
        "location": "厂区外围 / 生产车间 / 洗消间",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "车间通风换气与排尘设施运行良好；各工位废弃物容器均加盖密闭并张贴统一‘废弃物’标识，未见垃圾溢流。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】包装区有一只废弃物桶未盖上密闭盖，内有废弃包装碎料。建议：立即整改加盖密封，强化员工现场卫生守则培训。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_2_7",
        "itemNo": "2.7",
        "content": "车间内使用的洗涤剂、消毒剂等化学品明显标示、分类贮存，与食品原料、半成品、成品、包装材料等分隔放置，并有相应的使用记录。",
        "isKey": false,
        "categorySeq": 2,
        "categoryName": "生产环境条件（厂区、车间、设施、设备）",
        "location": "厂区外围 / 生产车间 / 洗消间",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "车间清洁所用消毒剂、洗涤剂存放于专用化学品柜并双人双锁管理，与食品原辅料严格隔离，领用台账记录清晰。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】原料仓库 B 区部分面粉托盘直接靠墙堆放，离墙间距不足 10cm，且温湿度记录表最近两天未签字更新。建议：按照 GB 14881 规范调整原料堆垛间距（离地离墙≥10cm），补全日常巡查温湿度记录。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_2_8",
        "itemNo": "2.8",
        "content": "生产设备设施定期维护保养，并有相应的记录。",
        "isKey": false,
        "categorySeq": 2,
        "categoryName": "生产环境条件（厂区、车间、设施、设备）",
        "location": "厂区外围 / 生产车间 / 洗消间",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "查看打浆机、杀菌釜、自动包装机等关键设备，张贴有设备点检卡与合格标识，最近一次保养日期记录完整规范。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】2号输送机传动轴处有少量润滑油滴漏，设备点检记录卡最近3日未填写。建议：立即清理润滑油污并紧固防漏密封圈，严格执行设备每日点检制度。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_2_9",
        "itemNo": "2.9",
        "content": "监控设备（如压力表、温度计）定期检定或校准、维护，并有相关记录。",
        "isKey": false,
        "categorySeq": 2,
        "categoryName": "生产环境条件（厂区、车间、设施、设备）",
        "location": "厂区外围 / 生产车间 / 洗消间",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "抽查杀菌釜压力表与冷库数字温度计，均在法定计量检定/校准有效期内，铅封完整，现场温湿度记录与仪表显示吻合。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】2号输送机传动轴处有少量润滑油滴漏，设备点检记录卡最近3日未填写。建议：立即清理润滑油污并紧固防漏密封圈，严格执行设备每日点检制度。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_2_10",
        "itemNo": "2.10",
        "content": "定期检查防鼠、防蝇、防虫害装置的使用情况并有相应检查记录，生产场所无虫害迹象。",
        "isKey": false,
        "categorySeq": 2,
        "categoryName": "生产环境条件（厂区、车间、设施、设备）",
        "location": "厂区外围 / 生产车间 / 洗消间",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "各车间外门均安装 60cm 铝合金挡鼠板，车间通道悬挂粘捕式灭蝇灯（避开食品正上方），检查记录显示无鼠迹虫害活动。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】生产车间后门挡鼠板底部密封胶条破损，缝隙约 1.5cm；车间中部 1 盏灭蝇灯未接通电源。建议：立即更换挡鼠板密封条，接通并检修灭蝇装置，防范有害生物侵入。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_2_11",
        "itemNo": "2.11",
        "content": "准清洁作业区、清洁作业区设置合理并有效分割。有空气净化要求的，应当符合相应要求，并对空气洁净度、压差、换气次数、温度、湿度等进行监测及记录。",
        "isKey": false,
        "categorySeq": 2,
        "categoryName": "生产环境条件（厂区、车间、设施、设备）",
        "location": "厂区外围 / 生产车间 / 洗消间",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "洁净作业区压差表显示正压符合规定要求，空气净化过滤机组运行良好，定期沉降菌与温湿度监测记录完整有效。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      }
    ]
  },
  {
    "seq": 3,
    "name": "进货查验",
    "location": "原辅料库 / 采购台账室",
    "itemCount": 4,
    "keyCount": 3,
    "items": [
      {
        "id": "item_3_1",
        "itemNo": "*3.1",
        "content": "查验食品原料、食品添加剂、食品相关产品供货者的许可证、产品合格证明文件等；供货者无法提供有效合格证明文件的，有检验记录。",
        "isKey": true,
        "categorySeq": 3,
        "categoryName": "进货查验",
        "location": "原辅料库 / 采购台账室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核验企业食品生产许可证原件（SC10653011100888），许可明细包含当前生产类别，在有效期内，住所及法定代表人与营业执照一致。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_3_2",
        "itemNo": "*3.2",
        "content": "进货查验记录及证明材料真实、完整，记录和凭证保存期限符合要求。",
        "isKey": true,
        "categorySeq": 3,
        "categoryName": "进货查验",
        "location": "原辅料库 / 采购台账室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场抽查本月采购的面粉、食用植物油、包装膜，供货方营业执照、生产许可证及批次出厂检验合格报告索取齐全，台账完整。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_3_3",
        "itemNo": "3.3",
        "content": "建立和保存食品原料、食品添加剂、食品相关产品的贮存、保管记录、领用出库和退库记录。",
        "isKey": false,
        "categorySeq": 3,
        "categoryName": "进货查验",
        "location": "原辅料库 / 采购台账室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "食品添加剂严格实行‘专人采购、专人保管、专人领用、专库存储、专用称量、专人复核、专用台账’五专管理，使用品种与限量符合 GB 2760。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】原料仓库 B 区部分面粉托盘直接靠墙堆放，离墙间距不足 10cm，且温湿度记录表最近两天未签字更新。建议：按照 GB 14881 规范调整原料堆垛间距（离地离墙≥10cm），补全日常巡查温湿度记录。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_3_4",
        "itemNo": "*T.2",
        "content": "生产特殊食品使用的原料、食品添加剂与注册或备案的技术要求一致。",
        "isKey": true,
        "categorySeq": 3,
        "categoryName": "进货查验",
        "location": "原辅料库 / 采购台账室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "经核查，企业未生产保健食品或婴幼儿配方食品等特殊食品，生产台账与备案品类一致，属于合理项。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      }
    ]
  },
  {
    "seq": 4,
    "name": "生产过程控制",
    "location": "配料间 / 生产加工车间流水线",
    "itemCount": 18,
    "keyCount": 8,
    "items": [
      {
        "id": "item_4_1",
        "itemNo": "*4.1",
        "content": "使用的食品原料、食品添加剂、食品相关产品的品种与索证索票、进货查验记录内容一致。",
        "isKey": true,
        "categorySeq": 4,
        "categoryName": "生产过程控制",
        "location": "配料间 / 生产加工车间流水线",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场抽查本月采购的面粉、食用植物油、包装膜，供货方营业执照、生产许可证及批次出厂检验合格报告索取齐全，台账完整。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_4_2",
        "itemNo": "*4.2",
        "content": "建立和保存生产投料记录，包括投料品名、生产日期或批号、使用数量等。",
        "isKey": true,
        "categorySeq": 4,
        "categoryName": "生产过程控制",
        "location": "配料间 / 生产加工车间流水线",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场调取批生产投料记录，配料称量数据与产品配方严格对应，双人复核签字，品名、批号及使用数量清晰可追溯。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_4_3",
        "itemNo": "*4.3",
        "content": "未发现使用非食品原料、食品添加剂以外的化学物质、回收食品、超过保质期与不符合食品安全标准的食品原料和食品添加剂投入生产。",
        "isKey": true,
        "categorySeq": 4,
        "categoryName": "生产过程控制",
        "location": "配料间 / 生产加工车间流水线",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场巡查原料库、投料间及暂存区，所有原辅料均在保质期内且标识规范，未发现回收食品、非食用物质及变质原料。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_4_4",
        "itemNo": "*4.4",
        "content": "未发现超范围、超限量使用食品添加剂的情况。",
        "isKey": true,
        "categorySeq": 4,
        "categoryName": "生产过程控制",
        "location": "配料间 / 生产加工车间流水线",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "食品添加剂严格实行‘专人采购、专人保管、专人领用、专库存储、专用称量、专人复核、专用台账’五专管理，使用品种与限量符合 GB 2760。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_4_5",
        "itemNo": "*4.5",
        "content": "生产或使用的新食品原料，限定于国务院卫生行政部门公吿的新食品原料范围内。",
        "isKey": true,
        "categorySeq": 4,
        "categoryName": "生产过程控制",
        "location": "配料间 / 生产加工车间流水线",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_4_6",
        "itemNo": "*4.6",
        "content": "未发现使用药品生产食品，未发现仅用于保健食品的原料生产保健食品以外的食品。",
        "isKey": true,
        "categorySeq": 4,
        "categoryName": "生产过程控制",
        "location": "配料间 / 生产加工车间流水线",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_4_7",
        "itemNo": "4.7",
        "content": "生产记录中的生产工艺和参数与准予食品生产许可时保持一致。",
        "isKey": false,
        "categorySeq": 4,
        "categoryName": "生产过程控制",
        "location": "配料间 / 生产加工车间流水线",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_4_8",
        "itemNo": "4.8",
        "content": "建立和保存生产加工过程关键控制点的控制情况记录。",
        "isKey": false,
        "categorySeq": 4,
        "categoryName": "生产过程控制",
        "location": "配料间 / 生产加工车间流水线",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_4_9",
        "itemNo": "4.9",
        "content": "生产现场未发现人流、物流交叉污染。",
        "isKey": false,
        "categorySeq": 4,
        "categoryName": "生产过程控制",
        "location": "配料间 / 生产加工车间流水线",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_4_10",
        "itemNo": "4.10",
        "content": "未发现待加工食品与直接入口食品、原料与成品交叉污染。",
        "isKey": false,
        "categorySeq": 4,
        "categoryName": "生产过程控制",
        "location": "配料间 / 生产加工车间流水线",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_4_11",
        "itemNo": "4.11",
        "content": "有温、湿度等生产环境监测要求的，定期进行监测并记录。",
        "isKey": false,
        "categorySeq": 4,
        "categoryName": "生产过程控制",
        "location": "配料间 / 生产加工车间流水线",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_4_12",
        "itemNo": "4.12",
        "content": "工作人员穿戴工作衣帽，洗手消毒后进入生产车间。生产车间内未发现与生产无关的个人用品或者其他与生产不相关物品。",
        "isKey": false,
        "categorySeq": 4,
        "categoryName": "生产过程控制",
        "location": "配料间 / 生产加工车间流水线",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "更衣室内配备足够数量的衣柜与紫外消毒灯；洗手池配备非手动感应水龙头、洗手液、自动热风干手器及 75% 酒精消毒喷雾，运行正常。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现 1 号更衣室洗手池感应龙头出水异常，洗手液瓶已空未及时补充，干手纸巾盒缺纸。建议：立即修复感应龙头，定人定时巡查并补充洗手消毒耗材。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_4_13",
        "itemNo": "4.13",
        "content": "食品生产加工用水的水质符合规定要求并有检测报告，与其他不与食品接触的用水以完全分离的管路输送。",
        "isKey": false,
        "categorySeq": 4,
        "categoryName": "生产过程控制",
        "location": "配料间 / 生产加工车间流水线",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "提供市政供水检测报告及企业自建净水系统检测合格报告，检测指标符合生活饮用水卫生标准 GB 5749，管道标识明确。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_4_14",
        "itemNo": "4.14",
        "content": "食品添加剂生产使用的原料和生产工艺符合产品标准规定。复配食品添加剂配方发生变化的，按规定报告。",
        "isKey": false,
        "categorySeq": 4,
        "categoryName": "生产过程控制",
        "location": "配料间 / 生产加工车间流水线",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "食品添加剂严格实行‘专人采购、专人保管、专人领用、专库存储、专用称量、专人复核、专用台账’五专管理，使用品种与限量符合 GB 2760。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_4_15",
        "itemNo": "*T.3",
        "content": "按照经特殊食品注册或备案的产品配方、生产工艺等技术要求组织生产。",
        "isKey": true,
        "categorySeq": 4,
        "categoryName": "生产过程控制",
        "location": "配料间 / 生产加工车间流水线",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "经核查，企业未生产保健食品或婴幼儿配方食品等特殊食品，生产台账与备案品类一致，属于合理项。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_4_16",
        "itemNo": "*T.4",
        "content": "批生产记录真实、完整、可追溯，批生产记录中的生产工艺和参数等与工艺规程和有关制度要求一致。",
        "isKey": true,
        "categorySeq": 4,
        "categoryName": "生产过程控制",
        "location": "配料间 / 生产加工车间流水线",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "企业接入市监食品安全追溯系统，纸质批生产记录与电子追溯系统数据完全对应，实现从原料采购到成品出库闭环溯源。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_4_17",
        "itemNo": "T.5",
        "content": "原料、食品添加剂实际使用量与注册或备案的配方和批生产记录中的使用量一致。",
        "isKey": false,
        "categorySeq": 4,
        "categoryName": "生产过程控制",
        "location": "配料间 / 生产加工车间流水线",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "食品添加剂严格实行‘专人采购、专人保管、专人领用、专库存储、专用称量、专人复核、专用台账’五专管理，使用品种与限量符合 GB 2760。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_4_18",
        "itemNo": "T.6",
        "content": "保健食品原料提取物或原料前处理符合要求。",
        "isKey": false,
        "categorySeq": 4,
        "categoryName": "生产过程控制",
        "location": "配料间 / 生产加工车间流水线",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      }
    ]
  },
  {
    "seq": 5,
    "name": "委托生产",
    "location": "质量管理部 / 合同档案室",
    "itemCount": 5,
    "keyCount": 1,
    "items": [
      {
        "id": "item_5_1",
        "itemNo": "*5.1",
        "content": "委托方、受托方具有有效证照，委托生产的食品、食品添加剂符合法律、法规、食品安全标准等规定。",
        "isKey": true,
        "categorySeq": 5,
        "categoryName": "委托生产",
        "location": "质量管理部 / 合同档案室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "食品添加剂严格实行‘专人采购、专人保管、专人领用、专库存储、专用称量、专人复核、专用台账’五专管理，使用品种与限量符合 GB 2760。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_5_2",
        "itemNo": "5.2",
        "content": "签订委托生产合同，约定委托生产的食品品种、委托期限等内容。",
        "isKey": false,
        "categorySeq": 5,
        "categoryName": "委托生产",
        "location": "质量管理部 / 合同档案室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_5_3",
        "itemNo": "5.3",
        "content": "有委托方对受托方生产行为进行监督的记录。",
        "isKey": false,
        "categorySeq": 5,
        "categoryName": "委托生产",
        "location": "质量管理部 / 合同档案室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_5_4",
        "itemNo": "5.4",
        "content": "委托生产的食品标签清晰标注委托方、受托方的名称、地址、联系方式等信息。",
        "isKey": false,
        "categorySeq": 5,
        "categoryName": "委托生产",
        "location": "质量管理部 / 合同档案室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "抽取在产成品外包装核验，食品名称、配料表、生产日期、保质期、贮存条件、营养成分表及生产许可证号标注规范合规。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】抽查待贴标签样品，配料表中复合调味料未完全展开标示原始配料。建议：暂停该批次包装，核实供应商配方后印制合规标签。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_5_5",
        "itemNo": "T.7",
        "content": "委托方持有保健食品注册证书或注册转备案凭证，受托方具备相应的生产能力且能完成生产委托品种的全部生产过程。",
        "isKey": false,
        "categorySeq": 5,
        "categoryName": "委托生产",
        "location": "质量管理部 / 合同档案室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      }
    ]
  },
  {
    "seq": 6,
    "name": "产品检验",
    "location": "企业化验室 / 留样室",
    "itemCount": 6,
    "keyCount": 3,
    "items": [
      {
        "id": "item_6_1",
        "itemNo": "6.1",
        "content": "企业自检的，具备与所检项目适应的检验室和检验能力，有检验相关设备及化学试剂，检验仪器按期检定或校准。",
        "isKey": false,
        "categorySeq": 6,
        "categoryName": "产品检验",
        "location": "企业化验室 / 留样室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "自检化验室配备天平、培养箱、显微镜等仪器，抽查出厂成品检验原始记录，菌落总数、净含量及理化指标检验真实规范，合格方予出厂。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_6_2",
        "itemNo": "6.2",
        "content": "不能自检的，委托有资质的检验机构进行检验。",
        "isKey": false,
        "categorySeq": 6,
        "categoryName": "产品检验",
        "location": "企业化验室 / 留样室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核验企业食品生产许可证原件（SC10653011100888），许可明细包含当前生产类别，在有效期内，住所及法定代表人与营业执照一致。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_6_3",
        "itemNo": "*6.3",
        "content": "有与生产产品相应的食品安全标准文本，按照食品安全标准规定进行检验。",
        "isKey": true,
        "categorySeq": 6,
        "categoryName": "产品检验",
        "location": "企业化验室 / 留样室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "自检化验室配备天平、培养箱、显微镜等仪器，抽查出厂成品检验原始记录，菌落总数、净含量及理化指标检验真实规范，合格方予出厂。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_6_4",
        "itemNo": "*6.4",
        "content": "建立和保存原始检验数据和检验报告记录，检验记录真实、完整，保存期限符合规定要求。",
        "isKey": true,
        "categorySeq": 6,
        "categoryName": "产品检验",
        "location": "企业化验室 / 留样室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "自检化验室配备天平、培养箱、显微镜等仪器，抽查出厂成品检验原始记录，菌落总数、净含量及理化指标检验真实规范，合格方予出厂。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_6_5",
        "itemNo": "6.5",
        "content": "按规定时限保存检验留存样品并记录留样情况。",
        "isKey": false,
        "categorySeq": 6,
        "categoryName": "产品检验",
        "location": "企业化验室 / 留样室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "自检化验室配备天平、培养箱、显微镜等仪器，抽查出厂成品检验原始记录，菌落总数、净含量及理化指标检验真实规范，合格方予出厂。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_6_6",
        "itemNo": "*T.8",
        "content": "对出厂的婴幼儿配方食品、特殊医学用途婴儿配方食品等按照要求批批全项目自行检验，每年对全项目检验能力进行验证。",
        "isKey": true,
        "categorySeq": 6,
        "categoryName": "产品检验",
        "location": "企业化验室 / 留样室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "自检化验室配备天平、培养箱、显微镜等仪器，抽查出厂成品检验原始记录，菌落总数、净含量及理化指标检验真实规范，合格方予出厂。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      }
    ]
  },
  {
    "seq": 7,
    "name": "贮存及交付控制",
    "location": "常温库 / 冷藏保鲜库 / 发货区",
    "itemCount": 6,
    "keyCount": 1,
    "items": [
      {
        "id": "item_7_1",
        "itemNo": "7.1",
        "content": "食品原料、食品相关产品的贮存有专人管理，贮存条件符合要求。",
        "isKey": false,
        "categorySeq": 7,
        "categoryName": "贮存及交付控制",
        "location": "常温库 / 冷藏保鲜库 / 发货区",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "原辅料库与成品库通风干燥，物品分类码放并离地离墙 20cm 以上，货位卡信息与实物相符，冷库温度监控曲线正常。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】原料仓库 B 区部分面粉托盘直接靠墙堆放，离墙间距不足 10cm，且温湿度记录表最近两天未签字更新。建议：按照 GB 14881 规范调整原料堆垛间距（离地离墙≥10cm），补全日常巡查温湿度记录。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_7_2",
        "itemNo": "7.2",
        "content": "食品添加剂专库或专区贮存，明显标示，专人管理。",
        "isKey": false,
        "categorySeq": 7,
        "categoryName": "贮存及交付控制",
        "location": "常温库 / 冷藏保鲜库 / 发货区",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "食品添加剂严格实行‘专人采购、专人保管、专人领用、专库存储、专用称量、专人复核、专用台账’五专管理，使用品种与限量符合 GB 2760。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】原料仓库 B 区部分面粉托盘直接靠墙堆放，离墙间距不足 10cm，且温湿度记录表最近两天未签字更新。建议：按照 GB 14881 规范调整原料堆垛间距（离地离墙≥10cm），补全日常巡查温湿度记录。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_7_3",
        "itemNo": "7.3",
        "content": "不合格品在划定区域存放，具有明显标示。",
        "isKey": false,
        "categorySeq": 7,
        "categoryName": "贮存及交付控制",
        "location": "常温库 / 冷藏保鲜库 / 发货区",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "设立专门的不合格品隔离区并悬挂警示标牌，处置台账完备；具备食品召回管理制度与演练记录。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_7_4",
        "itemNo": "7.4",
        "content": "根据产品特点建立和执行相适应的贮存、运输及交付控制制度和记录。",
        "isKey": false,
        "categorySeq": 7,
        "categoryName": "贮存及交付控制",
        "location": "常温库 / 冷藏保鲜库 / 发货区",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "原辅料库与成品库通风干燥，物品分类码放并离地离墙 20cm 以上，货位卡信息与实物相符，冷库温度监控曲线正常。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】原料仓库 B 区部分面粉托盘直接靠墙堆放，离墙间距不足 10cm，且温湿度记录表最近两天未签字更新。建议：按照 GB 14881 规范调整原料堆垛间距（离地离墙≥10cm），补全日常巡查温湿度记录。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_7_5",
        "itemNo": "7.5",
        "content": "仓库温湿度符合要求。",
        "isKey": false,
        "categorySeq": 7,
        "categoryName": "贮存及交付控制",
        "location": "常温库 / 冷藏保鲜库 / 发货区",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "原辅料库与成品库通风干燥，物品分类码放并离地离墙 20cm 以上，货位卡信息与实物相符，冷库温度监控曲线正常。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】原料仓库 B 区部分面粉托盘直接靠墙堆放，离墙间距不足 10cm，且温湿度记录表最近两天未签字更新。建议：按照 GB 14881 规范调整原料堆垛间距（离地离墙≥10cm），补全日常巡查温湿度记录。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_7_6",
        "itemNo": "*7.6",
        "content": "有出厂记录，如实记录食品的名称、规格、数量、生产日期或者生产批号、检验合格证明、销售日期以及购货者名称、地址、联系方式等内容。",
        "isKey": true,
        "categorySeq": 7,
        "categoryName": "贮存及交付控制",
        "location": "常温库 / 冷藏保鲜库 / 发货区",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "自检化验室配备天平、培养箱、显微镜等仪器，抽查出厂成品检验原始记录，菌落总数、净含量及理化指标检验真实规范，合格方予出厂。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      }
    ]
  },
  {
    "seq": 8,
    "name": "不合格食品管理和食品召回",
    "location": "不合格品专区 / 召回处置区",
    "itemCount": 4,
    "keyCount": 2,
    "items": [
      {
        "id": "item_8_1",
        "itemNo": "8.1",
        "content": "建立和保存不合格品的处置记录，不合格品的批次、数量应与记录一致。",
        "isKey": false,
        "categorySeq": 8,
        "categoryName": "不合格食品管理和食品召回",
        "location": "不合格品专区 / 召回处置区",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "设立专门的不合格品隔离区并悬挂警示标牌，处置台账完备；具备食品召回管理制度与演练记录。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_8_2",
        "itemNo": "*8.2",
        "content": "实施不安全食品的召回，召回和处理情况向所在地市场监管部门报告。",
        "isKey": true,
        "categorySeq": 8,
        "categoryName": "不合格食品管理和食品召回",
        "location": "不合格品专区 / 召回处置区",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "设立专门的不合格品隔离区并悬挂警示标牌，处置台账完备；具备食品召回管理制度与演练记录。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_8_3",
        "itemNo": "8.3",
        "content": "有召回计划、公告等相应记录；召回食品有处置记录。",
        "isKey": false,
        "categorySeq": 8,
        "categoryName": "不合格食品管理和食品召回",
        "location": "不合格品专区 / 召回处置区",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "设立专门的不合格品隔离区并悬挂警示标牌，处置台账完备；具备食品召回管理制度与演练记录。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_8_4",
        "itemNo": "*8.4",
        "content": "有召回食品无害化处理、销毁等措施，未发现召回食品再次流入市场（对因标签存在瑕疵实施召回的除外）。",
        "isKey": true,
        "categorySeq": 8,
        "categoryName": "不合格食品管理和食品召回",
        "location": "不合格品专区 / 召回处置区",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "设立专门的不合格品隔离区并悬挂警示标牌，处置台账完备；具备食品召回管理制度与演练记录。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】抽查待贴标签样品，配料表中复合调味料未完全展开标示原始配料。建议：暂停该批次包装，核实供应商配方后印制合规标签。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      }
    ]
  },
  {
    "seq": 9,
    "name": "标签和说明书",
    "location": "包材标签库 / 包装车间成品区",
    "itemCount": 6,
    "keyCount": 6,
    "items": [
      {
        "id": "item_9_1",
        "itemNo": "*9.1",
        "content": "预包装食品的包装有标签，标签标注的事项完整、真实。",
        "isKey": true,
        "categorySeq": 9,
        "categoryName": "标签和说明书",
        "location": "包材标签库 / 包装车间成品区",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "抽取在产成品外包装核验，食品名称、配料表、生产日期、保质期、贮存条件、营养成分表及生产许可证号标注规范合规。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】抽查待贴标签样品，配料表中复合调味料未完全展开标示原始配料。建议：暂停该批次包装，核实供应商配方后印制合规标签。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_9_2",
        "itemNo": "*9.2",
        "content": "未发现标注虚假生产日期或批号的情况。",
        "isKey": true,
        "categorySeq": 9,
        "categoryName": "标签和说明书",
        "location": "包材标签库 / 包装车间成品区",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_9_3",
        "itemNo": "*9.3",
        "content": "未发现转基因食品、辐照食品未按规定标示。",
        "isKey": true,
        "categorySeq": 9,
        "categoryName": "标签和说明书",
        "location": "包材标签库 / 包装车间成品区",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_9_4",
        "itemNo": "*9.4",
        "content": "食品添加剂标签载明“食品添加剂”字样，并标明贮存条件、生产者名称和地址、食品添加剂的使用范围、用量和使用方法。",
        "isKey": true,
        "categorySeq": 9,
        "categoryName": "标签和说明书",
        "location": "包材标签库 / 包装车间成品区",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "食品添加剂严格实行‘专人采购、专人保管、专人领用、专库存储、专用称量、专人复核、专用台账’五专管理，使用品种与限量符合 GB 2760。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】原料仓库 B 区部分面粉托盘直接靠墙堆放，离墙间距不足 10cm，且温湿度记录表最近两天未签字更新。建议：按照 GB 14881 规范调整原料堆垛间距（离地离墙≥10cm），补全日常巡查温湿度记录。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_9_5",
        "itemNo": "*9.5",
        "content": "未发现食品、食品添加剂的标签、说明书涉及疾病预防、治疗功能，未发现保健食品之外的食品标签、说明书涉及保健功能。",
        "isKey": true,
        "categorySeq": 9,
        "categoryName": "标签和说明书",
        "location": "包材标签库 / 包装车间成品区",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "食品添加剂严格实行‘专人采购、专人保管、专人领用、专库存储、专用称量、专人复核、专用台账’五专管理，使用品种与限量符合 GB 2760。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】抽查待贴标签样品，配料表中复合调味料未完全展开标示原始配料。建议：暂停该批次包装，核实供应商配方后印制合规标签。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_9_6",
        "itemNo": "*T.9",
        "content": "特殊食品标签、说明书内容与注册或备案的内容要求一致，符合相关法律法规要求。",
        "isKey": true,
        "categorySeq": 9,
        "categoryName": "标签和说明书",
        "location": "包材标签库 / 包装车间成品区",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "经核查，企业未生产保健食品或婴幼儿配方食品等特殊食品，生产台账与备案品类一致，属于合理项。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】抽查待贴标签样品，配料表中复合调味料未完全展开标示原始配料。建议：暂停该批次包装，核实供应商配方后印制合规标签。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      }
    ]
  },
  {
    "seq": 10,
    "name": "食品安全自查",
    "location": "食品安全总监办公室 / 会议室",
    "itemCount": 3,
    "keyCount": 2,
    "items": [
      {
        "id": "item_10_1",
        "itemNo": "10.1",
        "content": "建立食品安全自查制度，并定期对食品安全状况进行检查评价。",
        "isKey": false,
        "categorySeq": 10,
        "categoryName": "食品安全自查",
        "location": "食品安全总监办公室 / 会议室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "企业建立了每周食品安全自查机制，按规定落实‘日管控、周排查、月调度’工作制度，台账记录完整真实。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_10_2",
        "itemNo": "*10.2",
        "content": "对自查发现食品安全问题，立即采取整改、停止生产等措施，并按规定向所在地市场监督管理部门报告。",
        "isKey": true,
        "categorySeq": 10,
        "categoryName": "食品安全自查",
        "location": "食品安全总监办公室 / 会议室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "企业建立了每周食品安全自查机制，按规定落实‘日管控、周排查、月调度’工作制度，台账记录完整真实。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_10_3",
        "itemNo": "*T.10",
        "content": "定期对生产质量管理体系的运行情况进行自查，保证其有效运行，并向所在地县级人民政府市场监督管理部门提交自查报告，自查发现问题整改率达100%。",
        "isKey": true,
        "categorySeq": 10,
        "categoryName": "食品安全自查",
        "location": "食品安全总监办公室 / 会议室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "企业建立了每周食品安全自查机制，按规定落实‘日管控、周排查、月调度’工作制度，台账记录完整真实。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      }
    ]
  },
  {
    "seq": 11,
    "name": "从业人员管理",
    "location": "晨检区 / 更衣消毒间 / 培训室",
    "itemCount": 6,
    "keyCount": 3,
    "items": [
      {
        "id": "item_11_1",
        "itemNo": "*11.1",
        "content": "建立企业主要负责人全面负责食品安全工作制度，配备食品安全管理人员、食品安全专业技术人员。",
        "isKey": true,
        "categorySeq": 11,
        "categoryName": "从业人员管理",
        "location": "晨检区 / 更衣消毒间 / 培训室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_11_2",
        "itemNo": "11.2",
        "content": "有食品安全管理人员、食品安全专业技术人员培训和考核记录，未发现考核不合格人员上岗。",
        "isKey": false,
        "categorySeq": 11,
        "categoryName": "从业人员管理",
        "location": "晨检区 / 更衣消毒间 / 培训室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "设立专门的不合格品隔离区并悬挂警示标牌，处置台账完备；具备食品召回管理制度与演练记录。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_11_3",
        "itemNo": "*11.3",
        "content": "未发现聘用禁止从事食品安全管理的人员。",
        "isKey": true,
        "categorySeq": 11,
        "categoryName": "从业人员管理",
        "location": "晨检区 / 更衣消毒间 / 培训室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_11_4",
        "itemNo": "11.4",
        "content": "企业负责人在企业内部制度制定、过程控制、安全培训、安全检查以及食品安全事件或事故调查等环节履行了岗位职责并有记录。",
        "isKey": false,
        "categorySeq": 11,
        "categoryName": "从业人员管理",
        "location": "晨检区 / 更衣消毒间 / 培训室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_11_5",
        "itemNo": "*11.5",
        "content": "建立并执行从业人员健康管理制度，从事接触直接入口食品工作的人员具备有效健康证明，符合相关规定。",
        "isKey": true,
        "categorySeq": 11,
        "categoryName": "从业人员管理",
        "location": "晨检区 / 更衣消毒间 / 培训室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核对在岗人员名单与健康证明档案，接触直接入口食品的 32 名员工健康证均在有效期内，每日晨检记录完整无异常。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】抽查包装车间在岗员工中，有 1 名新入职操作工健康证明将于次日到期，尚未提供体检预约单。建议：立即安排该员工离岗体检，取得合格证明后方可复岗。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_11_6",
        "itemNo": "11.6",
        "content": "有从业人员食品安全知识培训制度，并有相关培训记录。",
        "isKey": false,
        "categorySeq": 11,
        "categoryName": "从业人员管理",
        "location": "晨检区 / 更衣消毒间 / 培训室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      }
    ]
  },
  {
    "seq": 12,
    "name": "信息记录和追溯",
    "location": "追溯系统控制室 / 纸质档案柜",
    "itemCount": 3,
    "keyCount": 0,
    "items": [
      {
        "id": "item_12_1",
        "itemNo": "12.1",
        "content": "建立并实施食品安全追溯制度，并有相应记录。",
        "isKey": false,
        "categorySeq": 12,
        "categoryName": "信息记录和追溯",
        "location": "追溯系统控制室 / 纸质档案柜",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "企业接入市监食品安全追溯系统，纸质批生产记录与电子追溯系统数据完全对应，实现从原料采购到成品出库闭环溯源。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_12_2",
        "itemNo": "12.2",
        "content": "未发现食品安全追溯信息记录不真实、不准确等情况。",
        "isKey": false,
        "categorySeq": 12,
        "categoryName": "信息记录和追溯",
        "location": "追溯系统控制室 / 纸质档案柜",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "企业接入市监食品安全追溯系统，纸质批生产记录与电子追溯系统数据完全对应，实现从原料采购到成品出库闭环溯源。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_12_3",
        "itemNo": "12.3",
        "content": "建立信息化食品安全追溯体系的，电子记录信息与纸质记录信息保持一致。",
        "isKey": false,
        "categorySeq": 12,
        "categoryName": "信息记录和追溯",
        "location": "追溯系统控制室 / 纸质档案柜",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "企业接入市监食品安全追溯系统，纸质批生产记录与电子追溯系统数据完全对应，实现从原料采购到成品出库闭环溯源。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      }
    ]
  },
  {
    "seq": 13,
    "name": "食品安全事故处置",
    "location": "应急处置物资柜 / 安保室",
    "itemCount": 3,
    "keyCount": 1,
    "items": [
      {
        "id": "item_13_1",
        "itemNo": "13.1",
        "content": "有定期排查食品安全风险隐患的记录。",
        "isKey": false,
        "categorySeq": 13,
        "categoryName": "食品安全事故处置",
        "location": "应急处置物资柜 / 安保室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_13_2",
        "itemNo": "13.2",
        "content": "有食品安全处置方案，并定期检查食品安全防范措施落实情况，及时消除食品安全隐患。",
        "isKey": false,
        "categorySeq": 13,
        "categoryName": "食品安全事故处置",
        "location": "应急处置物资柜 / 安保室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      },
      {
        "id": "item_13_3",
        "itemNo": "*13.3",
        "content": "发生食品安全事故的，对导致或者可能导致食品安全事故的食品及原料、工具、设备、设施等，立即采取封存等控制措施，并向事故发生地市场监督管理部门报告。",
        "isKey": true,
        "categorySeq": 13,
        "categoryName": "食品安全事故处置",
        "location": "应急处置物资柜 / 安保室",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "现场核查记录完备，相关设施设备运行良好，执行记录规范完整，符合食品安全监管要求。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "non_compliant",
          "label": "不符合",
          "risk": "高风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      }
    ]
  },
  {
    "seq": 14,
    "name": "前次监督检查发现问题整改情况",
    "location": "前次整改台账档案 / 整改现场",
    "itemCount": 1,
    "keyCount": 0,
    "items": [
      {
        "id": "item_14_1",
        "itemNo": "14.1",
        "content": "对前次监督检查发现的问题完成整改。",
        "isKey": false,
        "categorySeq": 14,
        "categoryName": "前次监督检查发现问题整改情况",
        "location": "前次整改台账档案 / 整改现场",
        "presetPass": {
          "status": "compliant",
          "label": "符合",
          "risk": "低风险",
          "finding": "针对前次检查指出的‘2号更衣室洗手液未及时补充’问题，已全部整改到位并形成整改闭环复查报告。",
          "suggestion": "现场符合食品安全国家标准及日常检查规范，维持良好运行。"
        },
        "presetIssue": {
          "status": "warning",
          "label": "轻微隐患",
          "risk": "中风险",
          "finding": "【发现隐患】现场检查发现该项存在轻微执行偏差，未严格按照操作规程执行。建议：责令企业限期3日内完成整改，并向市场监督管理所提交整改报告。",
          "suggestion": "责令企业限期 3 个工作日内整改完毕，并将整改复查照片报监管部门闭环销号。"
        }
      }
    ]
  }
];

export const ALL_INSPECTION_ITEMS: InspectionItem[] = FOOD_INSPECTION_CATEGORIES.flatMap(c => c.items);
