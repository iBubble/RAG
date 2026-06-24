import { useState, useMemo } from 'react';

/**
 * DataTable - 数据分析结果专用表格渲染组件
 *
 * WHY: AI 数据分析模式返回的 Markdown 表格需要特殊渲染，
 *      提供排序、高亮数值、紧凑布局等增强功能，
 *      区别于普通文本消息的 whitespace-pre-wrap 渲染。
 */

interface DataTableProps {
  markdown: string;
}

type SortDir = 'asc' | 'desc' | null;

export default function DataTable({ markdown }: DataTableProps) {
  const [sortCol, setSortCol] = useState<number | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>(null);

  // 解析 Markdown 表格
  const { headers, rows } = useMemo(() => {
    const lines = markdown.split('\n').filter(l => l.trim().startsWith('|'));
    if (lines.length < 2) return { headers: [] as string[], rows: [] as string[][] };

    const parseRow = (line: string) =>
      line.split('|').slice(1, -1).map(c => c.trim());

    const headers = parseRow(lines[0]);

    // 跳过分隔行（---）
    const dataLines = lines.slice(1).filter(
      l => !l.replace(/[|\-\s:]/g, '').match(/^$/)
    );

    const rows = dataLines.map(parseRow);
    return { headers, rows };
  }, [markdown]);

  // 排序
  const sortedRows = useMemo(() => {
    if (sortCol === null || sortDir === null) return rows;

    return [...rows].sort((a, b) => {
      const va = a[sortCol] ?? '';
      const vb = b[sortCol] ?? '';
      const na = parseFloat(va.replace(/,/g, ''));
      const nb = parseFloat(vb.replace(/,/g, ''));

      // 数值比较
      if (!isNaN(na) && !isNaN(nb)) {
        return sortDir === 'asc' ? na - nb : nb - na;
      }
      // 字符串比较
      return sortDir === 'asc'
        ? va.localeCompare(vb, 'zh')
        : vb.localeCompare(va, 'zh');
    });
  }, [rows, sortCol, sortDir]);

  const handleSort = (colIdx: number) => {
    if (sortCol === colIdx) {
      // 循环: asc → desc → null
      if (sortDir === 'asc') setSortDir('desc');
      else if (sortDir === 'desc') { setSortCol(null); setSortDir(null); }
    } else {
      setSortCol(colIdx);
      setSortDir('asc');
    }
  };

  const isNumeric = (val: string) => {
    const cleaned = val.replace(/,/g, '').trim();
    return cleaned !== '' && !isNaN(Number(cleaned));
  };

  if (headers.length === 0) {
    return <div className="whitespace-pre-wrap text-sm">{markdown}</div>;
  }

  return (
    <div className="my-2 rounded-lg border border-teal-200/60 overflow-hidden shadow-sm">
      {/* 表格标题栏 */}
      <div className="px-3 py-1.5 bg-teal-50/80 border-b border-teal-100 flex items-center justify-between">
        <span className="text-[11px] text-teal-700 font-medium flex items-center gap-1">
          📊 查询结果
          <span className="text-teal-500 font-normal">
            ({sortedRows.length} 行 × {headers.length} 列)
          </span>
        </span>
        <button
          onClick={() => {
            // 复制为 TSV 格式
            const tsv = [headers.join('\t'), ...sortedRows.map(r => r.join('\t'))].join('\n');
            navigator.clipboard.writeText(tsv);
          }}
          className="text-[10px] text-teal-600 hover:text-teal-800 hover:bg-teal-100 px-2 py-0.5 rounded transition-colors"
          title="复制为 TSV（可粘贴到 Excel）"
        >
          📋 复制
        </button>
      </div>

      {/* 表格内容 */}
      <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
        <table className="w-full text-[12px] leading-tight">
          <thead className="sticky top-0 z-10">
            <tr className="bg-gray-50 border-b border-gray-200">
              {headers.map((h, i) => (
                <th
                  key={i}
                  onClick={() => handleSort(i)}
                  className="px-2.5 py-2 text-left font-semibold text-gray-700 whitespace-nowrap cursor-pointer hover:bg-gray-100 select-none transition-colors border-r border-gray-100 last:border-r-0"
                >
                  <span className="flex items-center gap-1">
                    {h}
                    <span className="text-[9px] text-gray-400">
                      {sortCol === i
                        ? sortDir === 'asc' ? '▲' : '▼'
                        : '⇅'
                      }
                    </span>
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row, ri) => (
              <tr
                key={ri}
                className={`border-b border-gray-50 hover:bg-teal-50/30 transition-colors ${
                  ri % 2 === 0 ? 'bg-white' : 'bg-gray-50/30'
                }`}
              >
                {headers.map((_, ci) => {
                  const val = row[ci] ?? '';
                  const isNum = isNumeric(val);
                  // 高亮合计行
                  const isSummaryRow = row[0] === '合计' || row[0] === '总计' || row[0] === '小计';

                  return (
                    <td
                      key={ci}
                      className={`px-2.5 py-1.5 whitespace-nowrap border-r border-gray-50 last:border-r-0 ${
                        isNum ? 'text-right font-mono tabular-nums text-blue-700' : 'text-gray-700'
                      } ${isSummaryRow ? 'font-bold bg-amber-50/50' : ''}`}
                    >
                      {val}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
