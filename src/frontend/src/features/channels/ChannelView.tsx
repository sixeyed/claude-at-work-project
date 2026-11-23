/**
 * The open channel: its header, its history, its composer and its members.
 *
 * The composition is the point of this file; everything it renders belongs to a
 * component of its own. What it owns is the one query the others hang off —
 * the channel itself — and the three states that query can be in, including the
 * clean "not found" that a channel id nobody may see has to produce.
 */

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'

import { getChannel } from '../../lib/api/messaging'
import { useNarrow } from '../../lib/layout/useNarrow'
import { ThreadPanel } from '../threads/ThreadPanel'
import { useThreadParam } from '../threads/useThreadParam'
import { ChannelHeader } from './ChannelHeader'
import { MemberPanel } from './MemberPanel'
import { MessageComposer } from './MessageComposer'
import { MessageList } from './MessageList'
import { channelLabel, channelTitle, isDm } from './directMessages'
import { channelKeys } from './useChannels'
import { useWorkspaceMembers } from './useWorkspaceMembers'
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

  const queryClient = useQueryClient()
  // Which thread is open lives in the URL. Switching channel drops it, since
  // the new channel's address carries no `?thread=`.
  const { threadId, openThread, closeThread } = useThreadParam()

  // Below 768px a panel covers the message column instead of sitting beside it
  // (register D48). The element tree is the same at every width: the column stays
  // mounted and laid out under the panel, so its scroll position survives, and a
  // rotation changes classes and attributes only.
  const narrow = useNarrow()
  // The member panel is open for one (channel, thread, width) and no other: changing
  // any of them closes it with no effect to reset it. Crossing to wide forgets it
  // outright — the key alone would reopen it on the way back to narrow.
  const [membersOpenFor, setMembersOpenFor] = useState<string | null>(null)
  const membersKey = `${channelId ?? ''}|${threadId ?? ''}|${narrow}`
  if (!narrow && membersOpenFor !== null) setMembersOpenFor(null)
  const membersOpen = membersOpenFor === membersKey

  // **Back to channel** returns the reader to the channel's composer. The panel is
  // still on screen when the press happens, so the focus waits for the render that
  // removes it (and the `inert` on the column with it).
  const column = useRef<HTMLDivElement>(null)
  const focusComposerOnReturn = useRef(false)
  useEffect(() => {
    if (focusComposerOnReturn.current && !threadId && !membersOpen) {
      focusComposerOnReturn.current = false
      column.current?.querySelector('textarea')?.focus()
    }
  })

  // Opening a channel refetches the list: the sidebar's counts are the
  // server's, and the user has just changed what they are looking at.
  useEffect(() => {
    void queryClient.invalidateQueries({ queryKey: channelKeys.list(workspaceId) })
  }, [queryClient, workspaceId, channelId])

  // A DM is named after the other person, which only the directory knows.
  const directory = useWorkspaceMembers(accessToken, workspaceId)

  const {
    data: channel,
    isPending,
    isFetching,
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

  const label = channelLabel(channel, directory.nameFor)
  const dm = isDm(channel)
  // A DM's two members are fixed and are its name; there is nothing to list.
  const canListMembers = !dm && !threadId
  const covered = narrow && (threadId !== null || membersOpen)

  function backToChannel() {
    focusComposerOnReturn.current = true
    if (threadId) closeThread()
    else setMembersOpenFor(null)
  }

  return (
    <section data-testid="channel-view" data-channel-name={label} className="flex h-full flex-col">
      <ChannelHeader
        accessToken={accessToken}
        workspaceId={workspaceId}
        channel={channel}
        label={label}
        onToggleMembers={
          narrow && canListMembers
            ? () => setMembersOpenFor(membersOpen ? null : membersKey)
            : undefined
        }
        membersOpen={membersOpen}
      />

      <div className="relative flex min-h-0 flex-1">
        <div ref={column} inert={covered} className="flex min-w-0 flex-1 flex-col">
          {/* Keyed by channel: every channel is a fresh mount, which starts at
              its newest message, measures the bottom, takes its divider once
              and flushes its pending read as it unmounts. */}
          <MessageList
            key={channel.id}
            accessToken={accessToken}
            workspaceId={workspaceId}
            channelId={channel.id}
            userId={userId}
            myRole={channel.myRole ?? null}
            lastReadId={channel.lastReadId ?? null}
            channelFetching={isFetching}
            onOpenThread={openThread}
          />
          {/* Enabled for any channel this view can render: visibility is the
              write test as well as the read one, so someone who can see a
              public channel can talk in it without joining. */}
          {/* Keyed by channel, so a half-finished batch error from one channel
              is not carried into the next. Text, chips and send errors are per
              channel in their stores. A key of its own: the list above is
              keyed by the same id, and siblings must not share one. */}
          <MessageComposer
            key={`composer-${channel.id}`}
            accessToken={accessToken}
            workspaceId={workspaceId}
            channelId={channel.id}
            channelTitle={channelTitle(channel, directory.nameFor)}
            userId={userId}
          />
        </div>

        {/* A thread takes the members' place: one right-hand column, so the
            channel list never loses width to a third pane. Keyed by the root so
            each thread is a fresh mount with its own scroll position. */}
        {threadId ? (
          <ThreadPanel
            key={threadId}
            accessToken={accessToken}
            workspaceId={workspaceId}
            channelId={channel.id}
            rootId={threadId}
            userId={userId}
            myRole={channel.myRole ?? null}
            // Narrow, the press is **Back to channel**; the browser's Back and the wide
            // **Close thread** go through `closeThread` untouched.
            onClose={narrow ? backToChannel : closeThread}
            fullScreen={narrow}
          />
        ) : (
          canListMembers &&
          (!narrow || membersOpen) && (
            <MemberPanel
              accessToken={accessToken}
              workspaceId={workspaceId}
              channel={channel}
              onBack={narrow ? backToChannel : undefined}
            />
          )
        )}
      </div>
    </section>
  )
}
