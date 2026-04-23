const escapeHtml = (value = '') =>
  String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

const renderInline = (value = '') => {
  let html = value

  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a class="md-link" href="$2" target="_blank" rel="noreferrer">$1</a>')
  html = html.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/(^|[\s(])\*([^*]+)\*(?=[\s).,!?]|$)/g, '$1<em>$2</em>')
  html = html.replace(/(^|[\s(])_([^_]+)_(?=[\s).,!?]|$)/g, '$1<em>$2</em>')

  return html
}

export const renderMarkdown = (content, options = {}) => {
  if (!content) return ''

  const { stripLeadingTitle = false } = options
  let source = escapeHtml(String(content).replace(/\r\n?/g, '\n').trim())
  if (!source) return ''

  if (stripLeadingTitle) {
    source = source.replace(/^##?\s+.+\n+/, '')
  }

  const codeBlocks = []
  source = source.replace(/```([\w-]*)\n([\s\S]*?)```/g, (_, language, code) => {
    const token = `@@CODE_BLOCK_${codeBlocks.length}@@`
    codeBlocks.push({
      language: language || '',
      code: code.replace(/\n$/, '')
    })
    return token
  })

  const lines = source.split('\n')
  const html = []
  let paragraphLines = []
  let listType = null

  const flushParagraph = () => {
    if (!paragraphLines.length) return
    html.push(`<p class="md-p">${renderInline(paragraphLines.join('<br>'))}</p>`)
    paragraphLines = []
  }

  const closeList = () => {
    if (!listType) return
    html.push(listType === 'ol' ? '</ol>' : '</ul>')
    listType = null
  }

  const openList = (nextType) => {
    if (listType === nextType) return
    closeList()
    html.push(nextType === 'ol' ? '<ol class="md-ol">' : '<ul class="md-ul">')
    listType = nextType
  }

  for (const rawLine of lines) {
    const trimmed = rawLine.trim()

    if (!trimmed) {
      flushParagraph()
      closeList()
      continue
    }

    if (/^@@CODE_BLOCK_\d+@@$/.test(trimmed)) {
      flushParagraph()
      closeList()
      html.push(trimmed)
      continue
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      flushParagraph()
      closeList()
      const level = Math.min(heading[1].length + 1, 5)
      html.push(`<h${level} class="md-h${level}">${renderInline(heading[2])}</h${level}>`)
      continue
    }

    if (/^---+$/.test(trimmed)) {
      flushParagraph()
      closeList()
      html.push('<hr class="md-hr">')
      continue
    }

    const blockquote = trimmed.match(/^>\s+(.+)$/)
    if (blockquote) {
      flushParagraph()
      closeList()
      html.push(`<blockquote class="md-quote">${renderInline(blockquote[1])}</blockquote>`)
      continue
    }

    const orderedList = rawLine.match(/^(\s*)(\d+)\.\s+(.+)$/)
    if (orderedList) {
      flushParagraph()
      openList('ol')
      const level = Math.floor((orderedList[1] || '').length / 2)
      html.push(`<li class="md-oli" data-level="${level}">${renderInline(orderedList[3].trim())}</li>`)
      continue
    }

    const unorderedList = rawLine.match(/^(\s*)[-*]\s+(.+)$/)
    if (unorderedList) {
      flushParagraph()
      openList('ul')
      const level = Math.floor((unorderedList[1] || '').length / 2)
      html.push(`<li class="md-li" data-level="${level}">${renderInline(unorderedList[2].trim())}</li>`)
      continue
    }

    closeList()
    paragraphLines.push(trimmed)
  }

  flushParagraph()
  closeList()

  let rendered = html.join('')
  rendered = rendered.replace(/@@CODE_BLOCK_(\d+)@@/g, (_, index) => {
    const block = codeBlocks[Number(index)]
    if (!block) return ''
    const langAttr = block.language ? ` data-lang="${block.language}"` : ''
    return `<pre class="code-block"${langAttr}><code>${block.code}</code></pre>`
  })

  return rendered
}
