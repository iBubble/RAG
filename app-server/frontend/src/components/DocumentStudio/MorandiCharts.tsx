import React, { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, LabelList,
  PieChart, Pie, Cell, Legend,
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis
} from 'recharts';

export const MORANDI_COLORS = ["#7C9885", "#8B9DC3", "#B4A992", "#C4A484", "#C9A9A6", "#9CAF88"];

interface ChartProps {
  title: string;
  labels: string[];
  values?: number[];
  series?: Record<string, number[]>; // For multi-series radar
}

// 1. 莫兰迪柱状图
export const MorandiBarChart: React.FC<ChartProps> = ({ title, labels, values }) => {
  const data = useMemo(() => labels.map((label, i) => ({
    name: label,
    value: values?.[i] || 0
  })), [labels, values]);

  return (
    <div className="w-full bg-white rounded-xl shadow-sm border border-gray-100 p-6 my-4 font-sans max-w-3xl mx-auto transition-transform hover:shadow-md">
      <h4 className="text-center text-gray-800 font-bold mb-6 text-base tracking-wide">{title}</h4>
      <div className="h-[280px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
            <XAxis dataKey="name" tick={{ fill: '#6B7280', fontSize: 12 }} axisLine={{ stroke: '#D1D5DB' }} tickLine={false} />
            <YAxis tick={{ fill: '#6B7280', fontSize: 12 }} axisLine={false} tickLine={false} />
            <RechartsTooltip cursor={{ fill: '#F3F4F6' }} contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} />
            <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={60}>
              {data.map((_, index) => (
                <Cell key={`cell-${index}`} fill={MORANDI_COLORS[index % MORANDI_COLORS.length]} />
              ))}
              <LabelList dataKey="value" position="top" fill="#6B7280" fontSize={11} fontWeight={500} formatter={(v: any) => Number.isInteger(Number(v)) ? Number(v) : Number(v).toFixed(1)} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

// 2. 莫兰迪饼图
export const MorandiPieChart: React.FC<ChartProps> = ({ title, labels, values }) => {
  const data = useMemo(() => labels.map((label, i) => ({
    name: label,
    value: values?.[i] || 0
  })), [labels, values]);

  return (
    <div className="w-full bg-white rounded-xl shadow-sm border border-gray-100 p-6 my-4 font-sans max-w-2xl mx-auto transition-transform hover:shadow-md">
      <h4 className="text-center text-gray-800 font-bold mb-2 text-base tracking-wide">{title}</h4>
      <div className="h-[300px] w-full pt-4">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="48%"
              innerRadius={0}
              outerRadius={100}
              paddingAngle={2}
              dataKey="value"
              label={({ name, percent }) => `${name} ${((percent || 0) * 100).toFixed(1)}%`}
              labelLine={{ stroke: '#9CA3AF', strokeWidth: 1 }}
            >
              {data.map((_, index) => (
                <Cell key={`cell-${index}`} fill={MORANDI_COLORS[index % MORANDI_COLORS.length]} />
              ))}
            </Pie>
            <RechartsTooltip contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

// 3. 莫兰迪雷达图 (多维对比)
export const MorandiRadarChart: React.FC<ChartProps> = ({ title, labels, series }) => {
  const data = useMemo(() => {
    return labels.map((label, i) => {
      const row: any = { subject: label };
      if (series) {
        Object.keys(series).forEach(serieName => {
          row[serieName] = series[serieName][i] || 0;
        });
      }
      return row;
    });
  }, [labels, series]);

  const seriesNames = series ? Object.keys(series) : [];

  return (
    <div className="w-full bg-white rounded-xl shadow-sm border border-gray-100 p-6 my-4 font-sans max-w-2xl mx-auto transition-transform hover:shadow-md">
      <h4 className="text-center text-gray-800 font-bold mb-4 text-base tracking-wide">{title}</h4>
      <div className="h-[320px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart cx="50%" cy="50%" outerRadius="75%" data={data}>
            <PolarGrid stroke="#E5E7EB" />
            <PolarAngleAxis dataKey="subject" tick={{ fill: '#4B5563', fontSize: 12, fontWeight: 500 }} />
            <PolarRadiusAxis angle={30} domain={[0, 'auto']} tick={{ fill: '#9CA3AF', fontSize: 10 }} />
            <RechartsTooltip contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} />
            <Legend wrapperStyle={{ fontSize: 12, paddingTop: '10px' }} />
            {seriesNames.map((name, idx) => (
              <Radar key={name} name={name} dataKey={name} stroke={MORANDI_COLORS[idx % MORANDI_COLORS.length]} fill={MORANDI_COLORS[idx % MORANDI_COLORS.length]} fillOpacity={0.4} />
            ))}
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

// 智能探测工厂组件：提取富文本中的可视化标记并挂载真实前端组件
export const SmartChartRenderer: React.FC<{ htmlContent: string }> = ({ htmlContent }) => {
  const charts = useMemo(() => {
    // 剥离出所有的纯文本，忽略标签，抗击 TipTap 包裹
    const plainText = htmlContent.replace(/<[^>]*>?/gm, ' ');
    const chartRegex = /\[可视化[：:]\s*(柱状图|饼图|雷达图)\s*[，,]\s*标题[：:]\s*(.+?)\s*\]/g;
    
    const parsedCharts: any[] = [];
    
    let m;
    while ((m = chartRegex.exec(plainText)) !== null) {
        const typeStr = m[1];
        const title = m[2];
        const type = typeStr === "柱状图" ? "bar" : typeStr === "饼图" ? "pie" : "radar";
        parsedCharts.push({ type, title });
    }
    
    if (parsedCharts.length === 0) return [];

    // 获取与之并行的富文本内的 Table 并提取数据
    if (typeof document !== 'undefined') {
        const parser = new DOMParser();
        const doc = parser.parseFromString(htmlContent, 'text/html');
        const tables = Array.from(doc.querySelectorAll('table'));
        
        return parsedCharts.map((chart, i) => {
            const table = tables[i];
            if (!table) return null;
            
            const rows = Array.from(table.querySelectorAll('tr'));
            if (rows.length < 2) return null;

            const headerCells = Array.from(rows[0].querySelectorAll('th, td')).map(th => th.textContent?.trim() || '');
            
            // 双列 (Bar, Pie)
            if (chart.type === 'bar' || chart.type === 'pie') {
                const labels: string[] = [];
                const values: number[] = [];
                for (let r = 1; r < rows.length; r++) {
                    const cells = Array.from(rows[r].querySelectorAll('td')).map(tc => tc.textContent?.trim() || '');
                    if (cells.length >= 2) {
                        labels.push(cells[0] || '未知');
                        // 去除一切非数字相关的字符进行转换
                        const num = parseFloat(cells[1].replace(/[^\d.-]/g, ''));
                        values.push(isNaN(num) ? 0 : num);
                    }
                }
                return { ...chart, labels, values };
            } 
            
            // 多列 (Radar)
            if (chart.type === 'radar' && headerCells.length >= 2) {
                const seriesNames = headerCells.slice(1);
                const labels: string[] = [];
                const series: Record<string, number[]> = {};
                seriesNames.forEach(name => { series[name] = []; });
                
                for (let r = 1; r < rows.length; r++) {
                    const cells = Array.from(rows[r].querySelectorAll('td')).map(tc => tc.textContent?.trim() || '');
                    if (cells.length >= 2) {
                        labels.push(cells[0] || '未知');
                        seriesNames.forEach((name, j) => {
                            const rawStr = cells[j + 1] || '0';
                            const num = parseFloat(rawStr.replace(/[^\d.-]/g, ''));
                            series[name].push(isNaN(num) ? 0 : num);
                        });
                    }
                }
                return { ...chart, labels, series };
            }
            return null;
        }).filter(Boolean);
    }
    
    return [];
  }, [htmlContent]);

  if (charts.length === 0) return null;

  return (
    <div className="mt-4 pt-4 border-t border-dashed border-gray-200">
      <div className="flex items-center gap-2 mb-4 px-2">
        <span className="w-1.5 h-4 bg-indigo-400 rounded-full"></span>
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-widest">智能图表自动渲染 </span>
      </div>
      <div className="space-y-6">
        {charts.map((chart, idx) => {
          if (!chart) return null;
          if (chart.type === 'bar') {
              return <MorandiBarChart key={idx} title={chart.title} labels={chart.labels} values={chart.values} />;
          } else if (chart.type === 'pie') {
              return <MorandiPieChart key={idx} title={chart.title} labels={chart.labels} values={chart.values} />;
          } else if (chart.type === 'radar') {
              return <MorandiRadarChart key={idx} title={chart.title} labels={chart.labels} series={chart.series} />;
          }
          return null;
        })}
      </div>
    </div>
  );
};
