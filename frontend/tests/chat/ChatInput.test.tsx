// @vitest-environment jsdom
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import ChatInput from '@/components/chat/ChatInput'

describe('ChatInput', () => {
  it('renders with placeholder text', () => {
    render(<ChatInput onSend={vi.fn()} />)
    expect(
      screen.getByPlaceholderText('Ask about your knowledge base...')
    ).toBeInTheDocument()
  })

  it('Enter key calls onSend with content', async () => {
    const onSend = vi.fn()
    const user = userEvent.setup()
    render(<ChatInput onSend={onSend} />)
    const textarea = screen.getByPlaceholderText(
      'Ask about your knowledge base...'
    )
    await user.type(textarea, 'hello')
    await user.keyboard('{Enter}')
    expect(onSend).toHaveBeenCalledWith('hello')
  })

  it('Shift+Enter inserts newline instead of sending', async () => {
    const onSend = vi.fn()
    const user = userEvent.setup()
    render(<ChatInput onSend={onSend} />)
    const textarea = screen.getByPlaceholderText(
      'Ask about your knowledge base...'
    )
    await user.type(textarea, 'hello')
    await user.keyboard('{Shift>}{Enter}{/Shift}')
    expect(onSend).not.toHaveBeenCalled()
  })

  it('is disabled while streaming', () => {
    render(<ChatInput onSend={vi.fn()} isStreaming={true} />)
    const sendButton = screen.getByRole('button', { name: /send/i })
    expect(sendButton).toBeDisabled()
  })

  it('clears after send', async () => {
    const onSend = vi.fn()
    const user = userEvent.setup()
    render(<ChatInput onSend={onSend} />)
    const textarea = screen.getByPlaceholderText(
      'Ask about your knowledge base...'
    ) as HTMLTextAreaElement
    await user.type(textarea, 'hello')
    await user.keyboard('{Enter}')
    expect(textarea.value).toBe('')
  })

  it('shows Search badge for /search prefix', async () => {
    const user = userEvent.setup()
    render(<ChatInput onSend={vi.fn()} />)
    const textarea = screen.getByPlaceholderText(
      'Ask about your knowledge base...'
    )
    await user.type(textarea, '/search foo')
    expect(screen.getByText('Search')).toBeInTheDocument()
  })

  it('shows Graph badge for /graph prefix', async () => {
    const user = userEvent.setup()
    render(<ChatInput onSend={vi.fn()} />)
    const textarea = screen.getByPlaceholderText(
      'Ask about your knowledge base...'
    )
    await user.type(textarea, '/graph foo')
    expect(screen.getByText('Graph')).toBeInTheDocument()
  })
})
