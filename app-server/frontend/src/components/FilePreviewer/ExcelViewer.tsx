/**
 * ExcelViewer - Excel (.xlsx/.xls) 表格预览组件
 * WHY: 替代纯文本 <pre> 渲染，用 SheetJS 解析为真实 HTML 表格，
 *      支持合并单元格、多 Sheet 切换、冻结首行表头。
 */
import { useState, useEffect, useMemo } from 'react';
import * as XLSX from 'xlsx';
import { Loader2, Table2 } from 'lucide-react';

interface ExcelViewerProps {
  blob: Blob;
  filename: string;
}

interface SheetData {
  name: string;
  rows: (string | number | null)[][];
  merges: XLSX.Range[];
  colCount: number;
  rowOffset: number; // 增加此字段
}

// WHY: 限制渲染行数，防止 10 万行的国土报表撑爆浏览器
const MAX_RENDER_ROWS = 3000;

export default function ExcelViewer({ blob, filename }: ExcelViewerProps) {
  const [sheets, setSheets] = useState<SheetData[]>([]);
  const [activeSheet, setActiveSheet] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    blob.arrayBuffer()
      .then(buffer => {
        // WHY: SheetJS 支持合并单元格解析（cellStyles 非必需故关闭以提升性能）
        const wb = XLSX.read(buffer, { type: 'array', cellDates: true });

        const parsed: SheetData[] = wb.SheetNames.map(name => {
          const ws = wb.Sheets[name];
          // 获取原始二维数组（包含 null）
          const rows: (string | number | null)[][] = XLSX.utils.sheet_to_json(ws, {
            header: 1,
            defval: null,
            raw: false,
          });
          const merges = ws['!merges'] || [];
          const ref = ws['!ref'];
          let colCount = 0;
          let rowOffset = 0;
          if (ref) {
            const range = XLSX.utils.decode_range(ref);
            colCount = range.e.c + 1;
            rowOffset = range.s.r;
          }
          return { name, rows: rows.slice(0, MAX_RENDER_ROWS), merges, colCount, rowOffset };
        });

        if (!cancelled) {
          setSheets(parsed);
          setActiveSheet(0);
          setLoading(false);
        }
      })
      .catch(e => {
        if (!cancelled) {
          setError(`Excel 解析失败: ${e.message}`);
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [blob]);

  const sheet = sheets[activeSheet];

  // WHY: 构建合并单元格映射表 → { "r,c": { rowSpan, colSpan } | "skip" }
  // 核心重构：引入 rowOffset 将物理绝对坐标对齐 rows 数组相对索引，防止由于 Excel 前部隐藏空行产生上下行错位
  const mergeMap = useMemo(() => {
    if (!sheet) return {};
    const map: Record<string, { rowSpan: number; colSpan: number } | 'skip'> = {};
    const offset = sheet.rowOffset || 0;
    for (const m of sheet.merges) {
      const rs = m.e.r - m.s.r + 1;
      const cs = m.e.c - m.s.c + 1;
      
      const rel_s_r = m.s.r - offset;
      if (rel_s_r >= 0) {
        map[`${rel_s_r},${m.s.c}`] = { rowSpan: rs, colSpan: cs };
      }
      
      // 标记被合并覆盖的单元格为 skip
      for (let r = m.s.r; r <= m.e.r; r++) {
        const rel_r = r - offset;
        if (rel_r < 0) continue;
        for (let c = m.s.c; c <= m.e.c; c++) {
          if (r !== m.s.r || c !== m.s.c) {
            map[`${rel_r},${c}`] = 'skip';
          }
        }
      }
    }
    return map;
  }, [sheet]);

  // ── 智能识别表头行数 ──
  // 查找数据起始行（第一列为 1 或 1.0 的行）。若未找到，默认第一行（索引 0）为表头。
  const headerRowCount = useMemo(() => {
    if (!sheet || !sheet.rows) return 1;
    let count = 1;
    const scanLimit = Math.min(10, sheet.rows.length);
    for (let r = 0; r < scanLimit; r++) {
      const row = sheet.rows[r];
      const firstVal = row?.[0];
      if (firstVal !== null && firstVal !== undefined) {
        const s = String(firstVal).trim();
        if (s === '1' || s === '1.0') {
          count = r;
          break;
        }
      }
    }
    return count;
  }, [sheet?.rows]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full gap-3 text-gray-400">
        <Loader2 className="w-6 h-6 animate-spin" />
        <span className="text-sm">正在解析 Excel 文件...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full text-red-400 text-sm">
        {error}
      </div>
    );
  }

  if (!sheet || sheet.rows.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        工作表为空
      </div>
    );
  }

  const totalRows = sheet.rows.length;

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Sheet 标签栏 */}
      {sheets.length > 1 && (
        <div className="flex items-center gap-0.5 px-3 py-1.5 bg-gray-100 border-b border-gray-200 shrink-0 overflow-x-auto">
          {sheets.map((s, i) => (
            <button
              key={s.name}
              onClick={() => setActiveSheet(i)}
              className={`px-3 py-1 text-xs rounded-t-md border border-b-0 transition-colors whitespace-nowrap ${
                i === activeSheet
                  ? 'bg-white text-gray-800 font-medium border-gray-300'
                  : 'bg-gray-50 text-gray-500 border-transparent hover:bg-gray-200'
              }`}
            >
              <Table2 className="w-3 h-3 inline mr-1" />
              {s.name}
            </button>
          ))}
        </div>
      )}

      {/* 表格区域 */}
      <div className="flex-1 overflow-auto">
        <table className="excel-table border-collapse text-xs">
          <thead className="sticky top-0 z-20 bg-[#e8eaed]">
            {sheet.rows.slice(0, headerRowCount).map((row, ri) => (
              <tr key={ri}>
                {/* 冻结首列行号，z-30 保证在 x-轴 滚动时置于最上层 */}
                <th className="excel-row-num sticky left-0 z-30">
                  {ri + 1}
                </th>
                {Array.from({ length: sheet.colCount }, (_, c) => {
                  const key = `${ri},${c}`;
                  const m = mergeMap[key];
                  if (m === 'skip') return null; // 核心修复：被合并覆盖的幽灵单元格不渲染，防止列错位
                  const span = m as { rowSpan: number, colSpan: number } | undefined;
                  return (
                    <th
                      key={c}
                      className="excel-header-cell"
                      rowSpan={span?.rowSpan}
                      colSpan={span?.colSpan}
                    >
                      {row?.[c] ?? ''}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {sheet.rows.slice(headerRowCount).map((row, ri) => (
              <tr key={ri + headerRowCount} className={ri % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}>
                {/* 行号 */}
                <td className="excel-row-num sticky left-0 z-10">
                  {ri + headerRowCount + 1}
                </td>
                {Array.from({ length: sheet.colCount }, (_, c) => {
                  const key = `${ri + headerRowCount},${c}`;
                  const m = mergeMap[key];
                  if (m === 'skip') return null; // 核心修复：被合并覆盖的幽灵单元格不渲染，防止列错位
                  const span = m as { rowSpan: number, colSpan: number } | undefined;
                  const val = row?.[c];
                  // WHY: 数字/金额右对齐，和 Excel 保持一致
                  const isNum = val !== null && val !== '' && !isNaN(Number(val));
                  const isMergedCell = !!(span && (span.rowSpan > 1 || span.colSpan > 1));
                  return (
                    <td
                      key={c}
                      className={`excel-cell ${isNum ? 'text-right' : ''} ${isMergedCell ? 'excel-merged-cell' : ''}`}
                      rowSpan={span?.rowSpan}
                      colSpan={span?.colSpan}
                    >
                      {val ?? ''}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>

        {totalRows >= MAX_RENDER_ROWS && (
          <div className="text-center py-3 text-xs text-amber-600 bg-amber-50 border-t border-amber-200">
            ⚠️ 仅显示前 {MAX_RENDER_ROWS} 行（共 {totalRows}+ 行），完整数据请下载原件查看
          </div>
        )}
      </div>

      {/* 底部状态栏 */}
      <div className="flex items-center justify-between px-4 py-1.5 bg-gray-50 border-t border-gray-200 text-[11px] text-gray-500 shrink-0">
        <span>{sheet.name} · {totalRows} 行 × {sheet.colCount} 列</span>
        <span>{filename}</span>
      </div>

      <style>{`
        .excel-table {
          min-width: 100%;
        }
        .excel-table thead {
          position: sticky;
          top: 0;
          z-index: 20;
        }
        .excel-header-cell {
          background: #e8eaed;
          color: #333;
          font-weight: 600;
          padding: 5px 8px;
          border: 1px solid #c5c8cc;
          text-align: center;
          white-space: nowrap;
        }
        .excel-cell {
          padding: 4px 8px;
          border: 1px solid #dde1e6;
          white-space: nowrap;
          max-width: 300px;
          overflow: hidden;
          text-overflow: ellipsis;
          color: #333;
        }
        .excel-merged-cell {
          text-align: center !important;
          vertical-align: middle !important;
          white-space: normal !important;
        }
        .excel-row-num {
          background: #f0f1f3;
          color: #666;
          font-weight: 500;
          text-align: center;
          padding: 4px 6px;
          border: 1px solid #c5c8cc;
          min-width: 40px;
          font-size: 10px;
        }
        .excel-table tr:hover td:not(.excel-row-num) {
          background: #e8f0fe !important;
        }
      `}</style>
    </div>
  );
}
