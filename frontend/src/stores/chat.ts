import { create } from 'zustand'
import type { SourceAttribution } from '@/services/websocket'

export interface SessionMeta {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources: SourceAttribution[]
  timestamp: string
}

interface ChatState {
  sessions: SessionMeta[]
  currentSessionId: string | null
  messagesBySession: Record<string, Message[]>
  streamingContent: string
  isStreaming: boolean
  isConnected: boolean
  suggestions: string[]
}

interface ChatActions {
  setSessions: (sessions: SessionMeta[]) => void
  setCurrentSession: (id: string | null) => void
  setMessages: (sessionId: string, messages: Message[]) => void
  addMessage: (sessionId: string, message: Message) => void
  appendStreamingChunk: (content: string) => void
  finalizeStreamingMessage: (sessionId: string, sources: SourceAttribution[]) => void
  setSuggestions: (suggestions: string[]) => void
  setConnected: (connected: boolean) => void
  setStreaming: (streaming: boolean) => void
}

export const useChatStore = create<ChatState & ChatActions>()((set, get) => ({
  sessions: [],
  currentSessionId: null,
  messagesBySession: {},
  streamingContent: '',
  isStreaming: false,
  isConnected: false,
  suggestions: [],

  setSessions: (sessions) => set({ sessions }),
  setCurrentSession: (id) => set({ currentSessionId: id }),
  setMessages: (sessionId, messages) =>
    set((state) => ({
      messagesBySession: { ...state.messagesBySession, [sessionId]: messages },
    })),
  addMessage: (sessionId, message) =>
    set((state) => {
      const existing = state.messagesBySession[sessionId] ?? []
      return {
        messagesBySession: {
          ...state.messagesBySession,
          [sessionId]: [...existing, message],
        },
      }
    }),
  appendStreamingChunk: (content) =>
    set((state) => ({
      streamingContent: state.streamingContent + content,
      isStreaming: true,
    })),
  finalizeStreamingMessage: (sessionId, sources) => {
    const state = get()
    if (!state.streamingContent) return
    const msg: Message = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: state.streamingContent,
      sources,
      timestamp: new Date().toISOString(),
    }
    set((prev) => ({
      messagesBySession: {
        ...prev.messagesBySession,
        [sessionId]: [...(prev.messagesBySession[sessionId] ?? []), msg],
      },
      streamingContent: '',
      isStreaming: false,
    }))
  },
  setSuggestions: (suggestions) => set({ suggestions }),
  setConnected: (connected) => set({ isConnected: connected }),
  setStreaming: (streaming) => set({ isStreaming: streaming }),
}))
