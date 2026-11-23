/**
 * The sidebar's search box. Enter submits the trimmed text to `/search?q=…`, from
 * any route; a blank box submits nothing.
 *
 * The box remounts when the route's query changes (`key`), with `defaultValue`,
 * so its text follows the route — the query on `/search`, empty elsewhere —
 * without an effect copying the URL into state. Submitting the query already on
 * screen invalidates it, so it refetches, and navigates nowhere: a duplicate
 * history entry would make Back a no-op once.
 */

import { useQueryClient } from '@tanstack/react-query'
import type { FormEvent } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'

import { searchKeys } from './useSearch'

/** The longest query Messaging accepts. */
const MAX_QUERY_LENGTH = 200

interface Props {
  workspaceId: string | null
  /**
   * Called on every non-blank submit, whether it navigates or only refetches: the
   * narrow shell closes its drawer either way, and a location listener would miss
   * the second.
   */
  onNavigate?: () => void
}

export function SearchBox({ workspaceId, onNavigate }: Props) {
  const { pathname } = useLocation()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const onSearchPage = pathname === '/search'
  const current = onSearchPage ? (params.get('q') ?? '') : ''

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const typed = new FormData(event.currentTarget).get('q')
    const q = typeof typed === 'string' ? typed.trim() : ''
    if (q === '') return

    void queryClient.invalidateQueries({ queryKey: searchKeys.results(workspaceId, q) })
    if (!onSearchPage || current.trim() !== q) navigate(`/search?q=${encodeURIComponent(q)}`)
    onNavigate?.()
  }

  return (
    <form role="search" aria-label="Search messages" onSubmit={submit} className="p-3">
      <input
        key={onSearchPage ? `search:${current}` : 'other'}
        type="search"
        name="q"
        aria-label="Search messages"
        placeholder="Search messages"
        maxLength={MAX_QUERY_LENGTH}
        defaultValue={current}
        data-testid="search-box"
        className="w-full rounded border border-border bg-surface px-2 py-1 text-sm text-ink"
      />
    </form>
  )
}
