/**
 * Where you type.
 *
 * The server owns the rules and this does not restate them. **No client-side
 * length check and no `maxlength`**, deliberately: a second copy of a limit is
 * a copy that drifts from the one guarding the database, and pre-validating
 * here would mean the over-long send never leaves the browser — so there would
 * be nothing to roll back and no error to render, which is exactly the
 * behaviour the slice exists to build. `CreateChannelDialog` made the same call
 * for channel names.
 *
 * **Sending goes over the socket, and renders before the server confirms.** The
 * message appears greyed the instant enter is pressed and settles when the ack
 * lands; a refusal takes it back out and puts the words back in this box.
 * `POST /channels/{id}/messages` stays alive as the documented REST fallback —
 * moving the composer off it does not delete the route.
 *
 * **The composer is disabled while the socket is down**, with the reason
 * visible. `emit` on a closed socket does not fail, it buffers, and the callback
 * never fires — so a dead input that says why beats a live one that silently
 * swallows what you type. There is no offline queue: it would need ordering,
 * durable storage and dedupe against a write with no idempotency key.
 *
 * Half-typed text is client state by definition, so it lives in Zustand and
 * survives switching channels and coming back.
 *
 * Enter sends and Shift+Enter breaks a line, which is what people expect from a
 * chat box and is why this is a `textarea`.
 */

import { type FormEvent, type KeyboardEvent } from 'react'

import { describeError, ProblemError } from '../../lib/api/client'
import { useSocket } from '../../lib/realtime/SocketProvider'
import { useChatStore } from '../../stores/chat'
import { TypingIndicator } from './TypingIndicator'
import { useSendMessage } from './useMessages'
import { useTyping } from './useTyping'
import { useWorkspaceMembers } from './useWorkspaceMembers'

interface Props {
  accessToken: string
  workspaceId: string | null
  channelId: string
  channelName: string
  userId: string
}

export function MessageComposer({
  accessToken,
  workspaceId,
  channelId,
  channelName,
  userId,
}: Props) {
  const draft = useChatStore((state) => state.drafts[channelId] ?? '')
  const setDraft = useChatStore((state) => state.setDraft)
  const clearDraft = useChatStore((state) => state.clearDraft)
  const connectionStatus = useChatStore((state) => state.connectionStatus)

  const socket = useSocket()
  const directory = useWorkspaceMembers(accessToken, workspaceId)
  const { typingUserIds, onKeystroke } = useTyping(socket, channelId, userId)
  const send = useSendMessage(socket, workspaceId, channelId, userId)

  const offline = connectionStatus !== 'connected'
  const problem = send.error instanceof ProblemError ? send.error : undefined
  const bodyError = problem?.fieldError('body')
  const otherError = send.error && !bodyError ? describeError(send.error) : undefined

  function submit(event?: FormEvent) {
    event?.preventDefault()
    if (!draft) return

    // The draft is cleared straight away, because the message is already on
    // screen — and restored if the send is refused, so nothing typed is lost.
    const text = draft
    clearDraft(channelId)
    send.mutate(text, { onError: () => setDraft(channelId, text) })
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <div className="border-t border-border">
      <TypingIndicator names={typingUserIds.map((id) => directory.nameFor(id))} />

      <form onSubmit={submit} data-testid="message-composer" className="flex flex-col gap-2 p-4">
        <div className="flex items-end gap-2">
          <textarea
            data-testid="message-composer-input"
            value={draft}
            onChange={(event) => {
              setDraft(channelId, event.target.value)
              onKeystroke()
            }}
            onKeyDown={onKeyDown}
            rows={2}
            disabled={offline}
            aria-label={`Message #${channelName}`}
            placeholder={offline ? 'Reconnecting…' : `Message #${channelName}`}
            className="min-w-0 flex-1 resize-none rounded border border-border bg-surface px-3 py-2 text-sm text-ink disabled:opacity-60"
          />
          <button
            type="submit"
            data-testid="message-composer-send"
            disabled={offline}
            className="rounded bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-60"
          >
            Send
          </button>
        </div>

        {offline && (
          <p data-testid="composer-offline" className="text-xs text-ink-muted">
            Not connected — messages cannot be sent until the connection is back.
          </p>
        )}

        {(bodyError || otherError) && (
          <p data-testid="message-composer-error" role="alert" className="text-sm text-danger">
            {bodyError ?? otherError}
          </p>
        )}
      </form>
    </div>
  )
}
