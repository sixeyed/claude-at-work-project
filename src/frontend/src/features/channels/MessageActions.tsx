/**
 * A message's "⋯" button and the one menu behind it: react, reply in thread,
 * edit, delete — exactly what `offeredActions` says the message allows.
 *
 * It is a WAI-ARIA menu button: `aria-haspopup="menu"`, a `role="menu"` of
 * `role="menuitem"` buttons. Opening focuses the first item; ArrowDown/ArrowUp
 * and Tab/Shift+Tab move between items, wrapping, Home and End jump to the ends,
 * Enter and Space choose, Escape closes. Tab stays inside the menu because the
 * menu is a portal at the end of `<body>`: letting Tab leave it would send focus
 * out of the page rather than on to the next control.
 *
 * Choosing **React** swaps the menu's items for the six emoji in the same popup,
 * so Escape and an outside press apply to one popup and not two.
 *
 * **The menu is a portal, `position: fixed`.** The message list and the thread
 * panel both scroll (`overflow-y-auto`), and an absolutely positioned popup
 * inside a row would be clipped by them. `placeMenu` puts it below "⋯" when it
 * fits, otherwise above, clamped inside the viewport, and it is placed again on
 * any scroll or resize while open. A scroll does not close it: a new message
 * scrolling the list would otherwise close the menu every time someone speaks.
 *
 * **It closes on a `pointerdown` outside, Escape, or a choice — never on blur.**
 * Closing on blur reads as tidier and races the option's own click: focus leaves
 * the row, the row unmounts, and the click lands on nothing. That failure is
 * intermittent rather than absolute, which is the worst kind to have underneath
 * an acceptance test. For the same reason "outside" is DOM containment against
 * the portal's own node, never React's tree, where a portal's events still
 * bubble to its parents.
 *
 * Only one menu is open at a time, through `openMessageMenu` in the chat store
 * (D24: an instance id, client state). That covers a screen reader's `click`,
 * which sends no `pointerdown` to close the other.
 *
 * **Focus.** A close by Escape, a choice, an outside press or a change in the
 * offered actions returns focus to "⋯". On an outside press with focus in the
 * menu, "⋯" takes it first and the press's own default then does what the
 * platform does (a press on an input focuses it) — no `preventDefault`, which
 * would block text selection and focus wherever the user pressed. If the row
 * goes away while it holds focus (a live delete), focus goes to the nearest
 * `[data-focus-fallback]` and never falls to the page body.
 */

import {
  type KeyboardEvent,
  type Ref,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from 'react'
import { createPortal } from 'react-dom'

import { useChatStore } from '../../stores/chat'
import type { MessageAction } from './actionRules'
import { placeMenu } from './menuPlacement'
import { REACTION_EMOJI, glyphFor, labelFor } from './reactions'

interface Props {
  /** At least one; `MessageItem` renders nothing for none. */
  actions: readonly MessageAction[]
  onReact: (emoji: string) => void
  onReply: () => void
  onEdit: () => void
  onDelete: () => void
  /** The "⋯" button, so `MessageItem` can return focus to it after editing. */
  triggerRef?: Ref<HTMLButtonElement>
}

const ITEM_CLASS =
  'w-full rounded px-2 py-1 text-left text-sm text-ink hover:bg-surface-sunken focus:bg-surface-sunken focus:outline-none'

export function MessageActions({
  actions,
  onReact,
  onReply,
  onEdit,
  onDelete,
  triggerRef,
}: Props) {
  const id = useId()
  const open = useChatStore((state) => state.openMessageMenu === id)
  const [mode, setMode] = useState<'menu' | 'emoji'>('menu')
  const trigger = useRef<HTMLButtonElement | null>(null)
  const menu = useRef<HTMLDivElement | null>(null)

  const setTrigger = useCallback(
    (node: HTMLButtonElement | null) => {
      trigger.current = node
      if (typeof triggerRef === 'function') triggerRef(node)
      else if (triggerRef) triggerRef.current = node
    },
    [triggerRef],
  )

  const close = useCallback(() => {
    useChatStore.getState().closeMessageMenu(id)
    trigger.current?.focus({ preventScroll: true })
  }, [id])

  function choose(then: () => void) {
    close()
    then()
  }

  // Place the menu next to "⋯", before paint. Position is set on the node rather
  // than held in state: it changes on every scroll, and nothing else reads it.
  const place = useCallback(() => {
    const node = menu.current
    const anchor = trigger.current
    if (!node || !anchor) return
    const { top, left } = placeMenu(
      anchor.getBoundingClientRect(),
      node.getBoundingClientRect(),
      { width: window.innerWidth, height: window.innerHeight },
    )
    node.style.top = `${top}px`
    node.style.left = `${left}px`
  }, [])

  // On opening, and on the swap to the emoji row: place, and focus the first item.
  useLayoutEffect(() => {
    if (!open) return
    place()
    menu.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus({ preventScroll: true })
  }, [open, mode, place])

  useEffect(() => {
    if (!open) return
    function onPointerDown(event: PointerEvent) {
      const target = event.target
      if (!(target instanceof Node)) return
      if (trigger.current?.contains(target) || menu.current?.contains(target)) return
      // Focus in the menu would be lost to the body when it unmounts.
      if (menu.current?.contains(document.activeElement)) {
        trigger.current?.focus({ preventScroll: true })
      }
      useChatStore.getState().closeMessageMenu(id)
    }
    function onKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        close()
      }
    }
    document.addEventListener('pointerdown', onPointerDown, true)
    document.addEventListener('keydown', onKeyDown)
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown, true)
      document.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [open, id, place, close])

  // The offered actions changing under an open menu closes it: items moving under
  // the user's finger is worse. Compared by value — every render of a row makes a
  // new array, and a live reaction or edit must not close the menu.
  const actionsKey = actions.join(',')
  const seenKey = useRef(actionsKey)
  useLayoutEffect(() => {
    if (seenKey.current === actionsKey) return
    seenKey.current = actionsKey
    if (useChatStore.getState().openMessageMenu === id) close()
  }, [actionsKey, id, close])

  // Going away: clear our open id (and no one else's), and if focus is on "⋯" or
  // in the menu, hand it to the fallback — a removed node leaves it on the body.
  // A deleted component's layout cleanup runs before React removes its host
  // nodes, so the focused node is still in the document here.
  useLayoutEffect(() => {
    return () => {
      useChatStore.getState().closeMessageMenu(id)
      const active = document.activeElement
      const anchor = trigger.current
      if (anchor && active && (active === anchor || document.getElementById(id)?.contains(active))) {
        anchor.closest<HTMLElement>('[data-focus-fallback]')?.focus({ preventScroll: true })
      }
    }
  }, [id])

  function onMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const items = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]'),
    )
    if (items.length === 0) return
    const at = items.indexOf(document.activeElement as HTMLElement)
    let next: number
    switch (event.key) {
      case 'ArrowDown':
        next = (at + 1) % items.length
        break
      case 'Tab':
        next = event.shiftKey ? (at - 1 + items.length) % items.length : (at + 1) % items.length
        break
      case 'ArrowUp':
        next = (at - 1 + items.length) % items.length
        break
      case 'Home':
        next = 0
        break
      case 'End':
        next = items.length - 1
        break
      default:
        return
    }
    event.preventDefault()
    items[next]?.focus({ preventScroll: true })
  }

  function toggle() {
    if (open) {
      close()
      return
    }
    setMode('menu')
    useChatStore.getState().openMessageMenuFor(id)
  }

  const items: Record<MessageAction, { label: string; testId: string; onChoose: () => void }> = {
    react: { label: 'React', testId: 'reaction-picker', onChoose: () => setMode('emoji') },
    reply: { label: 'Reply in thread', testId: 'thread-open', onChoose: () => choose(onReply) },
    edit: { label: 'Edit', testId: 'message-edit', onChoose: () => choose(onEdit) },
    delete: { label: 'Delete', testId: 'message-delete', onChoose: () => choose(onDelete) },
  }

  return (
    <>
      <button
        ref={setTrigger}
        type="button"
        data-testid="message-actions"
        aria-label="Message actions"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={toggle}
        className="ml-auto rounded px-1.5 text-base leading-none text-ink-muted hover:bg-surface-sunken"
      >
        <span aria-hidden="true">⋯</span>
      </button>

      {open &&
        createPortal(
          <div
            ref={menu}
            id={id}
            role="menu"
            aria-label={mode === 'emoji' ? 'Add a reaction' : 'Message actions'}
            data-testid="message-actions-menu"
            // top and left are set by `place`, before paint.
            style={{ position: 'fixed', top: 0, left: 0 }}
            onKeyDown={onMenuKeyDown}
            className={`z-50 rounded-md border border-border bg-surface p-1 shadow ${mode === 'emoji' ? 'flex gap-1' : 'flex min-w-40 flex-col'}`}
          >
            {mode === 'emoji'
              ? REACTION_EMOJI.map((emoji) => (
                  <button
                    key={emoji}
                    type="button"
                    role="menuitem"
                    data-testid="reaction-option"
                    data-emoji={emoji}
                    aria-label={labelFor(emoji)}
                    onClick={() => choose(() => onReact(emoji))}
                    className="rounded px-1 text-base hover:bg-surface-sunken focus:bg-surface-sunken focus:outline-none"
                  >
                    <span aria-hidden="true">{glyphFor(emoji)}</span>
                  </button>
                ))
              : actions.map((action) => (
                  <button
                    key={action}
                    type="button"
                    role="menuitem"
                    data-testid={items[action].testId}
                    onClick={items[action].onChoose}
                    className={`${ITEM_CLASS} ${action === 'delete' ? 'text-danger' : ''}`}
                  >
                    {items[action].label}
                  </button>
                ))}
          </div>,
          document.body,
        )}
    </>
  )
}
