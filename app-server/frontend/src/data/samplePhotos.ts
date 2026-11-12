/**
 * 现场检查各要点预置演示照片生成器 (SVG Data URLs)
 * 供 Demo 演示时一键模拟手机端现场拍照拍摄到的取证照片
 */

function svgToDataUrl(svg: string): string {
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

export const SAMPLE_PHOTOS = {
  // 1. 资质许可证 (合规)
  license: svgToDataUrl(`
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 260" width="100%" height="100%">
      <rect width="400" height="260" fill="#fdfbf7" stroke="#b45309" stroke-width="6"/>
      <rect x="12" y="12" width="376" height="236" fill="none" stroke="#d97706" stroke-width="1.5" stroke-dasharray="4,2"/>
      <text x="200" y="45" font-family="sans-serif" font-size="18" font-weight="bold" fill="#78350f" text-anchor="middle">中华人民共和国食品生产许可证</text>
      <text x="200" y="70" font-family="sans-serif" font-size="11" fill="#92400e" text-anchor="middle">SC10653011100888</text>
      <line x1="30" y1="82" x2="370" y2="82" stroke="#d97706" stroke-width="1"/>
      <text x="40" y="110" font-family="sans-serif" font-size="12" fill="#1f2937">生产者名称：云南七彩高原绿色食品有限公司</text>
      <text x="40" y="135" font-family="sans-serif" font-size="12" fill="#1f2937">法定代表人：王建华</text>
      <text x="40" y="160" font-family="sans-serif" font-size="12" fill="#1f2937">生产地址：昆明市经开区经邮路18号生产基地</text>
      <text x="40" y="185" font-family="sans-serif" font-size="12" fill="#1f2937">食品类别：糕点、膨化食品、坚果制品</text>
      <text x="40" y="210" font-family="sans-serif" font-size="12" fill="#059669" font-weight="bold">有效期至：2028年09月15日 (有效状态)</text>
      <circle cx="330" cy="190" r="32" fill="none" stroke="#dc2626" stroke-width="3" stroke-dasharray="6,2"/>
      <text x="330" y="188" font-family="sans-serif" font-size="9" fill="#dc2626" text-anchor="middle" font-weight="bold">市场监督管理局</text>
      <text x="330" y="202" font-family="sans-serif" font-size="9" fill="#dc2626" text-anchor="middle">许可专用章</text>
    </svg>
  `),

  // 2. 车间生产环境 (合规)
  workshop: svgToDataUrl(`
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 260" width="100%" height="100%">
      <defs>
        <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#e0f2fe"/><stop offset="100%" stop-color="#bae6fd"/></linearGradient>
        <linearGradient id="floor" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#94a3b8"/><stop offset="100%" stop-color="#64748b"/></linearGradient>
      </defs>
      <rect width="400" height="150" fill="url(#sky)"/>
      <rect y="150" width="400" height="110" fill="url(#floor)"/>
      <line x1="0" y1="150" x2="400" y2="150" stroke="#334155" stroke-width="3"/>
      <!-- 排污槽与地漏 -->
      <rect x="30" y="220" width="340" height="18" rx="4" fill="#475569" stroke="#cbd5e1" stroke-width="1.5"/>
      <circle cx="60" cy="229" r="4" fill="#1e293b"/><circle cx="100" cy="229" r="4" fill="#1e293b"/><circle cx="140" cy="229" r="4" fill="#1e293b"/>
      <circle cx="180" cy="229" r="4" fill="#1e293b"/><circle cx="220" cy="229" r="4" fill="#1e293b"/><circle cx="260" cy="229" r="4" fill="#1e293b"/>
      <circle cx="300" cy="229" r="4" fill="#1e293b"/><circle cx="340" cy="229" r="4" fill="#1e293b"/>
      <!-- 设备与流水线 -->
      <rect x="50" y="80" width="120" height="90" rx="6" fill="#cbd5e1" stroke="#475569" stroke-width="2"/>
      <rect x="220" y="70" width="140" height="100" rx="6" fill="#cbd5e1" stroke="#475569" stroke-width="2"/>
      <line x1="170" y1="125" x2="220" y2="125" stroke="#3b82f6" stroke-width="4"/>
      <!-- 标识牌 -->
      <rect x="70" y="95" width="80" height="24" rx="3" fill="#22c55e"/>
      <text x="110" y="111" font-family="sans-serif" font-size="11" fill="#fff" text-anchor="middle" font-weight="bold">已清洁已点检</text>
      <!-- 现场说明文字水印 -->
      <rect x="10" y="10" width="190" height="26" rx="4" fill="rgba(15,23,42,0.7)"/>
      <text x="18" y="27" font-family="sans-serif" font-size="11" fill="#22c55e">✓ 车间地面无积水 · 设施整洁</text>
    </svg>
  `),

  // 3. 更衣洗手消毒区 (合规)
  hygiene: svgToDataUrl(`
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 260" width="100%" height="100%">
      <rect width="400" height="260" fill="#f8fafc"/>
      <!-- 瓷砖纹理 -->
      <line x1="0" y1="60" x2="400" y2="60" stroke="#e2e8f0" stroke-width="1"/>
      <line x1="0" y1="120" x2="400" y2="120" stroke="#e2e8f0" stroke-width="1"/>
      <line x1="0" y1="180" x2="400" y2="180" stroke="#e2e8f0" stroke-width="1"/>
      <!-- 洗手池 -->
      <rect x="40" y="140" width="150" height="70" rx="8" fill="#e0f2fe" stroke="#0284c7" stroke-width="2"/>
      <!-- 感应水龙头 -->
      <path d="M 115 140 L 115 105 Q 115 95 105 95 L 95 95" fill="none" stroke="#64748b" stroke-width="6" stroke-linecap="round"/>
      <circle cx="105" cy="115" r="3" fill="#0284c7"/>
      <!-- 消毒与洗手液瓶 -->
      <rect x="220" y="110" width="30" height="50" rx="4" fill="#10b981" stroke="#047857" stroke-width="1.5"/>
      <text x="235" y="138" font-family="sans-serif" font-size="8" fill="#fff" text-anchor="middle">洗手液</text>
      <!-- 酒精喷雾 -->
      <rect x="265" y="100" width="32" height="60" rx="4" fill="#3b82f6" stroke="#1d4ed8" stroke-width="1.5"/>
      <text x="281" y="132" font-family="sans-serif" font-size="8" fill="#fff" text-anchor="middle">75%酒精</text>
      <!-- 干手器 -->
      <rect x="320" y="80" width="55" height="70" rx="6" fill="#f1f5f9" stroke="#94a3b8" stroke-width="2"/>
      <rect x="335" y="130" width="25" height="8" rx="2" fill="#0284c7"/>
      <text x="347" y="110" font-family="sans-serif" font-size="9" fill="#334155" text-anchor="middle">干手器</text>
      <rect x="10" y="10" width="220" height="26" rx="4" fill="rgba(15,23,42,0.7)"/>
      <text x="18" y="27" font-family="sans-serif" font-size="11" fill="#22c55e">✓ 洗消设施完好 · 感应龙头+消毒液</text>
    </svg>
  `),

  // 4. 原辅料库与托盘堆放 (合规)
  storage: svgToDataUrl(`
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 260" width="100%" height="100%">
      <rect width="400" height="260" fill="#f1f5f9"/>
      <!-- 墙壁与地面标线 -->
      <rect x="0" y="0" width="60" height="260" fill="#e2e8f0"/>
      <line x1="60" y1="0" x2="60" y2="260" stroke="#cbd5e1" stroke-width="3"/>
      <!-- 离地离墙标识线 (黄黑相间) -->
      <line x1="90" y1="0" x2="90" y2="260" stroke="#eab308" stroke-width="4" stroke-dasharray="10,6"/>
      <!-- 托盘与原料码放 -->
      <rect x="110" y="190" width="120" height="20" rx="2" fill="#78350f"/>
      <rect x="115" y="130" width="110" height="60" rx="3" fill="#fed7aa" stroke="#f97316" stroke-width="1.5"/>
      <text x="170" y="165" font-family="sans-serif" font-size="11" fill="#9a3412" text-anchor="middle" font-weight="bold">特制小麦粉</text>
      <!-- 货位卡与温湿度计 -->
      <rect x="250" y="80" width="120" height="130" rx="6" fill="#fff" stroke="#94a3b8" stroke-width="2"/>
      <rect x="250" y="80" width="120" height="30" rx="6" fill="#3b82f6"/>
      <text x="310" y="100" font-family="sans-serif" font-size="11" fill="#fff" text-anchor="middle" font-weight="bold">原辅料货位卡</text>
      <text x="260" y="130" font-family="sans-serif" font-size="10" fill="#1e293b">品名：食用植物油</text>
      <text x="260" y="150" font-family="sans-serif" font-size="10" fill="#1e293b">批次：LOT20261108</text>
      <text x="260" y="170" font-family="sans-serif" font-size="10" fill="#1e293b">保质期：18个月</text>
      <text x="260" y="195" font-family="sans-serif" font-size="10" fill="#059669" font-weight="bold">温湿度：21℃ / 55%</text>
      <rect x="10" y="10" width="210" height="26" rx="4" fill="rgba(15,23,42,0.7)"/>
      <text x="18" y="27" font-family="sans-serif" font-size="11" fill="#22c55e">✓ 原料离地离墙≥10cm · 货位卡规范</text>
    </svg>
  `),

  // 5. 食品添加剂专柜五专管理 (合规)
  additive: svgToDataUrl(`
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 260" width="100%" height="100%">
      <rect width="400" height="260" fill="#f8fafc"/>
      <!-- 双门专柜 -->
      <rect x="60" y="40" width="280" height="190" rx="8" fill="#e2e8f0" stroke="#475569" stroke-width="3"/>
      <line x1="200" y1="40" x2="200" y2="230" stroke="#475569" stroke-width="2"/>
      <!-- 警示标识牌 -->
      <rect x="100" y="55" width="200" height="30" rx="4" fill="#dc2626"/>
      <text x="200" y="75" font-family="sans-serif" font-size="12" fill="#fff" text-anchor="middle" font-weight="bold">食品添加剂专用柜（五专管理）</text>
      <!-- 双锁具 -->
      <circle cx="185" cy="140" r="10" fill="#f59e0b" stroke="#78350f" stroke-width="2"/>
      <circle cx="215" cy="140" r="10" fill="#f59e0b" stroke="#78350f" stroke-width="2"/>
      <!-- 精密天平 -->
      <rect x="80" y="150" width="70" height="50" rx="4" fill="#fff" stroke="#94a3b8" stroke-width="1.5"/>
      <text x="115" y="180" font-family="sans-serif" font-size="9" fill="#0284c7" text-anchor="middle">电子天平 0.01g</text>
      <rect x="10" y="10" width="220" height="26" rx="4" fill="rgba(15,23,42,0.7)"/>
      <text x="18" y="27" font-family="sans-serif" font-size="11" fill="#22c55e">✓ 添加剂专柜双人双锁 · 台账与专秤相符</text>
    </svg>
  `),

  // 6. 隐患样本 1: 洗手池无水无纸 (违规)
  issue_sink: svgToDataUrl(`
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 260" width="100%" height="100%">
      <rect width="400" height="260" fill="#fef2f2"/>
      <rect x="40" y="130" width="150" height="70" rx="8" fill="#fee2e2" stroke="#ef4444" stroke-width="2.5"/>
      <path d="M 115 130 L 115 95 Q 115 85 105 85 L 95 85" fill="none" stroke="#ef4444" stroke-width="6" stroke-linecap="round"/>
      <rect x="220" y="110" width="30" height="50" rx="4" fill="#e2e8f0" stroke="#dc2626" stroke-width="2"/>
      <text x="235" y="140" font-family="sans-serif" font-size="16" fill="#dc2626" text-anchor="middle" font-weight="bold">空</text>
      <rect x="310" y="80" width="55" height="70" rx="6" fill="#f87171" stroke="#b91c1c" stroke-width="2"/>
      <text x="337" y="120" font-family="sans-serif" font-size="11" fill="#fff" text-anchor="middle" font-weight="bold">缺干手纸</text>
      <rect x="10" y="10" width="230" height="26" rx="4" fill="rgba(220,38,38,0.9)"/>
      <text x="18" y="27" font-family="sans-serif" font-size="11" fill="#fff" font-weight="bold">⚠ 现场隐患：龙头缺水 · 洗手耗材未配齐</text>
    </svg>
  `),

  // 7. 隐患样本 2: 挡鼠板破损 (违规)
  issue_pest: svgToDataUrl(`
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 260" width="100%" height="100%">
      <rect width="400" height="260" fill="#fffbeb"/>
      <!-- 门框 -->
      <rect x="60" y="30" width="280" height="200" fill="#f8fafc" stroke="#64748b" stroke-width="4"/>
      <!-- 挡鼠板 -->
      <rect x="60" y="170" width="280" height="60" fill="#cbd5e1" stroke="#b45309" stroke-width="2"/>
      <!-- 底部缝隙破损 -->
      <polygon points="170,230 190,210 215,230" fill="#ef4444"/>
      <circle cx="195" cy="220" r="14" fill="none" stroke="#dc2626" stroke-width="2" stroke-dasharray="3,2"/>
      <text x="195" y="200" font-family="sans-serif" font-size="10" fill="#dc2626" text-anchor="middle" font-weight="bold">缝隙过大 (>1.5cm)</text>
      <rect x="10" y="10" width="230" height="26" rx="4" fill="rgba(217,119,6,0.95)"/>
      <text x="18" y="27" font-family="sans-serif" font-size="11" fill="#fff" font-weight="bold">⚠ 现场隐患：挡鼠板密封破损 · 防虫不全</text>
    </svg>
  `)
};

export function getSamplePhotoForItem(catSeq: number, itemNo: string, isIssue: boolean = false): string {
  if (isIssue) {
    if (catSeq === 2 && (itemNo.includes('5') || itemNo.includes('4'))) return SAMPLE_PHOTOS.issue_sink;
    if (catSeq === 2 && itemNo.includes('10')) return SAMPLE_PHOTOS.issue_pest;
    return SAMPLE_PHOTOS.issue_sink;
  }
  if (catSeq === 1) return SAMPLE_PHOTOS.license;
  if (catSeq === 2 && (itemNo.includes('5') || itemNo.includes('4'))) return SAMPLE_PHOTOS.hygiene;
  if (catSeq === 2) return SAMPLE_PHOTOS.workshop;
  if (catSeq === 3 || catSeq === 7) return SAMPLE_PHOTOS.storage;
  if (catSeq === 4 && itemNo.includes('4')) return SAMPLE_PHOTOS.additive;
  return SAMPLE_PHOTOS.workshop;
}
