import { useState, useEffect } from 'react';
import { useAuthStore } from '../../store/authStore';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { Loader2, ShieldAlert, Calendar, BarChart2 } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || '';

interface RagasReportItem {
  report_date: string;
  faithfulness: number;
  context_relevance: number;
  answer_relevance: number;
  total_evaluated: number;
}

export default function RagasEvaluation() {
  const { getAuthHeaders } = useAuthStore();
  const [reports, setReports] = useState<RagasReportItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [alertThreshold, setAlertThreshold] = useState(0.85);

  useEffect(() => {
    const loadData = async () => {
      try {
        const sRes = await fetch(`${API_BASE}/api/admin/settings`, { headers: getAuthHeaders() });
        if (sRes.ok) {
          const sData = await sRes.json();
          if (sData.ragas_alert_threshold) {
            setAlertThreshold(parseFloat(sData.ragas_alert_threshold));
          }
        }
        const res = await fetch(`${API_BASE}/api/admin/ragas-reports`, { headers: getAuthHeaders() });
        if (res.ok) {
          setReports(await res.json());
        }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-gray-500">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500 mb-2" />
        <span className="text-sm">载入质量评测指标中...</span>
      </div>
    );
  }

  const latestReport = reports[reports.length - 1];
  const hasAlert = latestReport && (
    latestReport.faithfulness < alertThreshold ||
    latestReport.context_relevance < alertThreshold ||
    latestReport.answer_relevance < alertThreshold
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-xl font-bold text-gray-800">RAG质量监控看板</h2>
          <p className="text-xs text-gray-500 mt-1">基于 Ragas 凌晨定时跑批评测 (RAG Triad 三元组模型裁判打分)</p>
        </div>
        <div className="flex items-center gap-2 px-3.5 py-1.5 bg-indigo-50 rounded-xl text-xs text-indigo-700 font-semibold border border-indigo-100">
          <span>⚠️ 报警红线阈值：</span>
          <span className="font-bold text-sm bg-white px-1.5 py-0.5 rounded-md border border-indigo-200">{alertThreshold.toFixed(2)}</span>
        </div>
      </div>

      {latestReport ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-white p-5 rounded-2xl border border-gray-100 shadow-sm flex flex-col justify-between">
            <span className="text-xs text-gray-400 font-bold uppercase tracking-wider">最近一次评估日期</span>
            <div className="flex items-center gap-2 mt-2">
              <Calendar className="w-5 h-5 text-gray-400" />
              <span className="text-lg font-extrabold text-gray-800">{latestReport.report_date}</span>
            </div>
            <span className="text-[10px] text-gray-400 mt-1">样本容量: {latestReport.total_evaluated} 条会话</span>
          </div>

          <div className="bg-white p-5 rounded-2xl border border-gray-100 shadow-sm flex flex-col justify-between">
            <span className="text-xs text-gray-400 font-bold uppercase tracking-wider">Faithfulness (忠实度)</span>
            <span className={`text-2xl font-black mt-2 ${latestReport.faithfulness >= alertThreshold ? 'text-emerald-600' : 'text-red-500'}`}>
              {(latestReport.faithfulness * 100).toFixed(1)}%
            </span>
            <span className="text-[10px] text-gray-400 mt-1">评估回答中是否有幻觉或捏造事实</span>
          </div>

          <div className="bg-white p-5 rounded-2xl border border-gray-100 shadow-sm flex flex-col justify-between">
            <span className="text-xs text-gray-400 font-bold uppercase tracking-wider">Context Relevance (检索相关性)</span>
            <span className={`text-2xl font-black mt-2 ${latestReport.context_relevance >= alertThreshold ? 'text-emerald-600' : 'text-red-500'}`}>
              {(latestReport.context_relevance * 100).toFixed(1)}%
            </span>
            <span className="text-[10px] text-gray-400 mt-1">评估召回文本与用户提问的吻合度</span>
          </div>

          <div className="bg-white p-5 rounded-2xl border border-gray-100 shadow-sm flex flex-col justify-between">
            <span className="text-xs text-gray-400 font-bold uppercase tracking-wider">Answer Relevance (回答相关性)</span>
            <span className={`text-2xl font-black mt-2 ${latestReport.answer_relevance >= alertThreshold ? 'text-emerald-600' : 'text-red-500'}`}>
              {(latestReport.answer_relevance * 100).toFixed(1)}%
            </span>
            <span className="text-[10px] text-gray-400 mt-1">评估最终公文/解答是否切实对准提问</span>
          </div>
        </div>
      ) : (
        <div className="bg-white p-6 rounded-2xl border border-gray-200 text-center text-gray-400 text-sm">
          💡 暂无历史评测跑批数据，评测将在每日凌晨定时运行。
        </div>
      )}

      {hasAlert && (
        <div className="flex items-center gap-3 bg-rose-50 border border-rose-200 text-rose-800 p-4 rounded-2xl shadow-sm">
          <ShieldAlert className="w-6 h-6 text-rose-500 shrink-0 animate-bounce" />
          <div>
            <h4 className="text-sm font-bold">🚨 警告：检测到知识库质量衰退红线预警！</h4>
            <p className="text-[11px] text-rose-600 mt-0.5">最近一次跑批中，部分核心检索或回答质量指标已跌破设定阈值 ({alertThreshold.toFixed(2)})，建议排查切片召回或模型 Prompt 质量。</p>
          </div>
        </div>
      )}

      {reports.length > 0 && (
        <div className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm">
          <h3 className="text-sm font-bold text-gray-800 mb-4 flex items-center gap-1.5">
            <BarChart2 className="w-4 h-4 text-indigo-500" />
            最近 30 日质量指标趋势变化曲线
          </h3>
          <div className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={reports}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                <XAxis dataKey="report_date" stroke="#9ca3af" fontSize={10} />
                <YAxis domain={[0, 1.0]} stroke="#9ca3af" fontSize={10} />
                <Tooltip />
                <Legend iconType="circle" wrapperStyle={{ fontSize: 11 }} />
                <Line type="monotone" dataKey="faithfulness" name="Faithfulness (忠实)" stroke="#10b981" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
                <Line type="monotone" dataKey="context_relevance" name="Context Relevance (检索)" stroke="#3b82f6" strokeWidth={3} dot={{ r: 4 }} />
                <Line type="monotone" dataKey="answer_relevance" name="Answer Relevance (回答)" stroke="#8b5cf6" strokeWidth={3} dot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
