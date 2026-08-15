/**
 * The open channel.
 *
 * Empty of messages on purpose — sending and reading arrive in the next slice.
 * What it proves now is that a channel opens by id, including a public one the
 * viewer has not joined, and that an id nobody may see is a clean "not found"
 * rather than a crash.
 */

import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { useEffect } from 'react'

import { getChannel } from '../../lib/api/messaging'
import { channelKeys } from './useChannels'
import { useChatStore } from '../../stores/chat'

interface Props {
  accessToken: string
  workspaceId: string | null
}

export function ChannelView({ accessToken, workspaceId }: Props) {
  const { channelId } = useParams<{ channelId: string }>()
  const setActiveChannel = useChatStore((state) => state.setActiveChannel)

  useEffect(() => {
    setActiveChannel(channelId ?? null)
    return () => setActiveChannel(null)
  }, [channelId, setActiveChannel])

  const {
    data: channel,
    isPending,
    error,
  } = useQuery({
    queryKey: channelKeys.detail(workspaceId, channelId),
    queryFn: () => getChannel(accessToken, channelId as string),
    enabled: Boolean(channelId),
  })

  if (isPending) {
    return (
      <p data-testid="channel-loading" className="p-6 text-sm text-ink-muted">
        Loading…
      </p>
    )
  }

  if (error) {
    return (
      <p data-testid="channel-error" role="alert" className="p-6 text-sm text-danger">
        {error.message}
      </p>
    )
  }

  return (
    <section data-testid="channel-view" data-channel-name={channel.name} className="flex h-full flex-col">
      <header className="border-b border-border px-6 py-4">
        <h2 data-testid="channel-header-name" className="text-lg font-semibold text-ink">
          <span aria-hidden="true" className="opacity-50">
            #
          </span>{' '}
          {channel.name}
        </h2>
        {channel.topic && <p className="text-sm text-ink-muted">{channel.topic}</p>}
      </header>

      <div className="flex flex-1 items-center justify-center p-6">
        <p data-testid="channel-empty" className="text-sm text-ink-muted">
          Nothing here yet.
        </p>
      </div>
    </section>
  )
}
