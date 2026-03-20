import { useState, useRef, type KeyboardEvent, type ChangeEvent } from 'react'
import { Send } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface ChatInputProps {
  onSend: (content: string) => void
  isStreaming?: boolean
  isConnected?: boolean
  className?: string
}

function detectMode(text: string): 'search' | 'graph' | null {
  if (text.startsWith('/search ')) return 'search'
  if (text.startsWith('/graph ')) return 'graph'
  return null
}

export default function ChatInput({
  onSend,
  isStreaming = false,
  isConnected = true,
  className,
}: ChatInputProps) {
  const [content, setContent] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const mode = detectMode(content)
  const canSend = !isStreaming && isConnected && content.trim().length > 0

  const handleSend = () => {
    if (!canSend) return
    onSend(content.trim())
    setContent('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setContent(e.target.value)
    // Auto-resize
    const el = e.target
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }

  return (
    <div className={cn('relative', className)}>
      {mode && (
        <div className="mb-2">
          <Badge variant="secondary">
            {mode === 'search' ? 'Search' : 'Graph'}
          </Badge>
        </div>
      )}
      <div className="flex items-end gap-2">
        <textarea
          ref={textareaRef}
          value={content}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your knowledge base..."
          rows={1}
          className="max-h-40 min-h-[2.5rem] flex-1 resize-none rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
        />
        <Button
          size="icon"
          onClick={handleSend}
          disabled={!canSend}
          aria-label="Send"
        >
          <Send className="size-4" />
        </Button>
      </div>
    </div>
  )
}
