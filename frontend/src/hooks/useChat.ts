import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useCallback } from 'react'
import { z } from 'zod'
import { ChatWebSocket } from '@/services/websocket'
import { useChatStore } from '@/stores/chat'
import type { SourceAttribution } from '@/services/websocket'
import type { SessionMeta, Message } from '@/stores/chat'

const API = import.meta.env.VITE_API_URL ?? ''

// Runtime validation schemas
const SourceAttributionSchema = z.object({
  document_id: z.string(),
  title: z.string(),
  source_type: z.string(),
  source_id: z.string(),
  excerpt: z.string(),
  relevance_score: z.number(),
  created_at: z.string(),
  url: z.string().nullable().optional(),
  participants: z.array(z.string()).optional(),
})

const MessageSchema = z.object({
  id: z.string(),
  role: z.enum(['user', 'assistant']),
  content: z.string(),
  sources: z.array(SourceAttributionSchema),
  timestamp: z.string(),
})

const SessionMetaSchema = z.object({
  id: z.string(),
  title: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
})

const SessionDetailSchema = SessionMetaSchema.extend({
  messages: z.array(MessageSchema),
})

async function fetchSessions(): Promise<SessionMeta[]> {
  const res = await fetch(`${API}/api/chat/sessions`)
  if (!res.ok) throw new Error('Failed to fetch sessions')
  return z.array(SessionMetaSchema).parse(await res.json())
}

async function createSession(firstMessage: string): Promise<z.infer<typeof SessionDetailSchema>> {
  const res = await fetch(`${API}/api/chat/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ first_message: firstMessage }),
  })
  if (!res.ok) throw new Error('Failed to create session')
  return SessionDetailSchema.parse(await res.json())
}

async function deleteSessionApi(id: string): Promise<void> {
  const res = await fetch(`${API}/api/chat/sessions/${id}`, {
    method: 'DELETE',
  })
  if (!res.ok && res.status !== 204) throw new Error('Failed to delete session')
}

async function fetchSessionDetail(id: string): Promise<z.infer<typeof SessionDetailSchema>> {
  const res = await fetch(`${API}/api/chat/sessions/${id}`)
  if (!res.ok) throw new Error('Failed to fetch session')
  return SessionDetailSchema.parse(await res.json())
}

export function useChat() {
  const queryClient = useQueryClient()
  const wsRef = useRef<ChatWebSocket | null>(null)
  const sourcesRef = useRef<SourceAttribution[]>([])

  const {
    sessions,
    currentSessionId,
    messagesBySession,
    streamingContent,
    isStreaming,
    isConnected,
    suggestions,
    setSessions,
    setCurrentSession,
    setMessages,
    addMessage,
    appendStreamingChunk,
    finalizeStreamingMessage,
    setSuggestions,
    setConnected,
    setStreaming,
  } = useChatStore()

  const sessionsQuery = useQuery({
    queryKey: ['chat-sessions'],
    queryFn: fetchSessions,
    staleTime: 30000,
  })

  useEffect(() => {
    if (sessionsQuery.data) {
      setSessions(sessionsQuery.data)
    }
  }, [sessionsQuery.data, setSessions])

  const connectWebSocket = useCallback(
    (sessionId: string) => {
      wsRef.current?.disconnect()
      sourcesRef.current = []

      const ws = new ChatWebSocket({
        onChunk: (content) => appendStreamingChunk(content),
        onSources: (sources) => {
          sourcesRef.current = sources
        },
        onSuggestions: (s) => setSuggestions(s),
        onDone: () => {
          finalizeStreamingMessage(sessionId, sourcesRef.current)
          sourcesRef.current = []
        },
        onError: (msg) => {
          setStreaming(false)
          console.error('WebSocket error:', msg)
        },
        onStatusChange: (status) => {
          setConnected(status === 'connected')
        },
      })

      ws.connect(sessionId)
      wsRef.current = ws
    },
    [
      appendStreamingChunk,
      finalizeStreamingMessage,
      setConnected,
      setStreaming,
      setSuggestions,
    ]
  )

  useEffect(() => {
    if (currentSessionId) {
      connectWebSocket(currentSessionId)
    }
    return () => {
      wsRef.current?.disconnect()
    }
  }, [currentSessionId, connectWebSocket])

  const createMutation = useMutation({
    mutationFn: createSession,
    onSuccess: (session) => {
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
      setMessages(session.id, session.messages ?? [])
      setCurrentSession(session.id)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteSessionApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
    },
  })

  const sendMessage = useCallback(
    (content: string) => {
      if (!currentSessionId || !content.trim()) return
      const msg: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content,
        sources: [],
        timestamp: new Date().toISOString(),
      }
      addMessage(currentSessionId, msg)
      setStreaming(true)
      setSuggestions([])
      wsRef.current?.send(content)
    },
    [currentSessionId, addMessage, setStreaming, setSuggestions]
  )

  const newSession = useCallback(
    (firstMessage: string) => {
      createMutation.mutate(firstMessage || 'New conversation')
    },
    [createMutation]
  )

  const loadSession = useCallback(
    async (id: string) => {
      const session = await fetchSessionDetail(id)
      setMessages(id, session.messages)
      setCurrentSession(id)
    },
    [setMessages, setCurrentSession]
  )

  const deleteSession = useCallback(
    (id: string) => {
      deleteMutation.mutate(id)
      if (currentSessionId === id) {
        setCurrentSession(null)
      }
    },
    [deleteMutation, currentSessionId, setCurrentSession]
  )

  const messages = currentSessionId
    ? (messagesBySession[currentSessionId] ?? [])
    : []

  return {
    sessions,
    currentSessionId,
    messages,
    isStreaming,
    isConnected,
    streamingContent,
    suggestions,
    isLoadingSessions: sessionsQuery.isLoading,
    sessionsError: sessionsQuery.error,
    sendMessage,
    newSession,
    loadSession,
    deleteSession,
  }
}
