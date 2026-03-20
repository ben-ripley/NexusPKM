// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act } from '@testing-library/react'
import { useChatStore } from '@/stores/chat'

type WsHandler = (event: MessageEvent | CloseEvent | Event) => void

class MockWebSocket {
  static instances: MockWebSocket[] = []

  url: string
  readyState: number = 0
  onopen: WsHandler | null = null
  onmessage: WsHandler | null = null
  onclose: WsHandler | null = null
  onerror: WsHandler | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
    // Simulate async open
    setTimeout(() => {
      this.readyState = 1
      this.onopen?.(new Event('open'))
    }, 0)
  }

  send = vi.fn()

  close(code?: number) {
    this.readyState = 3
    this.onclose?.(new CloseEvent('close', { code: code ?? 1000 }))
  }

  // Helper to simulate incoming message
  simulateMessage(data: Record<string, unknown>) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }))
  }

  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
}

describe('useChat (store-level)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    // Reset store state
    useChatStore.setState({
      sessions: [],
      currentSessionId: null,
      messagesBySession: {},
      streamingContent: '',
      isStreaming: false,
      isConnected: false,
      suggestions: [],
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('sendMessage adds user message immediately to store', () => {
    const sessionId = 'session-1'
    useChatStore.getState().setCurrentSession(sessionId)

    useChatStore.getState().addMessage(sessionId, {
      id: 'test-id',
      role: 'user',
      content: 'Hello',
      sources: [],
      timestamp: new Date().toISOString(),
    })

    const messages = useChatStore.getState().messagesBySession[sessionId]
    expect(messages).toHaveLength(1)
    expect(messages![0].role).toBe('user')
    expect(messages![0].content).toBe('Hello')
  })

  it('streaming chunks accumulate then finalize on done frame', () => {
    const sessionId = 'session-1'
    useChatStore.getState().setCurrentSession(sessionId)

    // Simulate streaming chunks
    act(() => {
      useChatStore.getState().appendStreamingChunk('Hello ')
    })
    expect(useChatStore.getState().streamingContent).toBe('Hello ')
    expect(useChatStore.getState().isStreaming).toBe(true)

    act(() => {
      useChatStore.getState().appendStreamingChunk('world')
    })
    expect(useChatStore.getState().streamingContent).toBe('Hello world')

    // Finalize
    act(() => {
      useChatStore.getState().finalizeStreamingMessage(sessionId, [])
    })
    expect(useChatStore.getState().streamingContent).toBe('')
    expect(useChatStore.getState().isStreaming).toBe(false)

    const messages = useChatStore.getState().messagesBySession[sessionId]
    expect(messages).toHaveLength(1)
    expect(messages![0].content).toBe('Hello world')
    expect(messages![0].role).toBe('assistant')
  })

  it('reconnect triggered after unexpected close', async () => {
    // Import the WebSocket service to test reconnect
    const { ChatWebSocket } = await import('@/services/websocket')

    const callbacks = {
      onChunk: vi.fn(),
      onSources: vi.fn(),
      onSuggestions: vi.fn(),
      onDone: vi.fn(),
      onError: vi.fn(),
      onStatusChange: vi.fn(),
    }

    const ws = new ChatWebSocket(callbacks)
    ws.connect('session-1', 'ws://localhost:8000')

    // Wait for connection
    await vi.waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(1)
    })

    const firstWs = MockWebSocket.instances[0]

    // Simulate open
    await vi.waitFor(() => {
      expect(callbacks.onStatusChange).toHaveBeenCalledWith('connected')
    })

    // Simulate unexpected close (code 1006)
    firstWs.readyState = 3
    firstWs.onclose?.(new CloseEvent('close', { code: 1006 }))

    // Wait for reconnect attempt (500ms delay for first retry)
    await vi.waitFor(
      () => {
        expect(MockWebSocket.instances.length).toBeGreaterThan(1)
      },
      { timeout: 2000 }
    )

    ws.disconnect()
  })
})
