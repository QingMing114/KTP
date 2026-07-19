import React, { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import SyntaxHighlighter from 'react-syntax-highlighter/dist/esm/prism-light'
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python'
import json from 'react-syntax-highlighter/dist/esm/languages/prism/json'
import bash from 'react-syntax-highlighter/dist/esm/languages/prism/bash'
import markdown from 'react-syntax-highlighter/dist/esm/languages/prism/markdown'
import yaml from 'react-syntax-highlighter/dist/esm/languages/prism/yaml'
import sql from 'react-syntax-highlighter/dist/esm/languages/prism/sql'
import { Copy, Check } from 'lucide-react'

SyntaxHighlighter.registerLanguage('python', python)
SyntaxHighlighter.registerLanguage('json', json)
SyntaxHighlighter.registerLanguage('bash', bash)
SyntaxHighlighter.registerLanguage('shell', bash)
SyntaxHighlighter.registerLanguage('markdown', markdown)
SyntaxHighlighter.registerLanguage('yaml', yaml)
SyntaxHighlighter.registerLanguage('sql', sql)

interface MarkdownRendererProps {
  content: string
}

const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content }) => {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw]}
      components={{
        code({ className, children, node, ...props }) {
          const match = /language-(\w+)/.exec(className || '')
          const codeString = String(children).replace(/\n$/, '')
          const isInline = !match && !codeString.includes('\n')

          if (!isInline) {
            return <CodeBlock language={match ? match[1] : 'text'} code={codeString} />
          }

          return (
            <code className="bg-stone-100 text-stone-700 px-1.5 py-0.5 rounded text-[13px] font-mono" {...props}>
              {children}
            </code>
          )
        },
        p({ children }) {
          return <p className="mb-3 last:mb-0 leading-relaxed">{children}</p>
        },
        h1({ children }) {
          return <h1 className="text-xl font-bold mb-3 mt-4 first:mt-0 text-stone-800">{children}</h1>
        },
        h2({ children }) {
          return <h2 className="text-lg font-bold mb-2 mt-4 first:mt-0 text-stone-800">{children}</h2>
        },
        h3({ children }) {
          return <h3 className="text-base font-bold mb-2 mt-3 first:mt-0 text-stone-800">{children}</h3>
        },
        ul({ children }) {
          return <ul className="list-disc pl-5 mb-3 space-y-1">{children}</ul>
        },
        ol({ children }) {
          return <ol className="list-decimal pl-5 mb-3 space-y-1">{children}</ol>
        },
        li({ children }) {
          return <li className="leading-relaxed">{children}</li>
        },
        blockquote({ children }) {
          return <blockquote className="border-l-[3px] border-stone-300 pl-4 my-3 text-stone-500 not-italic">{children}</blockquote>
        },
        img({ src, alt }) {
          if (!src) return null
          return (
            <figure className="my-3">
              <img
                src={src}
                alt={alt || ''}
                className="max-w-full rounded-lg border border-stone-200/60"
                loading="lazy"
              />
              {alt && (
                <figcaption className="text-[12px] text-stone-400 mt-1.5 text-center">{alt}</figcaption>
              )}
            </figure>
          )
        },
        table({ children }) {
          return (
            <div className="overflow-x-auto my-3">
              <table className="min-w-full border border-stone-200/80 rounded-lg text-sm">{children}</table>
            </div>
          )
        },
        thead({ children }) {
          return <thead className="bg-stone-50">{children}</thead>
        },
        th({ children }) {
          return <th className="px-3 py-2 text-left font-medium text-stone-600 border-b border-stone-200">{children}</th>
        },
        td({ children }) {
          return <td className="px-3 py-2 border-b border-stone-100">{children}</td>
        },
        a({ href, children }) {
          const isSafe = href && (href.startsWith('http://') || href.startsWith('https://') || href.startsWith('/'))
          return <a href={isSafe ? href : undefined} target="_blank" rel="noopener noreferrer" className="text-stone-500 hover:text-stone-700 underline">{children}</a>
        },
        hr() {
          return <hr className="my-4 border-stone-200" />
        },
      }}
    >
      {content}
    </ReactMarkdown>
  )
}

const CodeBlock = React.memo(function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }).catch(() => {
      setCopied(false)
    })
  }

  return (
    <div className="my-3 rounded-lg overflow-hidden border border-stone-200/80">
      <div className="flex items-center justify-between px-3 py-1.5 bg-stone-100 text-stone-400 text-xs">
        <span className="font-mono">{language}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 hover:text-stone-600 transition-colors"
          aria-label={copied ? '已复制' : '复制代码'}
        >
          {copied ? (
            <>
              <Check size={12} />
              <span>已复制</span>
            </>
          ) : (
            <>
              <Copy size={12} />
              <span>复制</span>
            </>
          )}
        </button>
      </div>
      <SyntaxHighlighter
        language={language}
        style={oneLight}
        customStyle={{
          margin: 0,
          padding: '12px 16px',
          fontSize: '13px',
          lineHeight: '1.5',
          background: '#fafaf9',
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  )
})

export default React.memo(MarkdownRenderer)
