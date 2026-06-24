interface AgentInfo {
  status: 'working' | 'sleeping' | 'funny' | 'idle';
  funny_event: string | null;
  current_project: string | null;
  current_task: string | null;
}

interface DeskProps {
  agentKey: 'vectorizer' | 'graph' | 'summary' | 'precompute' | 'chat' | 'legal' | 'service' | 'contrarian' | 'arbiter';
  name: string;
  gender?: 'male' | 'female';
  avatar?: 'ox' | 'horse' | 'human' | 'robot';
  roleTitle: string;
  info: AgentInfo;
}

export default function LinvisDesk({ agentKey, name, gender = 'male', avatar = 'horse', roleTitle, info }: DeskProps) {
  // 定义每个 Agent 的主题色和特色装饰
  const themeMap = {
    vectorizer: { primary: '#3b82f6', secondary: '#93c5fd', avatarBg: '#ebf8ff', accent: '👓' },
    graph: { primary: '#10b981', secondary: '#6ee7b7', avatarBg: '#ecfdf5', accent: '🕸️' },
    summary: { primary: '#8b5cf6', secondary: '#c4b5fd', avatarBg: '#f5f3ff', accent: '🦉' },
    precompute: { primary: '#f59e0b', secondary: '#fcd34d', avatarBg: '#fffbeb', accent: '🧮' },
    chat: { primary: '#ec4899', secondary: '#fbcfe8', avatarBg: '#fdf2f8', accent: '🐲' },
    legal: { primary: '#ef4444', secondary: '#fca5a5', avatarBg: '#fef2f2', accent: '⚖️' },
    service: { primary: '#6366f1', secondary: '#a5b4fc', avatarBg: '#e0e7ff', accent: '💼' },
    contrarian: { primary: '#ea580c', secondary: '#fdba74', avatarBg: '#fff7ed', accent: '🤨' },
    arbiter: { primary: '#b45309', secondary: '#fcd34d', avatarBg: '#fefce8', accent: '👑' }
  };

  const theme = themeMap[agentKey];
  const isWorking = info.status === 'working';
  const isSleeping = info.status === 'sleeping';
  const isFunny = info.status === 'funny';

  // 待处理任务数模拟，基于状态和搞笑内容
  const docPileHeight = isWorking ? 6 : (isFunny ? 3 : 1);

  return (
    <div className="flex flex-col items-center p-3 relative group w-52 bg-white/40 backdrop-blur-sm rounded-xl border border-[#e0dcd5] shadow-sm transition-all duration-300 hover:scale-[1.03] hover:shadow-md">
      
      {/* 状态泡泡 (搞笑事件对话框) */}
      {isFunny && info.funny_event && (
        <div className="absolute -top-12 left-1/2 -translate-x-1/2 w-48 bg-[#fffbeb] border border-amber-200 text-amber-900 text-xs px-3 py-1.5 rounded-xl shadow-md z-10 animate-bounce text-center">
          <div className="font-semibold text-[10px] text-amber-600 mb-0.5">💭 {name} 正在...</div>
          {info.funny_event}
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-8 border-transparent border-top-amber-200 border-t-[#fffbeb]"></div>
        </div>
      )}

      {/* 工作状态提示 */}
      {isWorking && info.current_task && (
        <div className="absolute -top-12 left-1/2 -translate-x-1/2 w-48 bg-[#ecfdf5] border border-emerald-200 text-emerald-900 text-xs px-3 py-1.5 rounded-xl shadow-md z-10 text-center">
          <div className="font-semibold text-[10px] text-emerald-600 mb-0.5">⚡ 正在处理</div>
          <p className="truncate font-bold">{info.current_task}</p>
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-8 border-transparent border-t-[#ecfdf5]"></div>
        </div>
      )}

      {/* Zzz 气泡 */}
      {isSleeping && (
        <div className="absolute top-4 right-10 text-lg font-bold text-indigo-400 select-none animate-[pulse_1.5s_ease-in-out_infinite]">
          💤 zZ
        </div>
      )}

      <div className={`w-24 h-24 flex items-center justify-center relative transition-all duration-500 ${
        isWorking ? 'animate-typing-shake' : (isSleeping ? 'opacity-85 scale-95' : 'animate-breath')
      }`}>
        <svg viewBox="0 0 100 100" className="w-22 h-22 filter drop-shadow-[0_4px_8px_rgba(0,0,0,0.15)]">
          <defs>
            {/* 3D 粘土皮肤渐变 */}
            <radialGradient id={`claySkin-${agentKey}`} cx="35%" cy="30%" r="70%">
              <stop offset="0%" stopColor="#ffffff" />
              <stop offset="25%" stopColor={theme.avatarBg} />
              <stop offset="85%" stopColor={theme.secondary} />
              <stop offset="100%" stopColor={theme.primary} />
            </radialGradient>
            
            {/* 3D 粘土后脑勺/阴影面渐变 */}
            <radialGradient id={`clayBack-${agentKey}`} cx="35%" cy="30%" r="70%">
              <stop offset="0%" stopColor={theme.secondary} />
              <stop offset="70%" stopColor={theme.primary} />
              <stop offset="100%" stopColor="#1e293b" />
            </radialGradient>

            {/* 椅子靠背 3D 渐变 */}
            <radialGradient id="chairBackGrad-new" cx="50%" cy="30%" r="75%">
              <stop offset="0%" stopColor="#ffffff" />
              <stop offset="80%" stopColor="#e2e8f0" />
              <stop offset="100%" stopColor="#cbd5e1" />
            </radialGradient>

            {/* 衣领立体渐变 */}
            <linearGradient id={`collarGrad-${agentKey}`} x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor={theme.secondary} />
              <stop offset="50%" stopColor="#ffffff" />
              <stop offset="100%" stopColor={theme.primary} />
            </linearGradient>

            {/* 3D 咖啡杯渐变 */}
            <linearGradient id="coffeeCupGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#f8fafc" />
              <stop offset="80%" stopColor="#e2e8f0" />
              <stop offset="100%" stopColor="#94a3b8" />
            </linearGradient>
          </defs>

          {/* 3D 办公椅靠背 */}
          <path d="M22,88 C22,48 78,48 78,88 Z" fill="url(#chairBackGrad-new)" stroke="#94a3b8" strokeWidth="1" />
          <line x1="50" y1="84" x2="50" y2="98" stroke="#64748b" strokeWidth="5" />

          {/* 3D 粘土小马身体 */}
          <path d="M30,86 Q50,56 70,86 Z" fill={`url(#clayBack-${agentKey})`} />

          {/* 3D 衣领 */}
          <rect x="34" y="68" width="32" height="10" rx="5" fill={`url(#collarGrad-${agentKey})`} filter="drop-shadow(0 2px 4px rgba(0,0,0,0.15))" />

          {/* 头部 (歪头与转头过渡) */}
          <g style={{
            transformOrigin: '50px 45px',
            transform: isSleeping ? 'rotate(-10deg) translateY(2px)' : 'none',
            transition: 'transform 0.4s ease-in-out'
          }}>
            {/* 特色耳朵/角/天线装饰物 */}
            {avatar === 'horse' && (
              <>
                {/* 3D 马耳 */}
                <path d="M33,24 Q41,5 45,22 Z" fill={`url(#clayBack-${agentKey})`} />
                <path d="M67,24 Q59,5 55,22 Z" fill={`url(#clayBack-${agentKey})`} />
                <path d="M36,22 Q40,10 42,20 Z" fill={theme.avatarBg} opacity="0.6" />
                <path d="M64,22 Q60,10 58,20 Z" fill={theme.avatarBg} opacity="0.6" />
                {/* 额前可爱马鬃毛 */}
                {!isWorking && (
                  <path d="M43,23 Q50,14 57,23 Q50,18 43,23 Z" fill="#334155" />
                )}
              </>
            )}

            {avatar === 'ox' && (
              <>
                {/* 3D 渐变金色牛角 */}
                <path d="M31,24 C24,13 18,15 16,20 C16,22 22,20 27,26 Z" fill="#fde047" stroke="#ca8a04" strokeWidth="0.5" />
                <path d="M69,24 C76,13 82,15 84,20 C84,22 78,20 73,26 Z" fill="#fde047" stroke="#ca8a04" strokeWidth="0.5" />
                {/* 耷拉的萌系大牛耳 */}
                <path d="M25,32 C15,34 16,42 23,38 Z" fill={`url(#clayBack-${agentKey})`} />
                <path d="M75,32 C85,34 84,42 77,38 Z" fill={`url(#clayBack-${agentKey})`} />
              </>
            )}

            {avatar === 'human' && !isWorking && (
              <>
                {gender === 'female' ? (
                  <>
                    {/* 女生蓬松双辫 */}
                    <circle cx="26" cy="42" r="5.5" fill="#334155" />
                    <circle cx="74" cy="42" r="5.5" fill="#334155" />
                    <circle cx="23" cy="46" r="4" fill="#334155" />
                    <circle cx="77" cy="46" r="4" fill="#334155" />
                  </>
                ) : (
                  <>
                    {/* 男生时尚粘土棒球帽 */}
                    <path d="M34,25 C34,13 66,13 66,25 Z" fill="#ef4444" filter="drop-shadow(0 2px 2px rgba(0,0,0,0.15))" />
                    <path d="M30,25 C40,22 60,22 70,25 C74,26 67,30 50,29 C33,30 26,26 30,25 Z" fill="#b91c1c" />
                  </>
                )}
              </>
            )}

            {avatar === 'robot' && (
              <>
                {/* 3D 侧边金属螺栓耳 */}
                <rect x="26" y="34" width="5" height="13" rx="2" fill="#94a3b8" stroke="#64748b" strokeWidth="0.5" />
                <rect x="69" y="34" width="5" height="13" rx="2" fill="#94a3b8" stroke="#64748b" strokeWidth="0.5" />
                {/* 科技感发光 3D 天线 */}
                <line x1="50" y1="22" x2="50" y2="10" stroke="#64748b" strokeWidth="2.5" />
                <circle cx="50" cy="9" r="3.5" fill="#f43f5e" className="animate-pulse" filter="drop-shadow(0 0 3px #f43f5e)" />
              </>
            )}

            {/* 2. 主头部外形渲染 */}
            {isWorking ? (
              // 工作状态：背影后脑勺
              <>
                {avatar === 'robot' ? (
                  <rect x="30" y="21" width="40" height="37" rx="8" fill={`url(#clayBack-${agentKey})`} />
                ) : (
                  <circle cx="50" cy="42" r="20" fill={`url(#clayBack-${agentKey})`} />
                )}
                {/* 后脑头饰/马鬃毛/人类头发 */}
                {avatar === 'horse' && (
                  <>
                    <path d="M46,18 Q50,8 54,18 Z" fill="#334155" />
                    <path d="M43,24 Q50,14 57,24 Z" fill="#334155" />
                  </>
                )}
                {avatar === 'human' && (
                  <path d="M30,30 Q50,13 70,30 C70,19 60,17 50,17 C40,17 30,19 30,30 Z" fill="#334155" />
                )}
              </>
            ) : (
              // 空闲/睡觉/搞怪：转过来正面
              <>
                {avatar === 'robot' ? (
                  <>
                    {/* 机器人头部外壳 */}
                    <rect x="29" y="21" width="42" height="37" rx="9" fill={`url(#claySkin-${agentKey})`} stroke={theme.primary} strokeWidth="1" />
                    {/* 深灰色 LED 屏幕区 */}
                    <rect x="33" y="25" width="34" height="22" rx="4" fill="#1e293b" />
                  </>
                ) : (
                  <circle cx="50" cy="42" r="20" fill={`url(#claySkin-${agentKey})`} stroke={theme.primary} strokeWidth="0.5" />
                )}

                {/* 人类发型 */}
                {avatar === 'human' && (
                  <>
                    {gender === 'female' ? (
                      <path d="M30,30 Q50,15 70,30 C66,22 58,22 50,23 C42,22 34,22 30,30 Z" fill="#334155" />
                    ) : (
                      <path d="M30,30 Q50,12 70,25 C64,20 54,20 50,22 C46,20 36,22 30,30 Z" fill="#334155" />
                    )}
                  </>
                )}

                {/* 3D 粘土腮红 (机器人不需要) */}
                {avatar !== 'robot' && (
                  <>
                    <circle cx="35" cy="46" r="3" fill="#fda4af" opacity="0.85" />
                    <circle cx="65" cy="46" r="3" fill="#fda4af" opacity="0.85" />
                  </>
                )}

                {/* 马嘴巴/马面突出吻部 */}
                {avatar === 'horse' && (
                  <>
                    <ellipse cx="50" cy="49" rx="8.5" ry="4.5" fill="#f8fafc" stroke={theme.secondary} strokeWidth="0.5" />
                    <circle cx="47" cy="49" r="0.8" fill="#64748b" />
                    <circle cx="53" cy="49" r="0.8" fill="#64748b" />
                  </>
                )}

                {/* 牛鼻子特质与 3D 黄金鼻环 */}
                {avatar === 'ox' && (
                  <>
                    <ellipse cx="50" cy="48" rx="6.5" ry="3.2" fill="#fecdd3" stroke="#f43f5e" strokeWidth="0.5" />
                    {/* 卡通金鼻环 */}
                    <circle cx="50" cy="51.5" r="2.8" fill="none" stroke="#fbbf24" strokeWidth="1.2" filter="drop-shadow(0 1px 1px rgba(0,0,0,0.15))" />
                  </>
                )}

                {/* 眼睛与表情 */}
                {isSleeping ? (
                  <>
                    {avatar === 'robot' ? (
                      <line x1="38" y1="36" x2="62" y2="36" stroke="#475569" strokeWidth="2.5" />
                    ) : (
                      <>
                        <path d="M38 42 Q42 46 45 42" fill="none" stroke="#475569" strokeWidth="2.5" strokeLinecap="round" />
                        <path d="M55 42 Q58 46 62 42" fill="none" stroke="#475569" strokeWidth="2.5" strokeLinecap="round" />
                      </>
                    )}
                    <path d="M48 50 Q50 52 52 50" fill="none" stroke="#475569" strokeWidth="2" strokeLinecap="round" />
                  </>
                ) : (
                  <>
                    {/* 眨眼眼球 */}
                    <g className="animate-blink">
                      {avatar === 'robot' ? (
                        <>
                          <rect x="37" y="32" width="7" height="4" rx="1" fill="#38bdf8" filter="drop-shadow(0 0 2px #38bdf8)" />
                          <rect x="56" y="32" width="7" height="4" rx="1" fill="#38bdf8" filter="drop-shadow(0 0 2px #38bdf8)" />
                        </>
                      ) : (
                        <>
                          <circle cx="41" cy="42" r="4.5" fill="white" />
                          <circle cx="41" cy="42" r="2.5" fill="#0f172a" />
                          <circle cx="42.5" cy="40.5" r="1" fill="white" />
                          
                          <circle cx="59" cy="42" r="4.5" fill="white" />
                          <circle cx="59" cy="42" r="2.5" fill="#0f172a" />
                          <circle cx="60.5" cy="40.5" r="1" fill="white" />
                        </>
                      )}
                    </g>
                    {/* 嘴巴 */}
                    {avatar === 'robot' ? (
                      // 机器人的 LED 声波示波线嘴巴
                      <path d="M44 41 Q47 43 50 41 Q53 39 56 41" fill="none" stroke="#38bdf8" strokeWidth="1.5" strokeLinecap="round" filter="drop-shadow(0 0 1.5px #38bdf8)" />
                    ) : (
                      <path d="M47 49 Q50 53 53 49" fill="none" stroke="#334155" strokeWidth="2" strokeLinecap="round" />
                    )}
                  </>
                )}
              </>
            )}
          </g>

          {/* 前景动作层：手部与道具 */}
          {isWorking && (
            // 工作打字：双手和键盘
            <>
              {/* 3D 键盘 */}
              <rect x="30" y="78" width="40" height="6" rx="2" fill="#475569" filter="drop-shadow(0 2px 2px rgba(0,0,0,0.2))" />
              {/* 左右小手跳动敲键盘 */}
              <circle cx="37" cy="78" r="4" fill={`url(#claySkin-${agentKey})`} className="animate-hand-l" />
              <circle cx="63" cy="78" r="4" fill={`url(#claySkin-${agentKey})`} className="animate-hand-r" />
            </>
          )}

          {isFunny && (
            // 搞怪：搓掌机
            <>
              <g className="animate-play" style={{ transformOrigin: '50px 80px' }}>
                <rect x="36" y="74" width="28" height="12" rx="2.5" fill="#ef4444" stroke="#b91c1c" strokeWidth="1" filter="drop-shadow(0 3px 4px rgba(0,0,0,0.2))" />
                <rect x="42" y="76" width="16" height="8" fill="#1e293b" />
                <circle cx="39" cy="80" r="2" fill="#fbbf24" />
                <circle cx="61" cy="80" r="1.5" fill="#3b82f6" />
                <circle cx="61" cy="82" r="1.5" fill="#10b981" />
                {/* 搓机小手 */}
                <circle cx="38" cy="81" r="3.5" fill={`url(#claySkin-${agentKey})`} />
                <circle cx="62" cy="81" r="3.5" fill={`url(#claySkin-${agentKey})`} />
              </g>
            </>
          )}

          {info.status === 'idle' && (
            // 空闲：端咖啡杯与上升热气
            <g transform="translate(68, 62)" filter="drop-shadow(0 2px 3px rgba(0,0,0,0.15))">
              <path d="M2,2 Q0,-4 -3,-2 Q-4,0 -2,4 Q1,8 6,8 Q12,8 14,4 L14,12 A4,4 0 0,1 10,16 L4,16 A4,4 0 0,1 0,12 Z" fill="none" />
              {/* 咖啡杯身 */}
              <path d="M2 5 L12 5 L10 14 L4 14 Z" fill="url(#coffeeCupGrad)" stroke="#cbd5e1" strokeWidth="0.5" />
              {/* 杯把手 */}
              <path d="M12 7 Q15 7 15 9.5 Q15 12 12 12" fill="none" stroke="#94a3b8" strokeWidth="1.5" />
              {/* 升腾热气线 */}
              <path d="M5 -1 Q7 -4 5 -7 Q3 -10 5 -13" fill="none" stroke="#94a3b8" strokeWidth="1" strokeLinecap="round" className="animate-steam" />
              <path d="M9 -2 Q11 -5 9 -8 Q7 -11 9 -14" fill="none" stroke="#94a3b8" strokeWidth="1" strokeLinecap="round" className="animate-steam" style={{ animationDelay: '0.7s' }} />
              {/* 端杯子小手 */}
              <circle cx="3" cy="11" r="3.5" fill={`url(#claySkin-${agentKey})`} />
            </g>
          )}

          {isSleeping && (
            // 睡觉：冒泡 Zzz
            <g transform="translate(64, 15)" fill="#6366f1" className="font-bold select-none text-[8px] opacity-75">
              <text x="0" y="0" className="animate-zzz-1">Z</text>
              <text x="5" y="-6" className="animate-zzz-2" style={{ fontSize: '10px' }}>Z</text>
            </g>
          )}
        </svg>

        {/* 右下角小胸针/标签 (表示 Agent 职能属性) */}
        <div className="absolute bottom-1 right-2 text-xl filter drop-shadow-md select-none">
          {theme.accent}
        </div>
      </div>

      {/* 办公桌与电脑 */}
      <div className="w-full flex flex-col items-center relative z-10 mt-[-8px]">
        {/* 3D 桌面上叠放的文件堆 */}
        <div className="absolute left-6 bottom-[36px] flex flex-col-reverse items-center z-20">
          {Array.from({ length: docPileHeight }).map((_, i) => (
            <div
              key={i}
              className="w-6 h-1 rounded-sm shadow-[1px_2px_3px_rgba(0,0,0,0.15)] border-b border-r border-[#c4b5a0] transition-all"
              style={{
                backgroundColor: i % 3 === 0 ? '#fbcfe8' : (i % 3 === 1 ? '#bfdbfe' : '#fef08a'),
                transform: `translateY(${i * 0.9}px) rotate(${i * 3 - 5}deg)`,
                opacity: 0.95
              }}
            ></div>
          ))}
        </div>

        {/* 3D 粘土电脑：带有 3D 厚度和屏显动态效果 */}
        <div className="absolute right-6 bottom-[35px] flex flex-col items-center z-20 filter drop-shadow-[0_3px_4px_rgba(0,0,0,0.12)]">
          {/* 3D 显示器外壳 */}
          <div className={`w-10 h-7 rounded-md border-2 p-0.5 flex flex-col items-center justify-between transition-all overflow-hidden ${
            isWorking 
              ? 'bg-[#064e3b] border-[#10b981]' 
              : (isSleeping ? 'bg-slate-950 border-slate-700' : 'bg-slate-900 border-[#6366f1]')
          }`}
          style={{
            boxShadow: 'inset 0 1px 2px rgba(255,255,255,0.2), 2px 2px 0px rgba(0,0,0,0.15)'
          }}>
            {/* 屏幕内容区 */}
            <div className="w-full h-full rounded relative overflow-hidden flex flex-col justify-center items-center">
              {isWorking && (
                // 滚动代码流
                <div className="w-full h-full flex flex-col gap-[2px] p-1 scale-90 origin-top animate-code-scroll">
                  <div className="w-[85%] h-[2px] bg-emerald-400/90 rounded-full"></div>
                  <div className="w-[60%] h-[2px] bg-emerald-400/80 rounded-full"></div>
                  <div className="w-[90%] h-[2px] bg-sky-400/90 rounded-full"></div>
                  <div className="w-[40%] h-[2px] bg-emerald-400/80 rounded-full"></div>
                  <div className="w-[70%] h-[2px] bg-yellow-400/80 rounded-full"></div>
                  <div className="w-[50%] h-[2px] bg-sky-400/90 rounded-full"></div>
                  {/* 重复循环内容 */}
                  <div className="w-[80%] h-[2px] bg-emerald-400/90 rounded-full mt-2"></div>
                  <div className="w-[60%] h-[2px] bg-sky-400/80 rounded-full"></div>
                </div>
              )}
              {isSleeping && (
                <div className="text-[4px] text-slate-600 font-bold select-none tracking-widest scale-75">OFF</div>
              )}
              {info.status === 'funny' && (
                // 摸鱼笑脸
                <div className="text-[7px] text-[#fcd34d] font-bold select-none animate-[bounce_1.5s_ease-in-out_infinite]">
                  🎮
                </div>
              )}
              {info.status === 'idle' && (
                // 屏保微笑
                <div className="text-[6px] text-[#818cf8] font-bold select-none animate-[pulse_2s_ease-in-out_infinite] scale-90">
                  ( ˘ ³˘)
                </div>
              )}
            </div>
          </div>
          {/* 3D 支架 */}
          <div className="w-2 h-1 bg-gradient-to-r from-gray-400 to-gray-500 shadow-inner"></div>
          {/* 3D 底座 */}
          <div className="w-7 h-1 bg-gradient-to-r from-gray-500 to-gray-600 rounded-full" style={{ boxShadow: '0 1px 2px rgba(0,0,0,0.2)' }}></div>
        </div>

        {/* 3D 木质桌面 */}
        <div className="w-full h-3.5 bg-gradient-to-b from-[#a16226] to-[#783b0b] rounded-t-xl shadow-[0_4px_8px_rgba(0,0,0,0.12)] border-b-[3px] border-[#502404] relative">
          {/* 桌边高光亮线 */}
          <div className="absolute top-0 left-0 w-full h-[1px] bg-white/20 rounded-t-xl"></div>
        </div>
        
        {/* 3D 桌腿 */}
        <div className="flex justify-between w-[88%] px-2">
          <div className="w-2 h-6 bg-gradient-to-r from-gray-300 via-gray-100 to-gray-400 border-r border-gray-400/50 shadow-inner rounded-b-sm"></div>
          <div className="w-2 h-6 bg-gradient-to-r from-gray-300 via-gray-100 to-gray-400 border-r border-gray-400/50 shadow-inner rounded-b-sm"></div>
        </div>
      </div>

      {/* 角色底座文字 */}
      <div className="text-center mt-1">
        <h4 className="font-bold text-gray-900 text-xs">{name}</h4>
        <p className="text-[9px] text-gray-400 font-medium tracking-wider">{roleTitle}</p>
      </div>

      {/* Hover 提示框（卡片指向时显示具体详情） */}
      <div className="absolute inset-0 bg-[#1e293b]/95 rounded-2xl p-4 text-white opacity-0 group-hover:opacity-100 transition-opacity duration-300 z-30 flex flex-col justify-between">
        <div>
          <div className="flex justify-between items-center border-b border-slate-700 pb-1.5 mb-2">
            <span className="font-bold text-sm text-[#fde047]">{name}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-bold">
              {info.status === 'working' ? '⚡ 繁忙' : (info.status === 'funny' ? '🤪 摸鱼' : (info.status === 'sleeping' ? '💤 睡觉' : '🟢 空闲'))}
            </span>
          </div>

          <p className="text-[11px] text-slate-400 leading-tight mb-2">{roleTitle}</p>

          <div className="space-y-1 text-[11px]">
            {info.current_project && (
              <div>
                <span className="text-slate-400">相关项目:</span>{' '}
                <span className="text-slate-200 font-medium block truncate" title={info.current_project}>
                  {info.current_project}
                </span>
              </div>
            )}
            {info.status === 'funny' && info.funny_event && (
              <div>
                <span className="text-slate-400">当前事件:</span>{' '}
                <span className="text-amber-300 block leading-tight font-medium">
                  {info.funny_event}
                </span>
              </div>
            )}
            {!info.current_project && info.status !== 'funny' && (
              <div className="text-slate-500 italic">暂无处理项目</div>
            )}
          </div>
        </div>

        <div className="border-t border-slate-700/60 pt-2 text-[10px] text-slate-400 flex justify-between">
          <span>堆积文档: {docPileHeight} 张</span>
          <span>状态: {info.status.toUpperCase()}</span>
        </div>
      </div>

    </div>
  );
}
