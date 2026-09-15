import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { renderWithProviders } from '../../test/render'
import { TypingIndicator } from './TypingIndicator'

describe('TypingIndicator', () => {
  it('is absent when nobody is typing', () => {
    renderWithProviders(<TypingIndicator names={[]} />)

    expect(screen.queryByText(/typing/)).not.toBeInTheDocument()
  })

  it.each([
    [['Ada Lovelace'], 'Ada Lovelace is typing…'],
    [['Ada Lovelace', 'Grace Hopper'], 'Ada Lovelace and Grace Hopper are typing…'],
    [['Ada Lovelace', 'Grace Hopper', 'Alan Turing'], 'Several people are typing…'],
  ])('names %j', (names, sentence) => {
    renderWithProviders(<TypingIndicator names={names} />)

    expect(screen.getByText(sentence)).toBeInTheDocument()
  })
})
