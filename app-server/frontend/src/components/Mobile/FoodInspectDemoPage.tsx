import React, { useState, useEffect, useRef } from 'react';
import { 
  Camera, 
  Upload, 
  AlertTriangle, 
  MinusCircle, 
  FileText, 
  ChevronRight, 
  ChevronLeft, 
  Trash2, 
  RotateCcw, 
  Sparkles, 
  ShieldCheck, 
  Printer, 
  ZoomIn, 
  Check, 
  X, 
  Clock, 
  MapPin, 
  FileCheck2, 
  ChevronDown, 
  ChevronUp 
} from 'lucide-react';
import { 
  FOOD_INSPECTION_CATEGORIES, 
  ALL_INSPECTION_ITEMS, 
  type InspectionItem, 
  type EvaluationRecord 
} from '../../data/foodInspectionData';
import { getSamplePhotoForItem } from '../../data/samplePhotos';

const STORAGE_KEY = 'food_inspect_demo_data_v2';

export default function FoodInspectDemoPage() {
  const [activeCategorySeq, setActiveCategorySeq] = useState<number>(1);
  const [evaluations, setEvaluations] = useState<Record<string, EvaluationRecord>>({});
  const [scanningItems, setScanningItems] = useState<Record<string, boolean>>({});
  const [currentItemForUpload, setCurrentItemForUpload] = useState<InspectionItem | null>(null);
  const [lightboxImageUrl, setLightboxImageUrl] = useState<string | null>(null);
  const [isSummaryModalOpen, setIsSummaryModalOpen] = useState(false);
  const [isHeaderCollapsed, setIsHeaderCollapsed] = useState(false);
  const [filterMode, setFilterMode] = useState<'all' | 'key_only' | 'pending' | 'evaluated'>('all');

  // 企业检查基础告知信息 (可在线编辑)
  const [enterpriseInfo, setEnterpriseInfo] = useState({
    name: '云南七彩高原绿色食品有限公司',
    address: '昆明市经开区经邮路18号现代食品工业园',
    scNo: 'SC10653011100888',
    inspectors: '李建国、张志华',
    inspectorIds: '530100234、530100235',
    inspectDate: new Date().toISOString().split('T')[0],
    inspectPlace: '生产一车间、原辅料库、化验室、包装车间',
    noticeStatus: '已出示执法证件，告知申请回避权利，被检查单位确认无需回避。'
  });

  const cameraInputRef = useRef<HTMLInputElement>(null);
  const galleryInputRef = useRef<HTMLInputElement>(null);
  const categoryScrollRef = useRef<HTMLDivElement>(null);

  // 初始化加载本地持久化数据
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.evaluations) setEvaluations(parsed.evaluations);
        if (parsed.enterpriseInfo) setEnterpriseInfo(parsed.enterpriseInfo);
      }
    } catch (e) {
      console.warn('读取本地检查记录失败:', e);
    }
  }, []);

  // 持久化保存
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        evaluations,
        enterpriseInfo
      }));
    } catch (e) {
      console.warn('保存本地检查记录失败:', e);
    }
  }, [evaluations, enterpriseInfo]);

  // 当前选中大类
  const currentCategory = FOOD_INSPECTION_CATEGORIES.find(c => c.seq === activeCategorySeq) || FOOD_INSPECTION_CATEGORIES[0];

  // 全局统计
  const totalItemsCount = ALL_INSPECTION_ITEMS.length;
  const keyItemsCount = ALL_INSPECTION_ITEMS.filter(it => it.isKey).length;
  const evaluatedCount = Object.keys(evaluations).length;
  const compliantCount = Object.values(evaluations).filter(e => e.status === 'compliant').length;
  const warningCount = Object.values(evaluations).filter(e => e.status === 'warning').length;
  const nonCompliantCount = Object.values(evaluations).filter(e => e.status === 'non_compliant').length;
  const progressPercent = Math.round((evaluatedCount / totalItemsCount) * 100);

  // 触发拍照采样
  const handleTriggerCamera = (item: InspectionItem) => {
    setCurrentItemForUpload(item);
    if (cameraInputRef.current) {
      cameraInputRef.current.value = '';
      cameraInputRef.current.click();
    }
  };

  // 触发相册选择
  const handleTriggerGallery = (item: InspectionItem) => {
    setCurrentItemForUpload(item);
    if (galleryInputRef.current) {
      galleryInputRef.current.value = '';
      galleryInputRef.current.click();
    }
  };

  // 处理文件上传事件 (拍照/相册)
  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0 || !currentItemForUpload) return;

    const file = files[0];
    const item = currentItemForUpload;
    const itemNo = item.itemNo;

    // 0ms 本地即时预览
    const localUrl = URL.createObjectURL(file);

    // 模拟 1.2s 视觉识别扫描特效
    setScanningItems(prev => ({ ...prev, [itemNo]: true }));

    // 默认预置为合规评定 (并提供按钮一键切换隐患模式)
    const preset = item.presetPass;
    const record: EvaluationRecord = {
      itemNo,
      photoUrl: localUrl,
      photoName: file.name,
      evaluatedAt: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      status: preset.status,
      finding: preset.finding,
      suggestion: preset.suggestion,
      risk: preset.risk,
      isAiEvaluated: true,
      isCustomModified: false
    };

    setEvaluations(prev => ({ ...prev, [itemNo]: record }));

    // 异步尝试上传到服务端以持久化留存 (失败不影响本地 Demo 运行)
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('item_no', itemNo);
      const res = await fetch('/api/mobile/demo-inspect-upload', {
        method: 'POST',
        body: formData
      });
      if (res.ok) {
        const json = await res.json();
        if (json.url) {
          setEvaluations(prev => ({
            ...prev,
            [itemNo]: {
              ...prev[itemNo],
              photoUrl: json.url
            }
          }));
        }
      }
    } catch (err) {
      console.warn('后端图片持久化可选服务跳过:', err);
    }

    setTimeout(() => {
      setScanningItems(prev => ({ ...prev, [itemNo]: false }));
    }, 1200);
  };

  // 一键载入预置演示样本照 (合规模式 vs 隐患模式)
  const handleLoadPresetSample = (item: InspectionItem, isIssue: boolean = false) => {
    const itemNo = item.itemNo;
    const samplePhoto = getSamplePhotoForItem(item.categorySeq, item.itemNo, isIssue);
    const preset = isIssue ? item.presetIssue : item.presetPass;

    setScanningItems(prev => ({ ...prev, [itemNo]: true }));

    const record: EvaluationRecord = {
      itemNo,
      photoUrl: samplePhoto,
      photoName: isIssue ? '现场发现隐患取证.jpg' : '现场规范点检采样.jpg',
      evaluatedAt: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      status: preset.status,
      finding: preset.finding,
      suggestion: preset.suggestion,
      risk: preset.risk,
      isAiEvaluated: true,
      isCustomModified: false
    };

    setEvaluations(prev => ({ ...prev, [itemNo]: record }));

    setTimeout(() => {
      setScanningItems(prev => ({ ...prev, [itemNo]: false }));
    }, 1000);
  };

  // 手动修改评定状态
  const handleUpdateStatus = (itemNo: string, newStatus: EvaluationRecord['status']) => {
    const existing = evaluations[itemNo];
    if (!existing) return;

    let newRisk: EvaluationRecord['risk'] = '低风险';
    if (newStatus === 'non_compliant') newRisk = '高风险';
    else if (newStatus === 'warning') newRisk = '中风险';
    else if (newStatus === 'not_applicable') newRisk = '无风险';

    setEvaluations(prev => ({
      ...prev,
      [itemNo]: {
        ...prev[itemNo],
        status: newStatus,
        risk: newRisk,
        isCustomModified: true
      }
    }));
  };

  // 删除某项照片与评定
  const handleDeleteEvaluation = (itemNo: string) => {
    setEvaluations(prev => {
      const copy = { ...prev };
      delete copy[itemNo];
      return copy;
    });
  };

  // 批量一键演示填充（用于快速演讲展示）
  const handleQuickDemoFill = (onlyCurrentCategory: boolean = true) => {
    const targetItems = onlyCurrentCategory ? currentCategory.items : ALL_INSPECTION_ITEMS;
    const newEvals = { ...evaluations };

    targetItems.forEach(it => {
      // 故意让第2大类的 2.5 或 2.10 展示隐患，增强演示效果
      const makeIssue = (it.itemNo === '2.5' || it.itemNo === '2.10');
      const preset = makeIssue ? it.presetIssue : it.presetPass;
      newEvals[it.itemNo] = {
        itemNo: it.itemNo,
        photoUrl: getSamplePhotoForItem(it.categorySeq, it.itemNo, makeIssue),
        photoName: makeIssue ? '现场隐患取证.jpg' : '现场达标取证.jpg',
        evaluatedAt: '14:20:00',
        status: preset.status,
        finding: preset.finding,
        suggestion: preset.suggestion,
        risk: preset.risk,
        isAiEvaluated: true,
        isCustomModified: false
      };
    });

    setEvaluations(newEvals);
  };

  // 清空所有演示记录
  const handleResetAll = () => {
    if (window.confirm('确定要清空已记录的现场检查照片和评定数据吗？')) {
      setEvaluations({});
      localStorage.removeItem(STORAGE_KEY);
    }
  };

  // 过滤展示当前大类的条目
  const displayedItems = currentCategory.items.filter(item => {
    if (filterMode === 'key_only') return item.isKey;
    if (filterMode === 'pending') return !evaluations[item.itemNo];
    if (filterMode === 'evaluated') return !!evaluations[item.itemNo];
    return true;
  });

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col font-sans pb-24 select-none">
      {/* 隐藏的文件输入控件 */}
      <input 
        type="file" 
        ref={cameraInputRef} 
        accept="image/*" 
        capture="environment" 
        className="hidden" 
        onChange={handleFileChange}
      />
      <input 
        type="file" 
        ref={galleryInputRef} 
        accept="image/*" 
        className="hidden" 
        onChange={handleFileChange}
      />

      {/* ═══════════════════════════════════════════════════════════════
          1. 顶部专业政务导览条
         ═══════════════════════════════════════════════════════════════ */}
      <header className="sticky top-0 z-30 bg-slate-950/90 backdrop-blur-md border-b border-slate-800 px-4 py-3 shadow-md">
        <div className="max-w-xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center shadow-lg shadow-blue-500/20 text-white font-black text-sm">
              监
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-bold text-white tracking-wide">食品生产检查</h1>
                <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded">
                  /m2 Demo
                </span>
              </div>
              <p className="text-[11px] text-slate-400 truncate max-w-[200px]">
                {enterpriseInfo.name}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsSummaryModalOpen(true)}
              className="px-2.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 active:scale-95 text-white text-xs font-medium flex items-center gap-1 shadow-sm transition"
            >
              <FileCheck2 className="w-3.5 h-3.5" />
              <span>要点表</span>
            </button>
            <button
              onClick={() => setIsHeaderCollapsed(!isHeaderCollapsed)}
              className="p-1.5 rounded-lg bg-slate-800 text-slate-400 hover:text-white"
              title="切换企业信息"
            >
              {isHeaderCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </header>

      {/* ═══════════════════════════════════════════════════════════════
          2. 被检查单位及告知信息卡片 (表0告知页)
         ═══════════════════════════════════════════════════════════════ */}
      <div className="max-w-xl mx-auto w-full px-4 pt-3">
        {!isHeaderCollapsed && (
          <div className="bg-slate-800/80 border border-slate-700/80 rounded-xl p-3.5 shadow-sm text-xs space-y-2 mb-3 backdrop-blur-sm">
            <div className="flex items-start justify-between border-b border-slate-700/60 pb-2">
              <div className="space-y-0.5">
                <div className="text-[11px] text-slate-400 font-medium">被检查单位（表1-1 告知页）：</div>
                <div className="font-semibold text-slate-200 text-sm">{enterpriseInfo.name}</div>
                <div className="text-[11px] text-slate-400 flex items-center gap-1">
                  <MapPin className="w-3 h-3 text-slate-500 shrink-0" />
                  <span className="truncate">{enterpriseInfo.address}</span>
                </div>
              </div>
              <span className="px-2 py-0.5 rounded bg-blue-950/60 text-blue-300 border border-blue-800/60 text-[10px] shrink-0">
                SC许可证有效
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-[11px] pt-0.5 text-slate-300">
              <div>
                <span className="text-slate-400">检查人员：</span>
                <span className="font-medium">{enterpriseInfo.inspectors}</span>
              </div>
              <div>
                <span className="text-slate-400">检查日期：</span>
                <span>{enterpriseInfo.inspectDate}</span>
              </div>
              <div className="col-span-2 text-[10px] text-emerald-400/90 flex items-center gap-1 bg-emerald-950/30 px-2 py-1 rounded border border-emerald-800/30">
                <Check className="w-3 h-3 shrink-0" />
                <span>{enterpriseInfo.noticeStatus}</span>
              </div>
            </div>
          </div>
        )}

        {/* 总体进度指标卡 */}
        <div className="bg-gradient-to-r from-slate-800 to-slate-850 border border-slate-700 rounded-xl p-3 flex items-center justify-between shadow-sm">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-300 font-medium">检查进度 (共14大类·79项)</span>
              <span className="text-xs font-bold text-blue-400">{evaluatedCount} / {totalItemsCount}</span>
            </div>
            <div className="w-40 bg-slate-700 rounded-full h-2 overflow-hidden">
              <div 
                className="bg-gradient-to-r from-blue-500 to-emerald-400 h-2 rounded-full transition-all duration-300"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>

          <div className="flex items-center gap-3 text-right">
            <div>
              <div className="text-xs font-bold text-emerald-400">{compliantCount}</div>
              <div className="text-[10px] text-slate-400">符合</div>
            </div>
            {warningCount > 0 && (
              <div>
                <div className="text-xs font-bold text-amber-400">{warningCount}</div>
                <div className="text-[10px] text-slate-400">瑕疵</div>
              </div>
            )}
            {nonCompliantCount > 0 && (
              <div>
                <div className="text-xs font-bold text-red-400">{nonCompliantCount}</div>
                <div className="text-[10px] text-slate-400">不符合</div>
              </div>
            )}
            <div>
              <div className="text-xs font-bold text-indigo-400">{keyItemsCount}</div>
              <div className="text-[10px] text-slate-400">重点项★</div>
            </div>
          </div>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════
          3. 14 个大类横向滑动选项卡 (Swipeable Categories)
         ═══════════════════════════════════════════════════════════════ */}
      <div className="max-w-xl mx-auto w-full px-4 pt-3">
        <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5 px-0.5">
          <span>检查项目分类 (14个大类)</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleQuickDemoFill(true)}
              className="text-blue-400 hover:text-blue-300 text-[11px] flex items-center gap-0.5"
            >
              <Sparkles className="w-3 h-3" />
              <span>本类填样</span>
            </button>
            <span className="text-slate-600">|</span>
            <button
              onClick={() => handleQuickDemoFill(false)}
              className="text-amber-400 hover:text-amber-300 text-[11px]"
            >
              全部填样
            </button>
          </div>
        </div>

        <div 
          ref={categoryScrollRef}
          className="flex items-center gap-2 overflow-x-auto pb-2 scrollbar-none no-scrollbar touch-pan-x"
        >
          {FOOD_INSPECTION_CATEGORIES.map(cat => {
            const isActive = cat.seq === activeCategorySeq;
            const catEvaluated = cat.items.filter(it => !!evaluations[it.itemNo]).length;
            const hasIssue = cat.items.some(it => {
              const e = evaluations[it.itemNo];
              return e && (e.status === 'non_compliant' || e.status === 'warning');
            });
            const isCompleted = catEvaluated === cat.items.length;

            return (
              <button
                key={cat.seq}
                onClick={() => setActiveCategorySeq(cat.seq)}
                className={`flex-shrink-0 px-3 py-2 rounded-xl text-xs font-medium transition-all flex flex-col items-start gap-0.5 border ${
                  isActive 
                    ? 'bg-blue-600 text-white border-blue-500 shadow-md shadow-blue-500/20' 
                    : 'bg-slate-800 text-slate-300 border-slate-700/80 hover:bg-slate-750'
                }`}
              >
                <div className="flex items-center gap-1.5 w-full">
                  <span className={`w-4 h-4 rounded-full text-[10px] flex items-center justify-center font-bold ${
                    isActive ? 'bg-white/20 text-white' : 'bg-slate-700 text-slate-300'
                  }`}>
                    {cat.seq}
                  </span>
                  <span className="truncate max-w-[120px]">{cat.name}</span>
                  {hasIssue && (
                    <span className="w-1.5 h-1.5 rounded-full bg-red-400 ml-auto animate-pulse" />
                  )}
                </div>
                <div className="text-[10px] opacity-80 pl-5.5 flex items-center gap-1">
                  <span>{catEvaluated}/{cat.items.length}项</span>
                  {isCompleted && <span className="text-emerald-300">✓</span>}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════
          4. 当前大类标题与筛选
         ═══════════════════════════════════════════════════════════════ */}
      <div className="max-w-xl mx-auto w-full px-4 pt-2">
        <div className="bg-slate-800/50 border border-slate-700/60 rounded-xl p-3 mb-3 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 bg-blue-500/20 text-blue-300 border border-blue-500/30 text-[11px] rounded font-bold">
                第 {currentCategory.seq} 类
              </span>
              <h2 className="text-sm font-bold text-white">{currentCategory.name}</h2>
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5 flex items-center gap-1">
              <MapPin className="w-3 h-3 text-slate-500" />
              <span>检查场所：{currentCategory.location}</span>
            </p>
          </div>

          <div className="text-right text-xs">
            <span className="text-slate-400">重点项：</span>
            <span className="font-bold text-amber-400">{currentCategory.keyCount}</span>
            <span className="text-slate-500"> / {currentCategory.itemCount}</span>
          </div>
        </div>

        {/* 筛选模式切换 */}
        <div className="flex items-center justify-between mb-3 text-xs">
          <div className="flex items-center gap-1 bg-slate-800/90 p-0.5 rounded-lg border border-slate-700/70">
            <button
              onClick={() => setFilterMode('all')}
              className={`px-2 py-1 rounded text-[11px] ${filterMode === 'all' ? 'bg-blue-600 text-white font-medium' : 'text-slate-400'}`}
            >
              全部 ({currentCategory.items.length})
            </button>
            <button
              onClick={() => setFilterMode('key_only')}
              className={`px-2 py-1 rounded text-[11px] ${filterMode === 'key_only' ? 'bg-amber-600 text-white font-medium' : 'text-slate-400'}`}
            >
              ★ 重点项 ({currentCategory.keyCount})
            </button>
            <button
              onClick={() => setFilterMode('pending')}
              className={`px-2 py-1 rounded text-[11px] ${filterMode === 'pending' ? 'bg-slate-700 text-white font-medium' : 'text-slate-400'}`}
            >
              待查 ({currentCategory.items.filter(it => !evaluations[it.itemNo]).length})
            </button>
          </div>

          <div className="text-[11px] text-slate-400">
            共 {displayedItems.length} 项要点
          </div>
        </div>

        {/* ═══════════════════════════════════════════════════════════════
            5. 检查要点列表卡片 (包含拍照、上传、预置评价与评定修改)
           ═══════════════════════════════════════════════════════════════ */}
        <div className="space-y-3.5">
          {displayedItems.map(item => {
            const evalRecord = evaluations[item.itemNo];
            const isScanning = !!scanningItems[item.itemNo];
            const hasPhoto = !!evalRecord?.photoUrl;

            return (
              <div 
                key={item.id}
                className={`bg-slate-800/90 border rounded-xl overflow-hidden transition-all shadow-sm ${
                  evalRecord?.status === 'non_compliant' 
                    ? 'border-red-500/60 shadow-red-950/20' 
                    : evalRecord?.status === 'warning'
                    ? 'border-amber-500/60 shadow-amber-950/20'
                    : evalRecord?.status === 'compliant'
                    ? 'border-emerald-500/50'
                    : 'border-slate-700/80 hover:border-slate-600'
                }`}
              >
                {/* 要点头部 */}
                <div className="px-3.5 pt-3 pb-2 flex items-start justify-between gap-2 border-b border-slate-700/50">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-sm font-bold text-blue-400">
                      {item.itemNo}
                    </span>
                    {item.isKey ? (
                      <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[10px] font-bold flex items-center gap-0.5">
                        ★ 重点项
                      </span>
                    ) : (
                      <span className="px-1.5 py-0.5 rounded bg-slate-700 text-slate-300 text-[10px]">
                        一般项
                      </span>
                    )}
                    <span className="text-[10px] text-slate-400 flex items-center gap-0.5">
                      <MapPin className="w-2.5 h-2.5 text-slate-500" />
                      {item.location}
                    </span>
                  </div>

                  {evalRecord && (
                    <span className={`px-2 py-0.5 rounded text-[11px] font-bold flex items-center gap-1 ${
                      evalRecord.status === 'compliant'
                        ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                        : evalRecord.status === 'warning'
                        ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                        : evalRecord.status === 'non_compliant'
                        ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                        : 'bg-slate-700 text-slate-400'
                    }`}>
                      {evalRecord.status === 'compliant' && <Check className="w-3 h-3" />}
                      {evalRecord.status === 'warning' && <AlertTriangle className="w-3 h-3" />}
                      {evalRecord.status === 'non_compliant' && <X className="w-3 h-3" />}
                      <span>
                        {evalRecord.status === 'compliant' ? '符合' : 
                         evalRecord.status === 'warning' ? '瑕疵' : 
                         evalRecord.status === 'non_compliant' ? '不符合' : '合理缺项'}
                      </span>
                    </span>
                  )}
                </div>

                {/* 监督检查要求内容 */}
                <div className="p-3.5">
                  <p className="text-xs text-slate-200 leading-relaxed font-normal">
                    {item.content}
                  </p>

                  {/* 拍照与上传操作按钮组 (未拍照时醒目展示) */}
                  {!hasPhoto && (
                    <div className="mt-3 grid grid-cols-3 gap-2">
                      <button
                        onClick={() => handleTriggerCamera(item)}
                        className="py-2.5 px-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 active:scale-95 text-white rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 shadow-sm transition"
                      >
                        <Camera className="w-4 h-4" />
                        <span>现场拍照</span>
                      </button>

                      <button
                        onClick={() => handleTriggerGallery(item)}
                        className="py-2.5 px-2 bg-slate-700 hover:bg-slate-650 active:scale-95 text-slate-200 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition"
                      >
                        <Upload className="w-4 h-4" />
                        <span>相册上传</span>
                      </button>

                      <button
                        onClick={() => handleLoadPresetSample(item, false)}
                        className="py-2.5 px-2 bg-emerald-950/40 hover:bg-emerald-900/50 border border-emerald-700/50 active:scale-95 text-emerald-300 rounded-lg text-xs font-medium flex items-center justify-center gap-1 transition"
                        title="快速载入合规样本图"
                      >
                        <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
                        <span>填入合规样照</span>
                      </button>
                    </div>
                  )}

                  {/* 图片展示与评价区域 */}
                  {hasPhoto && (
                    <div className="mt-3 space-y-3">
                      {/* 取证照片预览 */}
                      <div className="relative rounded-lg overflow-hidden border border-slate-700 bg-slate-950 aspect-video max-h-48 flex items-center justify-center group">
                        <img 
                          src={evalRecord.photoUrl} 
                          alt="现场取证" 
                          className="w-full h-full object-cover"
                        />

                        {/* 水印与拍摄时间 */}
                        <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent p-2 flex items-center justify-between text-[10px] text-slate-300">
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3 text-blue-400" />
                            <span>取证时间：{evalRecord.evaluatedAt || '13:30'}</span>
                          </span>
                          <span className="text-slate-400">已存入检查底稿</span>
                        </div>

                        {/* 悬浮操作按钮 */}
                        <div className="absolute top-2 right-2 flex items-center gap-1.5">
                          <button
                            onClick={() => setLightboxImageUrl(evalRecord.photoUrl || null)}
                            className="p-1.5 rounded-md bg-black/60 hover:bg-black/80 text-white backdrop-blur-sm"
                            title="查看大图"
                          >
                            <ZoomIn className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleDeleteEvaluation(item.itemNo)}
                            className="p-1.5 rounded-md bg-red-950/80 hover:bg-red-800 text-red-200 border border-red-700/50 backdrop-blur-sm"
                            title="重拍或删除"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>

                        {/* 扫描动画中遮罩 */}
                        {isScanning && (
                          <div className="absolute inset-0 bg-slate-950/75 flex flex-col items-center justify-center backdrop-blur-sm z-10 animate-fade-in">
                            <div className="w-10 h-10 rounded-full border-2 border-blue-500 border-t-transparent animate-spin mb-2" />
                            <div className="text-xs font-bold text-blue-300 flex items-center gap-1">
                              <Sparkles className="w-3.5 h-3.5 animate-pulse" />
                              <span>AI 视觉扫描分析中...</span>
                            </div>
                            <div className="text-[10px] text-slate-400 mt-0.5">正在核验现场要点合规性</div>
                          </div>
                        )}
                      </div>

                      {/* 预置评价与现场研判详情卡片 */}
                      <div className="bg-slate-900/90 border border-slate-700/90 rounded-lg p-3 space-y-2.5">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-1.5 text-xs font-bold text-slate-200">
                            <ShieldCheck className="w-4 h-4 text-blue-400" />
                            <span>现场智能预置评定结论</span>
                          </div>

                          <div className="flex items-center gap-1.5 text-[10px]">
                            <span className="text-slate-400">风险等级：</span>
                            <span className={`font-bold ${
                              evalRecord.risk === '高风险' ? 'text-red-400' :
                              evalRecord.risk === '中风险' ? 'text-amber-400' : 'text-emerald-400'
                            }`}>
                              {evalRecord.risk}
                            </span>
                          </div>
                        </div>

                        {/* 评定结论一键快速选择栏 */}
                        <div className="grid grid-cols-4 gap-1.5">
                          <button
                            onClick={() => handleUpdateStatus(item.itemNo, 'compliant')}
                            className={`py-1 px-1.5 rounded text-[11px] font-semibold border flex items-center justify-center gap-1 transition ${
                              evalRecord.status === 'compliant'
                                ? 'bg-emerald-600 text-white border-emerald-500 shadow-sm'
                                : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-slate-200'
                            }`}
                          >
                            <Check className="w-3 h-3" />
                            <span>是(符合)</span>
                          </button>

                          <button
                            onClick={() => handleUpdateStatus(item.itemNo, 'warning')}
                            className={`py-1 px-1.5 rounded text-[11px] font-semibold border flex items-center justify-center gap-1 transition ${
                              evalRecord.status === 'warning'
                                ? 'bg-amber-600 text-white border-amber-500 shadow-sm'
                                : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-slate-200'
                            }`}
                          >
                            <AlertTriangle className="w-3 h-3" />
                            <span>基本符合</span>
                          </button>

                          <button
                            onClick={() => handleUpdateStatus(item.itemNo, 'non_compliant')}
                            className={`py-1 px-1.5 rounded text-[11px] font-semibold border flex items-center justify-center gap-1 transition ${
                              evalRecord.status === 'non_compliant'
                                ? 'bg-red-600 text-white border-red-500 shadow-sm'
                                : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-slate-200'
                            }`}
                          >
                            <X className="w-3 h-3" />
                            <span>否(不符)</span>
                          </button>

                          <button
                            onClick={() => handleUpdateStatus(item.itemNo, 'not_applicable')}
                            className={`py-1 px-1.5 rounded text-[11px] font-semibold border flex items-center justify-center gap-1 transition ${
                              evalRecord.status === 'not_applicable'
                                ? 'bg-slate-600 text-white border-slate-500 shadow-sm'
                                : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-slate-200'
                            }`}
                          >
                            <MinusCircle className="w-3 h-3" />
                            <span>合理缺项</span>
                          </button>
                        </div>

                        {/* 现场核查记录与评价事实陈述 */}
                        <div className="bg-slate-950/70 p-2.5 rounded border border-slate-800 text-[11px] leading-relaxed text-slate-300">
                          <span className="text-slate-400 font-semibold">【核查记录】</span>
                          {evalRecord.finding}
                        </div>

                        {/* 整改建议 (若存在隐患) */}
                        {evalRecord.status !== 'compliant' && evalRecord.status !== 'not_applicable' && (
                          <div className="bg-amber-950/40 p-2 rounded border border-amber-800/40 text-[11px] text-amber-200 leading-relaxed">
                            <span className="font-semibold text-amber-300">【处理建议】</span>
                            {evalRecord.suggestion}
                          </div>
                        )}

                        {/* 演示用：一键切换合规样本与违规隐患样本 */}
                        <div className="pt-1 flex items-center justify-between text-[10px] text-slate-400 border-t border-slate-800/80">
                          <span>演示样本切换：</span>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => handleLoadPresetSample(item, false)}
                              className="text-emerald-400 hover:underline"
                            >
                              载入合规样本
                            </button>
                            <span className="text-slate-600">|</span>
                            <button
                              onClick={() => handleLoadPresetSample(item, true)}
                              className="text-red-400 hover:underline font-medium"
                            >
                              载入隐患样本
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════
          6. 底部固定悬浮导航栏 (Prev/Next/Summary Report)
         ═══════════════════════════════════════════════════════════════ */}
      <footer className="fixed bottom-0 inset-x-0 z-30 bg-slate-950/95 backdrop-blur-lg border-t border-slate-800 px-4 py-2.5 shadow-2xl">
        <div className="max-w-xl mx-auto flex items-center justify-between gap-2">
          {/* 上一类 */}
          <button
            disabled={activeCategorySeq <= 1}
            onClick={() => {
              setActiveCategorySeq(prev => Math.max(1, prev - 1));
              categoryScrollRef.current?.scrollBy({ left: -100, behavior: 'smooth' });
            }}
            className="p-2 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-30 disabled:pointer-events-none active:scale-95 transition"
            title="上一大类"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>

          {/* 核心查看要点表汇总大按钮 */}
          <button
            onClick={() => setIsSummaryModalOpen(true)}
            className="flex-1 py-2.5 px-3 bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-600 hover:from-blue-500 hover:to-indigo-500 text-white rounded-xl text-xs font-bold flex items-center justify-center gap-2 shadow-lg shadow-blue-600/25 active:scale-98 transition"
          >
            <FileText className="w-4 h-4" />
            <span>查看《监督检查要点表》汇总</span>
            <span className="px-1.5 py-0.2 bg-white/20 text-white rounded text-[10px]">
              {evaluatedCount}/{totalItemsCount}
            </span>
          </button>

          {/* 下一类 */}
          <button
            disabled={activeCategorySeq >= FOOD_INSPECTION_CATEGORIES.length}
            onClick={() => {
              setActiveCategorySeq(prev => Math.min(FOOD_INSPECTION_CATEGORIES.length, prev + 1));
              categoryScrollRef.current?.scrollBy({ left: 100, behavior: 'smooth' });
            }}
            className="p-2 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-30 disabled:pointer-events-none active:scale-95 transition"
            title="下一大类"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </footer>

      {/* ═══════════════════════════════════════════════════════════════
          7. 图片放大预览 Lightbox 模态弹窗
         ═══════════════════════════════════════════════════════════════ */}
      {lightboxImageUrl && (
        <div 
          onClick={() => setLightboxImageUrl(null)}
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4 backdrop-blur-sm animate-fade-in"
        >
          <div className="relative max-w-lg w-full max-h-[90vh] flex flex-col items-center">
            <img 
              src={lightboxImageUrl} 
              alt="取证放大预览" 
              className="max-w-full max-h-[80vh] object-contain rounded-lg border border-slate-700 shadow-2xl" 
            />
            <button
              onClick={() => setLightboxImageUrl(null)}
              className="mt-4 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-full text-xs font-medium flex items-center gap-1.5 border border-slate-600 shadow-lg"
            >
              <X className="w-4 h-4" />
              <span>关闭预览</span>
            </button>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════
          8. 《食品生产经营监督检查要点表》（表1-1）官方格式汇总报告弹窗
         ═══════════════════════════════════════════════════════════════ */}
      {isSummaryModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-3 backdrop-blur-sm overflow-y-auto">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-xl max-h-[90vh] flex flex-col overflow-hidden shadow-2xl text-slate-200">
            {/* 报告头部 */}
            <div className="px-4 py-3 bg-gradient-to-r from-slate-950 via-slate-900 to-slate-950 border-b border-slate-800 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-xs">
                  表
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">食品生产企业监督检查要点表</h3>
                  <p className="text-[10px] text-slate-400">附件1 · 表1-1 · 检查记录底稿预览</p>
                </div>
              </div>
              <button
                onClick={() => setIsSummaryModalOpen(false)}
                className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* 报告主体内容 (仿真官方表格排版) */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
              {/* 企业信息与告知记录 */}
              <div className="border border-slate-700 rounded-lg p-3 bg-slate-950/60 space-y-2">
                <div className="font-bold text-slate-200 border-b border-slate-800 pb-1.5 text-xs flex justify-between">
                  <span>被检查单位基本信息</span>
                  <span className="text-blue-400 font-normal">日期：{enterpriseInfo.inspectDate}</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-300">
                  <div>被检查单位：<span className="text-white font-medium">{enterpriseInfo.name}</span></div>
                  <div>生产许可号：<span className="text-white font-mono">{enterpriseInfo.scNo}</span></div>
                  <div className="col-span-2">生产地址：<span className="text-slate-300">{enterpriseInfo.address}</span></div>
                  <div>检查人员：<span className="text-white">{enterpriseInfo.inspectors}</span></div>
                  <div>执法证号：<span className="text-white font-mono">{enterpriseInfo.inspectorIds}</span></div>
                </div>
                <div className="bg-slate-900 p-2 rounded text-[10px] text-slate-400 leading-normal border border-slate-800">
                  告知事项：监督检查人员依法出示执法证件并告知申请回避权利，被检查单位明确表示不申请回避。
                </div>
              </div>

              {/* 14 大类汇总统计表 */}
              <div className="border border-slate-700 rounded-lg overflow-hidden">
                <div className="bg-slate-800 px-3 py-2 font-bold text-xs text-slate-200 flex items-center justify-between">
                  <span>14 大类检查统计汇总 (共 {totalItemsCount} 项)</span>
                  <span className="text-emerald-400 font-mono text-[11px]">
                    已查 {evaluatedCount} / {totalItemsCount}
                  </span>
                </div>

                <div className="divide-y divide-slate-800 text-[11px] max-h-56 overflow-y-auto">
                  {FOOD_INSPECTION_CATEGORIES.map(cat => {
                    const catItems = cat.items;
                    const catEvals = catItems.map(it => evaluations[it.itemNo]).filter(Boolean);
                    const compCount = catEvals.filter(e => e.status === 'compliant').length;
                    const issueCount = catEvals.filter(e => e.status === 'warning' || e.status === 'non_compliant').length;

                    return (
                      <div key={cat.seq} className="px-3 py-2 flex items-center justify-between hover:bg-slate-850">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-slate-400 w-4">{cat.seq}.</span>
                          <span className="text-slate-200 font-medium truncate max-w-[170px]">{cat.name}</span>
                          <span className="text-[10px] text-slate-500">({cat.itemCount}项)</span>
                        </div>

                        <div className="flex items-center gap-2 text-right text-[10px]">
                          <span className="text-emerald-400">合规 {compCount}</span>
                          {issueCount > 0 ? (
                            <span className="px-1.5 py-0.5 rounded bg-red-950/70 text-red-300 border border-red-800/60 font-bold">
                              隐患 {issueCount}
                            </span>
                          ) : (
                            <span className="text-slate-500">无隐患</span>
                          )}
                          <span className="text-slate-300 font-mono">
                            {catEvals.length}/{cat.itemCount}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* 发现问题及不合格项清单 (对应表1-1中的‘发现问题食品类别’与‘评价’列) */}
              <div className="border border-slate-700 rounded-lg overflow-hidden">
                <div className="bg-slate-800 px-3 py-2 font-bold text-xs text-slate-200 flex items-center justify-between">
                  <span>发现问题与需整改要点清单</span>
                  <span className="text-amber-400 font-bold">
                    {warningCount + nonCompliantCount} 项
                  </span>
                </div>

                {warningCount + nonCompliantCount === 0 ? (
                  <div className="p-4 text-center text-slate-500 text-xs">
                    本次检查暂未发现不合格或需整改要点。
                  </div>
                ) : (
                  <div className="p-3 space-y-2 text-[11px]">
                    {Object.values(evaluations)
                      .filter(e => e.status === 'warning' || e.status === 'non_compliant')
                      .map(e => (
                        <div key={e.itemNo} className="bg-slate-950/80 p-2.5 rounded border border-red-900/40 space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="font-mono font-bold text-amber-400">要点 {e.itemNo}</span>
                            <span className="px-1.5 py-0.2 bg-red-950 text-red-300 rounded text-[10px]">
                              {e.status === 'non_compliant' ? '不符合' : '轻微瑕疵'}
                            </span>
                          </div>
                          <div className="text-slate-300 text-[11px]">{e.finding}</div>
                          <div className="text-amber-300/90 text-[10px]">{e.suggestion}</div>
                        </div>
                      ))}
                  </div>
                )}
              </div>

              {/* 检查结论与签字区 */}
              <div className="border border-slate-700 rounded-lg p-3 bg-slate-950/40 text-[11px] space-y-3">
                <div className="font-bold text-slate-200 border-b border-slate-800 pb-1 text-xs">
                  检查结果评定意见
                </div>
                <p className="text-slate-300 leading-relaxed">
                  经对 {enterpriseInfo.name} 开展监督检查，共核验 {evaluatedCount} 项。
                  其中符合 {compliantCount} 项，发现问题瑕疵 {warningCount + nonCompliantCount} 项。
                  {warningCount + nonCompliantCount > 0 
                    ? '根据《食品生产经营监督检查管理办法》，责令企业针对发现问题限期于3个工作日内完成整改并提交整改复查材料。'
                    : '现场生产环境、过程控制、产品检验及追溯体系运行良好，评定结果为：符合规范。'}
                </p>

                <div className="grid grid-cols-2 gap-4 pt-2 border-t border-slate-800 text-[11px]">
                  <div className="space-y-4">
                    <div>检查人员（签名）：<span className="font-serif italic text-white underline">{enterpriseInfo.inspectors}</span></div>
                    <div>日期：{enterpriseInfo.inspectDate}</div>
                  </div>
                  <div className="space-y-4">
                    <div>被检查单位负责人（签名）：<span className="font-serif italic text-white underline">王建华 (已签章)</span></div>
                    <div>日期：{enterpriseInfo.inspectDate}</div>
                  </div>
                </div>
              </div>
            </div>

            {/* 弹窗底部操作按钮 */}
            <div className="px-4 py-3 bg-slate-950 border-t border-slate-800 flex items-center justify-between gap-2 shrink-0">
              <button
                onClick={handleResetAll}
                className="px-3 py-2 rounded-lg bg-slate-800 hover:bg-red-950/70 text-slate-400 hover:text-red-300 text-xs font-medium flex items-center gap-1 transition"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>清空演示记录</span>
              </button>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => window.print()}
                  className="px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-white text-xs font-medium flex items-center gap-1.5 transition"
                >
                  <Printer className="w-3.5 h-3.5" />
                  <span>打印报告</span>
                </button>
                <button
                  onClick={() => setIsSummaryModalOpen(false)}
                  className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold transition shadow-md"
                >
                  确定关闭
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
