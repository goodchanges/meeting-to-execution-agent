import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { Evidence, ModeLabel } from './ui'

it('renders injected markup as visible text and flags unverified evidence', () => {
  const payload = '<script>alert("sample")</script><img src=x>'
  const { container } = render(<Evidence text={payload} verified={false} />)
  expect(screen.getByText(payload)).toBeVisible()
  expect(screen.getByText(/evidence could not be verified/i)).toBeVisible()
  expect(container.querySelector('script, img')).toBeNull()
})
it('shows the exact demo label only for fixture-backed output', () => {
  const { rerender } = render(<ModeLabel mode="demo" />)
  expect(screen.getByText('DEMO MODE — not live AI')).toBeVisible()
  rerender(<ModeLabel mode="live" />)
  expect(screen.queryByText(/demo mode/i)).toBeNull()
})

