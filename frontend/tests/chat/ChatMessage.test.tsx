// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import ChatMessage from '@/components/chat/ChatMessage'
import type { Message } from '@/stores/chat'

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: 'msg-1',
    role: 'assistant',
    content: 'Hello world',
    sources: [],
    timestamp: new Date().toISOString(),
    ...overrides,
  }
}

describe('ChatMessage', () => {
  it('user message is right-aligned', () => {
    const msg = makeMessage({ role: 'user', content: 'Hi there' })
    const { container } = render(<ChatMessage message={msg} />)
    const wrapper = container.firstElementChild as HTMLElement
    expect(wrapper.className).toMatch(/justify-end/)
  })

  it('assistant message renders markdown bold', () => {
    const msg = makeMessage({ content: '**bold text**' })
    render(<ChatMessage message={msg} />)
    const strong = screen.getByText('bold text')
    expect(strong.tagName).toBe('STRONG')
  })

  it('assistant message renders inline code', () => {
    const msg = makeMessage({ content: 'Use `code` here' })
    render(<ChatMessage message={msg} />)
    const codeEl = screen.getByText('code')
    expect(codeEl.tagName).toBe('CODE')
  })

  it('source cards render when sources provided', () => {
    const msg = makeMessage({
      sources: [
        {
          document_id: 'd1',
          title: 'Source One',
          source_type: 'teams',
          source_id: 's1',
          excerpt: 'excerpt one',
          relevance_score: 0.95,
          created_at: new Date().toISOString(),
        },
        {
          document_id: 'd2',
          title: 'Source Two',
          source_type: 'obsidian',
          source_id: 's2',
          excerpt: 'excerpt two',
          relevance_score: 0.88,
          created_at: new Date().toISOString(),
        },
      ],
    })
    render(<ChatMessage message={msg} />)
    expect(screen.getByText('Source One')).toBeInTheDocument()
    expect(screen.getByText('Source Two')).toBeInTheDocument()
  })

  it('copy button present on assistant messages', () => {
    const msg = makeMessage({ content: 'Some content to copy' })
    render(<ChatMessage message={msg} />)
    expect(screen.getByRole('button', { name: /copy/i })).toBeInTheDocument()
  })
})
