export type WsStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

export interface SourceAttribution {
  document_id: string
  title: string
  source_type: string
  source_id: string
  excerpt: string
  relevance_score: number
  created_at: string
  url?: string | null
  participants?: string[]
}

export type WsFrame =
  | { type: 'chunk'; content: string }
  | { type: 'sources'; sources: SourceAttribution[] }
  | { type: 'suggestions'; suggestions: string[] }
  | { type: 'done' }
  | { type: 'error'; message: string }

export interface ChatWebSocketCallbacks {
  onChunk: (content: string) => void
  onSources: (sources: SourceAttribution[]) => void
  onSuggestions: (suggestions: string[]) => void
  onDone: () => void
  onError: (message: string) => void
  onStatusChange: (status: WsStatus) => void
}

export class ChatWebSocket {
  private ws: WebSocket | null = null
  private retryCount = 0
  private readonly maxRetries = 3
  private callbacks: ChatWebSocketCallbacks
  private sessionId = ''
  private baseUrl = ''
  private shouldReconnect = true

  constructor(callbacks: ChatWebSocketCallbacks) {
    this.callbacks = callbacks
  }

  connect(sessionId: string, baseUrl?: string): void {
    this.sessionId = sessionId
    this.baseUrl = baseUrl ?? this.deriveBaseUrl()
    this.shouldReconnect = true
    this.retryCount = 0
    this.openConnection()
  }

  send(query: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'query', content: query }))
    }
  }

  disconnect(): void {
    this.shouldReconnect = false
    this.ws?.close(1000)
    this.ws = null
  }

  private deriveBaseUrl(): string {
    const apiUrl = import.meta.env.VITE_API_URL as string | undefined
    if (apiUrl) {
      return apiUrl.replace(/^http/, 'ws')
    }
    // In Electron the protocol is file: and host is empty — fall back to localhost
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host || 'localhost:8000'
    return `${protocol}//${host}`
  }

  private openConnection(): void {
    this.callbacks.onStatusChange('connecting')
    const url = `${this.baseUrl}/ws/chat/${this.sessionId}`
    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      this.retryCount = 0
      this.callbacks.onStatusChange('connected')
    }

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const frame = JSON.parse(event.data as string) as WsFrame
        switch (frame.type) {
          case 'chunk':
            this.callbacks.onChunk(frame.content)
            break
          case 'sources':
            this.callbacks.onSources(frame.sources)
            break
          case 'suggestions':
            this.callbacks.onSuggestions(frame.suggestions)
            break
          case 'done':
            this.callbacks.onDone()
            break
          case 'error':
            this.callbacks.onError(frame.message)
            break
        }
      } catch {
        this.callbacks.onError('Failed to parse server message')
      }
    }

    this.ws.onclose = (event: CloseEvent) => {
      if (!this.shouldReconnect) return
      if (event.code === 1000) {
        this.callbacks.onStatusChange('disconnected')
        return
      }
      if (this.retryCount < this.maxRetries) {
        const delay = Math.pow(2, this.retryCount) * 500
        this.retryCount++
        setTimeout(() => this.openConnection(), delay)
      } else {
        this.callbacks.onStatusChange('error')
        this.callbacks.onError('Connection lost after max retries')
      }
    }

    this.ws.onerror = () => {
      this.callbacks.onStatusChange('error')
    }
  }
}
