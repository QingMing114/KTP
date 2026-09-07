import React from 'react'
import { escapeHtml } from '../utils'
import MarkdownRenderer from './MarkdownRenderer'

interface StreamingMarkdownProps {
  content: string
}

const StreamingMarkdown: React.FC<StreamingMarkdownProps> = ({ content }) => {
  const isLikelyMarkdown = content.includes('```') || content.includes('**') || content.includes('##') || content.includes('- ') || content.includes('| ') || /<[a-zA-Z][^>]*>/.test(content)
  if (isLikelyMarkdown) {
    return <MarkdownRenderer content={content} />
  }
  return <span className="whitespace-pre-wrap">{escapeHtml(content)}</span>
}

export default StreamingMarkdown
