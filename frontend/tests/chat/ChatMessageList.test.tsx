// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ChatMessageList from '@/components/chat/ChatMessageList'
import { useChatStore } from '@/stores/chat'

const defaultState = {
  sessions: [],
  currentSessionId: null,
  messagesBySession: {},
  streamingContent: '',
  isStreaming: false,
  isConnected: false,
  suggestions: [],
}

describe('ChatMessageList', () => {
  beforeEach(() => {
    useChatStore.setState(defaultState)
  })

  it('renders typing indicator (3 dots) when streaming with no content', () => {
    useChatStore.setState({ ...defaultState, isStreaming: true, streamingContent: '' })
    render(<ChatMessageList />)
    const dots = document.querySelectorAll('.animate-bounce')
    expect(dots).toHaveLength(3)
  })

  it('renders streaming content as it arrives', () => {
    useChatStore.setState({
      ...defaultState,
      isStreaming: true,
      streamingContent: 'Streaming answer here',
    })
    render(<ChatMessageList />)
    expect(screen.getByText('Streaming answer here')).toBeInTheDocument()
  })

  it('does not render typing indicator when streaming content is present', () => {
    useChatStore.setState({
      ...defaultState,
      isStreaming: true,
      streamingContent: 'Some content',
    })
    render(<ChatMessageList />)
    expect(document.querySelectorAll('.animate-bounce')).toHaveLength(0)
  })

  it('renders suggestion chips when not streaming', () => {
    useChatStore.setState({
      ...defaultState,
      isStreaming: false,
      suggestions: ['Tell me more', 'What else happened?'],
    })
    render(<ChatMessageList />)
    expect(screen.getByText('Tell me more')).toBeInTheDocument()
    expect(screen.getByText('What else happened?')).toBeInTheDocument()
  })

  it('calls onSuggestionClick with the suggestion text when a chip is clicked', async () => {
    const user = userEvent.setup()
    const onSuggestionClick = vi.fn()
    useChatStore.setState({
      ...defaultState,
      isStreaming: false,
      suggestions: ['Tell me more'],
    })
    render(<ChatMessageList onSuggestionClick={onSuggestionClick} />)
    await user.click(screen.getByText('Tell me more'))
    expect(onSuggestionClick).toHaveBeenCalledWith('Tell me more')
  })

  it('does not render suggestion chips while streaming', () => {
    useChatStore.setState({
      ...defaultState,
      isStreaming: true,
      suggestions: ['Tell me more'],
    })
    render(<ChatMessageList onSuggestionClick={vi.fn()} />)
    expect(screen.queryByText('Tell me more')).not.toBeInTheDocument()
  })
})
