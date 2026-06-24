/**
 * DocxViewer - Word (.docx) 富文本预览组件
 * WHY: 替代之前的纯文本 <pre> 渲染，用 mammoth.js 将 .docx 转为 HTML，
 *      保留标题层级、表格、加粗/斜体、列表等排版结构。
 * 安全: 使用 DOMPurify 对 mammoth 输出的 HTML 进行消毒，防止 XSS。
 */
import { useState, useEffect } from 'react';
import mammoth from 'mammoth';
import DOMPurify from 'dompurify';
import { Loader2 } from 'lucide-react';

interface DocxViewerProps {
  blob: Blob;
  filename: string;
}

export default function DocxViewer({ blob }: DocxViewerProps) {
  const [html, setHtml] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    blob.arrayBuffer()
      .then(buffer => mammoth.convertToHtml(
        { arrayBuffer: buffer },
        {
          // WHY: 将 Word 标题样式映射为语义化 HTML 标签
          styleMap: [
            "p[style-name='Heading 1'] => h1:fresh",
            "p[style-name='Heading 2'] => h2:fresh",
            "p[style-name='Heading 3'] => h3:fresh",
            "p[style-name='Heading 4'] => h4:fresh",
          ],
        }
      ))
      .then(result => {
        if (cancelled) return;
        // WHY: mammoth 输出的 HTML 需要消毒，防止恶意 .docx 文件注入脚本
        const clean = DOMPurify.sanitize(result.value, {
          ALLOWED_TAGS: [
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's',
            'ul', 'ol', 'li',
            'table', 'thead', 'tbody', 'tr', 'th', 'td',
            'a', 'img', 'span', 'div', 'sup', 'sub',
            'blockquote', 'pre', 'code',
          ],
          ALLOWED_ATTR: ['href', 'src', 'alt', 'colspan', 'rowspan', 'class', 'style'],
        });
        setHtml(clean);
        setLoading(false);
      })
      .catch(e => {
        if (cancelled) return;
        setError(`Word 文档解析失败: ${e.message}`);
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [blob]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full gap-3 text-gray-400">
        <Loader2 className="w-6 h-6 animate-spin" />
        <span className="text-sm">正在解析 Word 文档...</span>
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

  return (
    <div className="h-full overflow-y-auto bg-gray-100 p-6">
      {/* WHY: 模拟 A4 纸排版效果，白色居中容器 + 阴影 + 适当内边距 */}
      <div
        className="docx-viewer mx-auto bg-white shadow-lg rounded-sm"
        style={{
          maxWidth: '794px', // A4 宽度近似
          minHeight: '1123px', // A4 高度近似
          padding: '60px 72px', // Word 默认页边距
        }}
        dangerouslySetInnerHTML={{ __html: html }}
      />

      {/* Scoped CSS for Word-like rendering */}
      <style>{`
        .docx-viewer {
          font-family: "Songti SC", "SimSun", "宋体", serif;
          font-size: 14px;
          line-height: 1.8;
          color: #333;
        }
        .docx-viewer h1 {
          font-family: "Heiti SC", "Microsoft YaHei", "黑体", sans-serif;
          font-size: 22px;
          font-weight: 700;
          margin: 24px 0 12px;
          text-align: center;
          color: #1a1a1a;
        }
        .docx-viewer h2 {
          font-family: "Heiti SC", "Microsoft YaHei", "黑体", sans-serif;
          font-size: 18px;
          font-weight: 600;
          margin: 20px 0 10px;
          color: #222;
          border-bottom: 1px solid #e5e7eb;
          padding-bottom: 6px;
        }
        .docx-viewer h3 {
          font-family: "Heiti SC", "Microsoft YaHei", "黑体", sans-serif;
          font-size: 16px;
          font-weight: 600;
          margin: 16px 0 8px;
          color: #333;
        }
        .docx-viewer h4 {
          font-size: 15px;
          font-weight: 600;
          margin: 12px 0 6px;
          color: #444;
        }
        .docx-viewer p {
          margin: 0 0 8px;
          text-indent: 2em;
        }
        .docx-viewer ul, .docx-viewer ol {
          padding-left: 2em;
          margin: 8px 0;
        }
        .docx-viewer li {
          margin: 4px 0;
        }
        .docx-viewer table {
          width: 100%;
          border-collapse: collapse;
          margin: 16px 0;
          font-size: 13px;
        }
        .docx-viewer th, .docx-viewer td {
          border: 1px solid #999;
          padding: 6px 10px;
          text-align: left;
          text-indent: 0;
        }
        .docx-viewer th {
          background: #f3f4f6;
          font-weight: 600;
        }
        .docx-viewer img {
          max-width: 100%;
          height: auto;
          margin: 12px auto;
          display: block;
        }
        .docx-viewer a {
          color: #2563eb;
          text-decoration: underline;
        }
        .docx-viewer blockquote {
          border-left: 3px solid #d1d5db;
          padding-left: 16px;
          margin: 12px 0;
          color: #6b7280;
        }
      `}</style>
    </div>
  );
}
