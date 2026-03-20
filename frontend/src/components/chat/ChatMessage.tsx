import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Copy, Check } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import SourceCard from './SourceCard'
import type { Message } from '@/stores/chat'
import type { Components } from 'react-markdown'

interface ChatMessageProps {
  message: Message
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const [copied, setCopied] = useState(false)
  const isUser = message.role === 'user'

  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const markdownComponents: Components = {
    code: ({ className, children, ...rest }) => {
      const match = /language-(\w+)/.exec(className ?? '')
      const codeString = String(children).replace(/\n$/, '')

      if (match) {
        return (
          <SyntaxHighlighter
            style={oneDark}
            language={match[1]}
            PreTag="div"
          >
            {codeString}
          </SyntaxHighlighter>
        )
      }
      return (
        <code
          className="rounded bg-muted px-1 text-sm font-mono"
          {...rest}
        >
          {children}
        </code>
      )
    },
    p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  }

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-primary px-4 py-2 text-primary-foreground">
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] space-y-2">
        <div className="relative rounded-2xl rounded-tl-sm bg-muted px-4 py-2">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={markdownComponents}
          >
            {message.content}
          </ReactMarkdown>
          <Button
            variant="ghost"
            size="icon"
            className="absolute top-1 right-1 size-7"
            onClick={handleCopy}
            aria-label="Copy"
          >
            {copied ? (
              <Check className="size-3.5" />
            ) : (
              <Copy className="size-3.5" />
            )}
          </Button>
        </div>

        {message.sources.length > 0 && (
          <div className="space-y-1">
            {message.sources.map((source, i) => (
              <SourceCard key={source.source_id} source={source} index={i} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
