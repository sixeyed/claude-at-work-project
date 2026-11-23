/**
 * What a message shows for its files (issue 4 R9, R11, decisions 29–31): images
 * inline, PDFs as a chip, and a fresh URL at the moment of every click.
 *
 * **Metadata comes with the message; URLs are fetched.** A file's name, type and
 * size are stored on the message, so a chip renders with no request, and still
 * does when Asset is down. Only the bytes need a URL, and a URL is short-lived and
 * per-viewer, so each image asks Messaging for its own (`useAttachmentUrl`).
 *
 * * An image that will not load refetches its URL **once** — most often it has
 *   expired — then offers "Couldn't load — retry".
 * * A **pending** message (a `temp:` id, not yet confirmed) asks for nothing: the
 *   id would 404. It shows the chips' metadata and fetches once it is real.
 * * A **tombstone** shows no attachments at all.
 * * A click opens the window **synchronously** and sends it to the URL once a
 *   fresh one has arrived (`window.open` after an `await` loses its user
 *   activation in Safari and is blocked). A PDF navigates the page to a URL signed
 *   `Content-Disposition: attachment`, which downloads and leaves the page where it is.
 *
 * Images are capped at `max-h-60 max-w-80` (240 × 320 px), `object-contain`.
 */

import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import type { Attachment, Message } from '../../lib/api/messaging'
import { isPending } from '../channels/useMessages'
import { formatBytes } from './format'
import { freshAttachmentUrl, useAttachmentUrl } from './useAttachmentUrl'

interface Props {
  message: Message
  accessToken: string
  workspaceId: string | null
}

export function AttachmentList({ message, accessToken, workspaceId }: Props) {
  if (message.deletedAt !== null || message.attachments.length === 0) return null

  return (
    <div className="mt-1 flex flex-col items-start gap-2">
      {message.attachments.map((attachment) =>
        attachment.contentType.startsWith('image/') ? (
          <AttachmentImage
            key={attachment.assetId}
            message={message}
            attachment={attachment}
            accessToken={accessToken}
            workspaceId={workspaceId}
          />
        ) : (
          <AttachmentFile
            key={attachment.assetId}
            message={message}
            attachment={attachment}
            accessToken={accessToken}
            workspaceId={workspaceId}
          />
        ),
      )}
    </div>
  )
}

interface ItemProps extends Props {
  attachment: Attachment
}

/** Open a window now, and send it to a URL that is fresh when it arrives. */
function openFresh(
  queryClient: QueryClient,
  { message, attachment, accessToken, workspaceId }: ItemProps,
): void {
  // Synchronously, inside the click: see the module comment.
  const opened = window.open('', '_blank')
  // The page it opens is object storage's, not ours: it must not reach back.
  if (opened) opened.opener = null
  freshAttachmentUrl(queryClient, accessToken, workspaceId, message.id, attachment.assetId).then(
    (url) => {
      if (opened) opened.location.href = url
    },
    () => opened?.close(),
  )
}

function AttachmentImage(props: ItemProps) {
  const { message, attachment, accessToken, workspaceId } = props
  const queryClient = useQueryClient()
  const pending = isPending(message)
  const { url, isError, refetch } = useAttachmentUrl(
    accessToken,
    workspaceId,
    message.id,
    attachment.assetId,
    !pending,
  )
  // How many times the browser failed to load this image since the last retry.
  const [failures, setFailures] = useState(0)
  // While a fresh URL is on its way the old one is not shown: it just failed.
  const [refreshing, setRefreshing] = useState(false)

  function refresh(nextFailures: number) {
    setFailures(nextFailures)
    setRefreshing(true)
    void refetch().finally(() => setRefreshing(false))
  }

  if (pending) {
    return <Placeholder name={attachment.fileName} note="Sending…" />
  }
  if (isError || failures >= 2) {
    return (
      <button
        type="button"
        onClick={() => refresh(0)}
        className="rounded border border-border px-3 py-2 text-xs text-ink-muted underline"
      >
        Couldn’t load — retry
      </button>
    )
  }
  if (url === null || refreshing) {
    return <Placeholder name={attachment.fileName} note="Loading…" />
  }

  return (
    <button
      type="button"
      onClick={() => openFresh(queryClient, props)}
      // `max-w-80` on the image is a flat 320px, which a 360px screen's padded row
      // cannot hold; this wider-specificity rule caps it at the row when that is less.
      className="max-w-full rounded [&>img]:max-w-[min(20rem,100%)]"
      aria-label={`Open ${attachment.fileName}`}
    >
      <img
        data-testid="message-attachment-image"
        data-file-name={attachment.fileName}
        src={url}
        alt={attachment.fileName}
        // Once: the URL has most likely expired, so ask for another. A second
        // failure is the file, not the URL, and the retry placeholder takes over.
        onError={() => (failures === 0 ? refresh(1) : setFailures(2))}
        className="max-h-60 max-w-80 rounded object-contain"
      />
    </button>
  )
}

function AttachmentFile(props: ItemProps) {
  const { message, attachment, accessToken, workspaceId } = props
  const queryClient = useQueryClient()
  const [failed, setFailed] = useState(false)

  function download() {
    setFailed(false)
    freshAttachmentUrl(queryClient, accessToken, workspaceId, message.id, attachment.assetId).then(
      (url) => window.location.assign(url),
      () => setFailed(true),
    )
  }

  return (
    <div
      data-testid="message-attachment-file"
      data-file-name={attachment.fileName}
      className="flex max-w-full items-center gap-3 rounded border border-border px-3 py-2 text-sm"
    >
      <span className="min-w-0 truncate text-ink">{attachment.fileName}</span>
      <span className="text-xs text-ink-muted">{formatBytes(attachment.sizeBytes)}</span>
      <button
        type="button"
        data-testid="message-attachment-download"
        disabled={isPending(message)}
        onClick={download}
        className="text-xs text-accent underline disabled:opacity-60"
      >
        Download
      </button>
      {failed && (
        <span role="alert" className="text-xs text-danger">
          Couldn’t download — try again.
        </span>
      )}
    </div>
  )
}

function Placeholder({ name, note }: { name: string; note: string }) {
  return (
    <div className="flex h-16 w-40 items-center justify-center rounded border border-border bg-surface-sunken text-xs text-ink-muted">
      <span className="truncate" title={name}>
        {note}
      </span>
    </div>
  )
}
