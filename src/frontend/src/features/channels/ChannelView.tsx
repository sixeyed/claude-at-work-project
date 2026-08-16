/**
 * The open channel: its header, its history, its composer and its members.
 *
 * The composition is the point of this file; everything it renders belongs to a
 * component of its own. What it owns is the one query the others hang off —
 * the channel itself — and the three states that query can be in, including the
 * clean "not found" that a channel id nobody may see has to produce.
 */

import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { useEffect } from 'react'

import { getChannel } from '../../lib/api/messaging'
import { ChannelHeader } from './ChannelHeader'
import { MemberPanel } from './MemberPanel'
import { MessageComposer } from './MessageComposer'
import { MessageList } from './MessageList'
import { channelKeys } from './useChannels'
import { useChatStore } from '../../stores/chat'

interface Props {
  accessToken: string
  workspaceId: string | null
  userId: string
}

export function ChannelView({ accessToken, workspaceId, userId }: Props) {
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
    <section
      data-testid="channel-view"
      data-channel-name={channel.name}
      className="flex h-full flex-col"
    >
      <ChannelHeader accessToken={accessToken} workspaceId={workspaceId} channel={channel} />

      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <MessageList
            accessToken={accessToken}
            workspaceId={workspaceId}
            channelId={channel.id}
            userId={userId}
            myRole={channel.myRole ?? null}
          />
          {/* Enabled for any channel this view can render: visibility is the
              write test as well as the read one, so someone who can see a
              public channel can talk in it without joining. */}
          <MessageComposer
            accessToken={accessToken}
            workspaceId={workspaceId}
            channelId={channel.id}
            channelName={channel.name}
            userId={userId}
          />
        </div>

        <MemberPanel accessToken={accessToken} workspaceId={workspaceId} channel={channel} />
      </div>
    </section>
  )
}
