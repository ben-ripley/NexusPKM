import { MessageSquare } from 'lucide-react'

export default function ChatPage() {
  return (
    <div className="flex flex-1 items-center justify-center gap-3 text-muted-foreground">
      <MessageSquare className="size-8" />
      <h1 className="text-2xl font-semibold">Chat</h1>
    </div>
  )
}
