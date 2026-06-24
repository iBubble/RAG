/**
 * markdownUtils.ts — Markdown 文本处理纯函数
 *
 * WHY: 从 DocumentStudio.tsx 抽离，便于单元测试和复用。
 *      这些函数不依赖 React/DOM，是纯粹的字符串变换。
 */

/**
 * 将文本中的 Markdown 表格转为 HTML <table>。
 * WHY: LLM 输出的 Markdown 表格在 SSE 流式接收时被 replace(/\n/g, '<br/>')
 *      破坏了行结构，变成了纯文本段落。需要后处理为 HTML table
 *      才能让 Tiptap Table 扩展和 CSS 样式生效。
 */
export function convertMarkdownTables(html: string): string {
  // 将 <br/> 还原为 \n（SSE 处理时替换的）
  const text = html.replace(/<br\s*\/?>/gi, '\n');

  // 匹配连续的 Markdown 表格行，兼容被 <p> 标签包裹的情况（至少 3 行：表头 + 分隔符 + 数据行）
  const tableRegex = /(?:<p>)?\s*((?:\|.+?\|\s*(?:\n|<\/p>|$)){3,})/gm;

  return text.replace(tableRegex, (match, tableBlock) => {
    // 剔除遗留的 <p> 或 </p> 标签，并按行拆分
    const lines = tableBlock.replace(/<\/?p>/ig, '').trim().split('\n')
      .filter((l: string) => l.trim().startsWith('|'));

    if (lines.length < 3) return match;

    const sepLine = lines[1].trim();
    // 验证分隔符行格式（| --- | --- |）
    if (!/^\|[\s\-:]+(?:\|[\s\-:]+)*\|$/.test(sepLine)) {
      return match;
    }

    const parseCells = (line: string) =>
      line.trim().replace(/^\||\\|$/g, '').split('|').map((c: string) => c.trim());

    const headerCells = parseCells(lines[0]);
    const dataLines = lines.slice(2);

    let tableHtml = '<table><thead><tr>';
    for (const cell of headerCells) {
      tableHtml += `<th><p>${cell}</p></th>`;
    }
    tableHtml += '</tr></thead><tbody>';

    for (const dataLine of dataLines) {
      // 跳过可能的多余分隔行
      if (/^\|[\s\-:]+(?:\|[\s\-:]+)*\|$/.test(dataLine.trim())) continue;
      const cells = parseCells(dataLine);
      tableHtml += '<tr>';
      for (let i = 0; i < headerCells.length; i++) {
        tableHtml += `<td><p>${cells[i] || ''}</p></td>`;
      }
      tableHtml += '</tr>';
    }
    tableHtml += '</tbody></table>';

    return tableHtml;
  });
}

/**
 * 预处理 raw Markdown：在表格边界强制插入空行 + 修复被管道符包裹的文本。
 *
 * WHY: marked.parse 在 breaks:true + GFM 模式下有一个严重的贪婪解析行为：
 *      当 Markdown 表格最后一行之后没有空行时，紧接着的文本行会被吸收为
 *      表格的续行（<td>文字</td>），导致叙述性段落被渲染在窄表格列中。
 *
 * 策略：
 *   1. 检测管道符行→非管道符行的边界，强制插入空行切断表格解析
 *   2. 检测被管道符错误包裹的纯文本行（仅 1 个非空单元格），提取为段落
 *   3. 移除 Markdown 水平线标记（---、***、___），它们在技术报告中无意义
 */
export function sanitizeTableMarkdown(md: string): string {
  const lines = md.split('\n');
  const result: string[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    const prevLine = i > 0 ? lines[i - 1].trim() : '';

    // ── 策略 3：移除水平线标记 ──
    // WHY: LLM 有时输出 --- 或 *** 作为章节分隔符，或者 sanitizer 在表格
    //      边界插入空行后使原本在表格内的 | --- | 变成独立的 ---，
    //      marked.parse 会将其解析为 <hr>，Tailwind prose 渲染为可见横线。
    //      技术报告中不需要水平线，直接移除。
    if (/^-{3,}$/.test(line) || /^\*{3,}$/.test(line) || /^_{3,}$/.test(line)) {
      // 不是管道符包裹的表格分隔行，是独立的水平线标记 → 跳过
      continue;
    }

    // ── 策略 1：表格→文本边界强制空行 ──
    // WHY: 如果上一行是管道符行（表格行），当前行不是管道符行也不是空行，
    //      marked 会贪婪地把当前行吸收进表格。插入空行切断这个行为。
    if (prevLine.startsWith('|') && prevLine.endsWith('|')
        && line.length > 0
        && !line.startsWith('|')) {
      result.push('');  // 强制空行
    }

    // ── 策略 2：修复被管道符错误包裹的文本行 ──
    if (line.startsWith('|') && line.endsWith('|')) {
      // 分隔符行原样保留
      if (/^\|[\s\-:]+(?:\|[\s\-:]+)*\|$/.test(line)) {
        result.push(lines[i]);
        continue;
      }

      // 解析单元格
      const cells = line.slice(1, -1).split('|').map(c => c.trim());
      const nonEmptyCells = cells.filter(c => c.length > 0);

      // 如果只有 1 个非空单元格且总列数 ≥ 3 → 这是被塞进表格的文本
      if (nonEmptyCells.length === 1 && cells.length >= 3) {
        const text = nonEmptyCells[0];
        result.push('');
        result.push(text);
        result.push('');
        continue;
      }

      // 如果只有 1-2 个非空单元格且最长超 50 字符 → 也是被包裹的文本
      const maxCellLen = Math.max(...cells.map(c => c.length));
      if (nonEmptyCells.length <= 2 && maxCellLen > 50) {
        const text = nonEmptyCells.join(' ').trim();
        result.push('');
        result.push(text);
        result.push('');
        continue;
      }
    }

    result.push(lines[i]);
  }

  return result.join('\n');
}

/**
 * 从 marked.parse 输出的 HTML 中移除 <hr> 标签。
 *
 * WHY: 即使 sanitizeTableMarkdown 已移除了 --- 标记，某些 marked 版本
 *      或边缘情况仍可能生成 <hr>。作为最后一道防线，在 HTML 层面移除所有 <hr>。
 *      技术报告文档中不应出现水平分隔线。
 */
export function removeHrFromHtml(html: string): string {
  return html.replace(/<hr\s*\/?>/gi, '');
}
