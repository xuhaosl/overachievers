// 极简 Markdown 渲染：先转义 HTML 防注入，再支持标题/加粗/行内代码/列表/换行。
// 供 AiChat 与 Agent 工作台共用。
export function md2html(text) {
  let h = String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  h = h
    .replace(/^#{1,6}\s+(.+)$/gm, '<div class="md-h">$1</div>')
    .replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>')
    .replace(/`([^`\n]+)`/g, '<code>$1</code>')
  h = h.replace(/(?:^|\n)((?:[-*]\s+.+(?:\n|$))+)/g, (_, block) =>
    '\n<ul>' +
    block.trim().split('\n').map((l) => `<li>${l.replace(/^[-*]\s+/, '')}</li>`).join('') +
    '</ul>',
  )
  h = h.replace(/(?:^|\n)((?:\d+[.、]\s+.+(?:\n|$))+)/g, (_, block) =>
    '\n<ol>' +
    block.trim().split('\n').map((l) => `<li>${l.replace(/^\d+[.、]\s+/, '')}</li>`).join('') +
    '</ol>',
  )
  h = h
    .replace(/\n*(<\/?(?:ul|ol)>)/g, '$1')
    .replace(/(<\/li>)\n/g, '$1')
    .replace(/\n/g, '<br>')
  return h
}
