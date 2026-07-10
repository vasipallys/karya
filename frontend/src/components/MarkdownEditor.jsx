import {
  Bold,
  Code,
  Code2,
  Columns2,
  Copy,
  FileText,
  Heading,
  Image as ImageIcon,
  Italic,
  Link2,
  List,
  ListChecks,
  ListOrdered,
  PencilRuler,
  Quote,
  Sparkles,
  Strikethrough,
  Table,
} from 'lucide-react'
import mermaid from 'mermaid'
import { Children, forwardRef, isValidElement, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import MermaidView from './MermaidView'

mermaid.initialize({
  startOnLoad: false,
  securityLevel: 'strict',
  theme: 'base',
  themeVariables: {
    primaryColor: '#d3e3fd',
    primaryTextColor: '#1f1f1f',
    primaryBorderColor: '#0b57d0',
    lineColor: '#5f6368',
    secondaryColor: '#e6f4ea',
    tertiaryColor: '#fef7e0',
    fontFamily: 'Roboto, sans-serif',
  },
})

export const MERMAID_BLOCK_TEMPLATE = `

\`\`\`mermaid
flowchart LR
  User["User"] --> Experience["Experience"]
  Experience --> Service["Business service"]
  Service --> Outcome["Outcome"]
\`\`\`
`

const TABLE_TEMPLATE = `| Column A | Column B |
| --- | --- |
| Value | Value |
`

const MODES = [
  { id: 'edit', label: 'Edit', icon: Code2 },
  { id: 'split', label: 'Split', icon: Columns2 },
  { id: 'preview', label: 'Preview', icon: FileText },
]

export function findMermaidBlocks(markdown) {
  const blocks = []
  const pattern = /```mermaid[^\n]*\n([\s\S]*?)```/gi
  let match = pattern.exec(markdown || '')
  while (match) {
    blocks.push({
      index: blocks.length,
      start: match.index,
      end: match.index + match[0].length,
      source: match[1].trim(),
    })
    match = pattern.exec(markdown || '')
  }
  return blocks
}

function MermaidMarkdownBlock({ source, index, onEdit }) {
  const [mode, setMode] = useState('visual')

  return (
    <section className="md-mermaid-card">
      <header>
        <span><Sparkles size={15} /> Mermaid diagram</span>
        <div>
          {onEdit && <button type="button" onClick={() => onEdit({ index, source })} aria-label="Edit in Diagram Studio"><PencilRuler size={13} /> Edit</button>}
          <button type="button" className={mode === 'visual' ? 'active' : ''} onClick={() => setMode('visual')}>Visual</button>
          <button type="button" className={mode === 'source' ? 'active' : ''} onClick={() => setMode('source')}>Source</button>
          <button type="button" aria-label="Copy Mermaid source" onClick={() => navigator.clipboard?.writeText(source)}><Copy size={13} /></button>
        </div>
      </header>
      {mode === 'source'
        ? <pre><code>{source}</code></pre>
        : <MermaidView source={source} fit="width" className="md-mermaid-visual" />}
    </section>
  )
}

export function MarkdownViewer({ content, empty = '*No content yet.*', onEditMermaid }) {
  const headingIds = new Map()
  let mermaidIndex = 0
  const heading = (level) => function MarkdownHeading({ children }) {
    const text = Children.toArray(children).join('')
    const base = text.toLowerCase().replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-')
    const count = headingIds.get(base) || 0
    headingIds.set(base, count + 1)
    const id = count ? `${base}-${count + 1}` : base
    const Tag = `h${level}`
    return <Tag id={id}>{children}</Tag>
  }

  return (
    <article className="md-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children, ...props }) => <a {...props} target={props.href?.startsWith('#') ? undefined : '_blank'} rel="noreferrer">{children}</a>,
          h1: heading(1),
          h2: heading(2),
          h3: heading(3),
          h4: heading(4),
          pre: ({ children }) => {
            const child = Children.count(children) === 1 ? Children.only(children) : null
            const language = isValidElement(child) ? /language-([\w-]+)/.exec(child.props.className || '')?.[1] : null
            const source = isValidElement(child) ? String(child.props.children).replace(/\n$/, '') : ''
            if (language === 'mermaid') {
              const index = mermaidIndex
              mermaidIndex += 1
              return <MermaidMarkdownBlock source={source} index={index} onEdit={onEditMermaid} />
            }
            return <pre>{children}</pre>
          },
        }}>
        {content || empty}
      </ReactMarkdown>
    </article>
  )
}

function svgToPng(svg) {
  const viewBox = /viewBox="[^"]*\s([\d.]+)\s([\d.]+)"/i.exec(svg)
  const sourceWidth = Number(viewBox?.[1]) || 1000
  const sourceHeight = Number(viewBox?.[2]) || 600
  const width = Math.min(1800, Math.max(900, sourceWidth * 2))
  const height = Math.min(1200, Math.max(500, width * sourceHeight / sourceWidth))
  const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }))
  return new Promise((resolve, reject) => {
    const image = new window.Image()
    image.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        canvas.width = width
        canvas.height = height
        const context = canvas.getContext('2d')
        context.fillStyle = '#ffffff'
        context.fillRect(0, 0, width, height)
        context.drawImage(image, 0, 0, width, height)
        resolve(canvas.toDataURL('image/png'))
      } catch (error) {
        reject(error)
      } finally {
        URL.revokeObjectURL(url)
      }
    }
    image.onerror = (error) => {
      URL.revokeObjectURL(url)
      reject(error)
    }
    image.src = url
  })
}

export async function renderMermaidImages(markdown) {
  const images = []
  for (const block of findMermaidBlocks(markdown)) {
    try {
      const id = `markdown-export-${Date.now()}-${Math.random().toString(16).slice(2)}`
      const { svg } = await mermaid.render(id, block.source)
      images.push(await svgToPng(svg))
    } catch {
      images.push('')
    }
  }
  return images
}

const MarkdownEditor = forwardRef(function MarkdownEditor({
  value,
  onChange,
  previewValue,
  mode,
  onModeChange,
  defaultMode = 'split',
  onInsertMermaid,
  onEditMermaid,
  toolbarLabel = 'Markdown',
  sourceLabel = 'Markdown source',
  previewLabel = 'Document preview',
  placeholder = 'Write Markdown...',
  spellCheck = true,
  className = '',
}, ref) {
  const [internalMode, setInternalMode] = useState(defaultMode)
  const activeMode = mode || internalMode
  const textareaRef = useRef(null)
  const pendingSelection = useRef(null)
  const text = value || ''

  const setMode = (nextMode) => {
    if (onModeChange) onModeChange(nextMode)
    else setInternalMode(nextMode)
  }

  useLayoutEffect(() => {
    const range = pendingSelection.current
    const textarea = textareaRef.current
    if (!range || !textarea) return
    pendingSelection.current = null
    textarea.focus()
    textarea.setSelectionRange(range[0], range[1])
  }, [text])

  const commit = (nextValue, selection) => {
    if (selection) pendingSelection.current = selection
    onChange(nextValue)
    if (activeMode === 'preview') setMode('split')
  }

  const selectionRange = () => {
    const textarea = textareaRef.current
    const start = textarea?.selectionStart ?? text.length
    const end = textarea?.selectionEnd ?? start
    return [start, end]
  }

  const focusRange = (from, to) => {
    pendingSelection.current = [from, to]
  }

  const wrapSelection = (before, after, fallback) => {
    const [start, end] = selectionRange()
    const selected = text.slice(start, end) || fallback
    commit(text.slice(0, start) + before + selected + after + text.slice(end), [start + before.length, start + before.length + selected.length])
  }

  const prefixSelectedLines = (transform) => {
    const [start, end] = selectionRange()
    const from = text.lastIndexOf('\n', start - 1) + 1
    const nextBreak = text.indexOf('\n', end)
    const to = nextBreak === -1 ? text.length : nextBreak
    const updated = text.slice(from, to).split('\n').map(transform).join('\n')
    commit(text.slice(0, from) + updated + text.slice(to), [from, from + updated.length])
  }

  const insertSnippet = (snippet) => {
    const [start, end] = selectionRange()
    const block = (start > 0 && text[start - 1] !== '\n' ? '\n' : '') + snippet
    commit(text.slice(0, start) + block + text.slice(end), [start + block.length, start + block.length])
  }

  const insertMermaidSource = (source) => {
    insertSnippet(`\`\`\`mermaid\n${String(source || '').trim()}\n\`\`\`\n`)
  }

  const replaceMermaidBlock = (index, source) => {
    const block = findMermaidBlocks(text)[index]
    if (!block) return false
    const nextBlock = `\`\`\`mermaid\n${String(source || '').trim()}\n\`\`\``
    commit(text.slice(0, block.start) + nextBlock + text.slice(block.end), [block.start + nextBlock.length, block.start + nextBlock.length])
    return true
  }

  const insertCode = () => {
    const [start, end] = selectionRange()
    if (start !== end) wrapSelection('`', '`', 'code')
    else insertSnippet('```\ncode\n```\n')
  }

  useImperativeHandle(ref, () => ({
    focus: () => textareaRef.current?.focus(),
    focusRange,
    insertSnippet,
    insertMermaidSource,
    replaceMermaidBlock,
    textarea: textareaRef.current,
  }))

  const tools = [
    { key: 'bold', label: 'Bold', icon: Bold, run: () => wrapSelection('**', '**', 'bold text') },
    { key: 'italic', label: 'Italic', icon: Italic, run: () => wrapSelection('_', '_', 'italic text') },
    { key: 'heading', label: 'Heading', icon: Heading, run: () => prefixSelectedLines((line) => `## ${line.replace(/^#{1,6}\s+/, '')}`) },
    { key: 'strike', label: 'Strikethrough', icon: Strikethrough, run: () => wrapSelection('~~', '~~', 'strikethrough') },
    { sep: true, key: 'sep1' },
    { key: 'ul', label: 'Bulleted list', icon: List, run: () => prefixSelectedLines((line) => `- ${line.replace(/^[-*]\s+/, '')}`) },
    { key: 'ol', label: 'Numbered list', icon: ListOrdered, run: () => prefixSelectedLines((line, index) => `${index + 1}. ${line.replace(/^\d+\.\s+/, '')}`) },
    { key: 'task', label: 'Task list', icon: ListChecks, run: () => prefixSelectedLines((line) => `- [ ] ${line.replace(/^-\s*\[[ xX]\]\s*/, '').replace(/^[-*]\s+/, '')}`) },
    { key: 'quote', label: 'Quote', icon: Quote, run: () => prefixSelectedLines((line) => `> ${line.replace(/^>\s?/, '')}`) },
    { sep: true, key: 'sep2' },
    { key: 'code', label: 'Code', icon: Code, run: insertCode },
    { key: 'table', label: 'Table', icon: Table, run: () => insertSnippet(TABLE_TEMPLATE) },
    { key: 'link', label: 'Link', icon: Link2, run: () => wrapSelection('[', '](https://)', 'link text') },
    { key: 'image', label: 'Image', icon: ImageIcon, run: () => wrapSelection('![', '](https://)', 'alt text') },
  ]

  return (
    <div className={`md-editor mode-${activeMode} ${className}`.trim()}>
      <header className="md-editor-toolbar" onMouseDown={(event) => { if (event.target.closest('button')) event.preventDefault() }}>
        <div className="md-tool-group">
          {tools.map((tool) => tool.sep
            ? <span key={tool.key} className="md-tool-sep" aria-hidden="true" />
            : <button key={tool.key} type="button" className="md-tool-btn" onClick={tool.run} title={tool.label} aria-label={tool.label}><tool.icon size={15} /></button>)}
          {onInsertMermaid && <button type="button" className="md-tool-btn accent" onClick={onInsertMermaid} title="Insert Mermaid diagram" aria-label="Insert Mermaid diagram"><Sparkles size={15} /></button>}
        </div>
        <span className="md-toolbar-label">{toolbarLabel}</span>
        <div className="md-mode-toggle">
          {MODES.map((item) => <button key={item.id} type="button" className={activeMode === item.id ? 'active' : ''} onClick={() => setMode(item.id)}><item.icon size={14} /> {item.label}</button>)}
        </div>
      </header>
      <div className="md-editor-grid">
        {activeMode !== 'preview' && (
          <section className="md-source-pane">
            <header>{sourceLabel}</header>
            <textarea ref={textareaRef} spellCheck={spellCheck} value={text} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} aria-label={sourceLabel} />
          </section>
        )}
        {activeMode !== 'edit' && (
          <section className="md-preview-pane">
            <header>{previewLabel}</header>
            <MarkdownViewer content={previewValue ?? text} onEditMermaid={onEditMermaid} />
          </section>
        )}
      </div>
    </div>
  )
})

export default MarkdownEditor
