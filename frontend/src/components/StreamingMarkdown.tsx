import React from 'react'
import { escapeHtml } from '../utils'

interface StreamingMarkdownProps {
  content: string
}

const StreamingMarkdown: React.FC<StreamingMarkdownProps> = ({ content }) => {
  const isLikelyMarkdown = content.includes('```') || content.includes('**') || content.includes('##') || content.includes('- ') || content.includes('| ')
  if (!isLikelyMarkdown && content.length < 100) {
    return <span className="whitespace-pre-wrap">{escapeHtml(content)}</span>
  }
  if (isLikelyMarkdown) {
    const MarkdownRenderer = React.lazy(() => import('./MarkdownRenderer'))
    return (
      <React.Suspense fallback={<span className="whitespace-pre-wrap">{escapeHtml(content)}</span>}>
        <MarkdownRenderer content={content} />
      </React.Suspense>
    )
  }
  return <span className="whitespace-pre-wrap">{escapeHtml(content)}</span>
}

export default StreamingMarkdown
