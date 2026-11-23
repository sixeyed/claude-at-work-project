/**
 * The "⋯" menu (gh-8 Req 1–5): a menu button that opens exactly the actions a
 * message allows, closes on Escape, a choice or a press outside it, returns
 * focus to "⋯", and is in the document (portal), never inside the row.
 *
 * Queried by role and name only: the menu is in a portal on `document.body`, so
 * `screen`, never `within(row)`.
 *
 * Two kinds of "press outside" are used on purpose. `fireEvent.pointerDown` alone
 * has no default action — it stands for a touch that starts a scroll. `user.click`
 * dispatches the whole pointer sequence, whose `mousedown` default moves focus as
 * a browser does (checked in user-event's `system/pointer/mouse.js` and
 * `event/focus.js`). Which one a test uses is part of what it proves.
 *
 * The component is rendered with the plan's literal values: nothing here is
 * driven by an import from a module that does not exist yet, apart from the
 * component itself.
 */

import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useChatStore } from '../../stores/chat'
import { renderWithProviders } from '../../test/render'
import type { MessageAction } from './actionRules'
import { MessageActions } from './MessageActions'

const ALL: readonly MessageAction[] = ['react', 'reply', 'edit', 'delete']

function handlers() {
  return { onReact: vi.fn(), onReply: vi.fn(), onEdit: vi.fn(), onDelete: vi.fn() }
}
type Handlers = ReturnType<typeof handlers>

function ui(actions: readonly MessageAction[] = ALL, h: Handlers = handlers()) {
  return <MessageActions actions={actions} {...h} />
}

const trigger = () => screen.getByRole('button', { name: 'Message actions' })
const triggers = () => screen.getAllByRole('button', { name: 'Message actions' })
const menus = () => screen.queryAllByRole('menu')
const itemNames = () => screen.getAllByRole('menuitem').map((item) => item.textContent?.trim())
const item = (name: string | RegExp) => screen.getByRole('menuitem', { name })
const focused = () => document.activeElement

describe('MessageActions — the button', () => {
  it('"Message actions" is a menu button, collapsed, with no menu until pressed', async () => {
    const { user } = renderWithProviders(ui())

    expect(trigger()).toHaveAttribute('aria-haspopup', 'menu')
    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
    expect(menus()).toHaveLength(0)

    await user.click(trigger())

    expect(trigger()).toHaveAttribute('aria-expanded', 'true')
    expect(menus()).toHaveLength(1)
  })

  it('pressing it opens exactly the given items, in order, and focuses the first', async () => {
    const first = renderWithProviders(ui(ALL))
    await first.user.click(trigger())

    expect(screen.getByRole('menu', { name: 'Message actions' })).toBeInTheDocument()
    expect(itemNames()).toEqual(['React', 'Reply in thread', 'Edit', 'Delete'])
    expect(focused()).toBe(item('React'))
    first.unmount()

    const second = renderWithProviders(ui(['react']))
    await second.user.click(trigger())

    expect(itemNames()).toEqual(['React'])
    expect(focused()).toBe(item('React'))
  })

  it('is in a portal on the document body, not inside the component’s own node', async () => {
    const { user, container } = renderWithProviders(ui())
    await user.click(trigger())

    const menu = screen.getByRole('menu')

    expect(container.contains(menu)).toBe(false)
    expect(document.body.contains(menu)).toBe(true)
  })
})

describe('MessageActions — the keyboard', () => {
  it('ArrowDown, ArrowUp, Home, End, Tab and Shift+Tab reach every item, wrapping at both ends', async () => {
    const { user } = renderWithProviders(ui())
    await user.click(trigger())
    expect(focused()).toBe(item('React'))

    await user.keyboard('{ArrowDown}')
    expect(focused()).toBe(item('Reply in thread'))
    await user.keyboard('{ArrowDown}')
    expect(focused()).toBe(item('Edit'))
    await user.keyboard('{ArrowUp}')
    expect(focused()).toBe(item('Reply in thread'))

    await user.keyboard('{End}')
    expect(focused()).toBe(item('Delete'))
    await user.keyboard('{ArrowDown}')
    expect(focused()).toBe(item('React'))
    await user.keyboard('{ArrowUp}')
    expect(focused()).toBe(item('Delete'))
    await user.keyboard('{Home}')
    expect(focused()).toBe(item('React'))

    await user.tab()
    expect(focused()).toBe(item('Reply in thread'))
    await user.tab({ shift: true })
    expect(focused()).toBe(item('React'))
    await user.tab({ shift: true })
    expect(focused()).toBe(item('Delete'))
    await user.tab()
    expect(focused()).toBe(item('React'))
    // Tab never left the menu for the page.
    expect(menus()).toHaveLength(1)
  })

  it('Enter on a focused item chooses it: Delete calls onDelete once, the menu closes, focus is on "⋯"', async () => {
    const h = handlers()
    const { user } = renderWithProviders(ui(ALL, h))
    await user.click(trigger())
    await user.keyboard('{End}')
    expect(focused()).toBe(item('Delete'))

    await user.keyboard('{Enter}')

    expect(h.onDelete).toHaveBeenCalledOnce()
    expect(h.onEdit).not.toHaveBeenCalled()
    expect(menus()).toHaveLength(0)
    expect(focused()).toBe(trigger())
  })

  it('Escape closes the menu and focus returns to "⋯"', async () => {
    const { user } = renderWithProviders(ui())
    await user.click(trigger())
    expect(menus()).toHaveLength(1)

    await user.keyboard('{Escape}')

    expect(menus()).toHaveLength(0)
    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
    expect(focused()).toBe(trigger())
  })
})

describe('MessageActions — a choice', () => {
  it.each([
    ['Reply in thread', 'onReply'],
    ['Edit', 'onEdit'],
    ['Delete', 'onDelete'],
  ] as const)('choosing %s closes the menu, calls only %s once, and returns focus to "⋯"', async (name, handler) => {
    const h = handlers()
    const { user } = renderWithProviders(ui(ALL, h))
    await user.click(trigger())

    await user.click(item(name))

    expect(h[handler]).toHaveBeenCalledOnce()
    for (const other of Object.values(h).filter((fn) => fn !== h[handler])) {
      expect(other).not.toHaveBeenCalled()
    }
    expect(menus()).toHaveLength(0)
    expect(focused()).toBe(trigger())
  })

  it('"⋯" toggles: a second press closes the menu', async () => {
    const { user } = renderWithProviders(ui())

    await user.click(trigger())
    expect(menus()).toHaveLength(1)

    // Its own pointerdown is not "outside": else it closes, and the click reopens.
    await user.click(trigger())
    expect(menus()).toHaveLength(0)
  })
})

describe('MessageActions — a press outside', () => {
  it('a touch that starts a scroll outside closes it, chooses nothing, and focus is on "⋯", not the body', async () => {
    const h = handlers()
    const { user } = renderWithProviders(
      <>
        {ui(ALL, h)}
        <div>somewhere else</div>
      </>,
    )
    await user.click(trigger())
    expect(focused()).toBe(item('React'))

    // No click, no mousedown: the touch only began a scroll.
    fireEvent.pointerDown(screen.getByText('somewhere else'), { pointerType: 'touch' })

    expect(menus()).toHaveLength(0)
    expect(Object.values(h).every((fn) => fn.mock.calls.length === 0)).toBe(true)
    expect(focused()).toBe(trigger())
    expect(focused()).not.toBe(document.body)
  })

  it('a press on an outside input closes the menu, chooses nothing and leaves focus in that input', async () => {
    const h = handlers()
    const { user } = renderWithProviders(
      <>
        {ui(ALL, h)}
        <input aria-label="Elsewhere" />
      </>,
    )
    await user.click(trigger())
    expect(menus()).toHaveLength(1)

    await user.click(screen.getByRole('textbox', { name: 'Elsewhere' }))

    expect(menus()).toHaveLength(0)
    expect(Object.values(h).every((fn) => fn.mock.calls.length === 0)).toBe(true)
    expect(focused()).toBe(screen.getByRole('textbox', { name: 'Elsewhere' }))
  })

  it('a pointer-down inside the menu does not close it', async () => {
    const { user } = renderWithProviders(
      <>
        {ui()}
        <div>somewhere else</div>
      </>,
    )
    await user.click(trigger())

    fireEvent.pointerDown(screen.getByRole('menu'), { pointerType: 'touch' })
    fireEvent.pointerDown(item('Edit'), { pointerType: 'touch' })
    expect(menus()).toHaveLength(1)

    // The positive: the same event on the outside does close it.
    fireEvent.pointerDown(screen.getByText('somewhere else'), { pointerType: 'touch' })
    expect(menus()).toHaveLength(0)
  })
})

describe('MessageActions — React', () => {
  const EMOJI_LABELS = ['thumbs up', 'heart', 'celebrate', 'smile', 'eyes', 'check']

  async function openEmojiRow(h: Handlers = handlers()) {
    const view = renderWithProviders(
      <>
        {ui(ALL, h)}
        <div>somewhere else</div>
      </>,
    )
    await view.user.click(trigger())
    await view.user.click(item('React'))
    return { ...view, h }
  }

  it('React swaps the items for the six emoji, focus on the first', async () => {
    const { h } = await openEmojiRow()

    expect(screen.getByRole('menu', { name: 'Add a reaction' })).toBeInTheDocument()
    expect(screen.queryByRole('menu', { name: 'Message actions' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('menuitem').map((e) => e.getAttribute('aria-label'))).toEqual(
      EMOJI_LABELS,
    )
    expect(screen.queryByRole('menuitem', { name: 'Delete' })).not.toBeInTheDocument()
    expect(focused()).toBe(item('thumbs up'))
    expect(h.onReact).not.toHaveBeenCalled()
  })

  it('picking an emoji calls onReact once with it, closes the row and the menu, focus on "⋯"', async () => {
    const { user, h } = await openEmojiRow()
    await user.keyboard('{ArrowDown}{ArrowDown}')
    expect(focused()).toBe(item('celebrate'))

    await user.keyboard('{Enter}')

    expect(h.onReact).toHaveBeenCalledExactlyOnceWith('tada')
    expect(menus()).toHaveLength(0)
    expect(focused()).toBe(trigger())
  })

  it('a tap on an emoji is not swallowed by the outside-close', async () => {
    const { user, h } = await openEmojiRow()

    // The full pointerdown, mouseup, click sequence on the option, which sits in the
    // portal: a containment check against React's tree, or a close on blur, loses it.
    await user.click(item('celebrate'))

    expect(h.onReact).toHaveBeenCalledExactlyOnceWith('tada')
    expect(menus()).toHaveLength(0)
  })

  it('Escape in the emoji row closes both and returns focus to "⋯"', async () => {
    const { user } = await openEmojiRow()
    expect(menus()).toHaveLength(1)

    await user.keyboard('{Escape}')

    expect(menus()).toHaveLength(0)
    expect(focused()).toBe(trigger())
  })

  it('a pointer-down outside the emoji row closes it and adds no reaction', async () => {
    const { h } = await openEmojiRow()
    expect(screen.getAllByRole('menuitem')).toHaveLength(6)

    fireEvent.pointerDown(screen.getByText('somewhere else'), { pointerType: 'touch' })

    expect(menus()).toHaveLength(0)
    expect(h.onReact).not.toHaveBeenCalled()
  })
})

describe('MessageActions — one at a time', () => {
  it('opening one menu closes another, even with no pointer-down', async () => {
    const { user } = renderWithProviders(
      <>
        {ui()}
        {ui()}
      </>,
    )
    const [a, b] = triggers()

    await user.click(a)
    expect(menus()).toHaveLength(1)
    expect(a).toHaveAttribute('aria-expanded', 'true')

    // A screen reader's activation: a click with no pointerdown before it.
    fireEvent.click(b)

    expect(menus()).toHaveLength(1)
    expect(a).toHaveAttribute('aria-expanded', 'false')
    expect(b).toHaveAttribute('aria-expanded', 'true')
    expect(menus()[0].id).toBe(b.getAttribute('aria-controls'))
  })
})

describe('MessageActions — the actions changing while open', () => {
  it('closes the menu, focus on "⋯", when the offered actions change', async () => {
    const h = handlers()
    const view = renderWithProviders(ui(['react', 'reply', 'delete'], h))
    await view.user.click(trigger())
    expect(itemNames()).toEqual(['React', 'Reply in thread', 'Delete'])

    view.rerender(ui(['react', 'reply'], h))

    expect(menus()).toHaveLength(0)
    expect(focused()).toBe(trigger())
  })

  it('a re-render with the same actions in a new array keeps the menu open and focus where it was', async () => {
    const h = handlers()
    const view = renderWithProviders(ui(['react', 'reply', 'delete'], h))
    await view.user.click(trigger())
    await view.user.keyboard('{ArrowDown}')
    expect(focused()).toBe(item('Reply in thread'))
    const menu = screen.getByRole('menu')

    // Every render of a row makes a fresh array: it is no change.
    view.rerender(ui(['react', 'reply', 'delete'], h))

    expect(screen.getByRole('menu')).toBe(menu)
    expect(focused()).toBe(item('Reply in thread'))
  })
})

describe('MessageActions — going away', () => {
  function Surface({ shown, h = handlers() }: { shown: boolean; h?: Handlers }) {
    return (
      <>
        <div data-focus-fallback tabIndex={-1} aria-label="the fallback" role="region">
          {shown && ui(ALL, h)}
        </div>
        <input aria-label="Elsewhere" />
      </>
    )
  }
  const fallback = () => screen.getByRole('region', { name: 'the fallback' })

  it('unmounting with focus on "⋯" or in its menu moves focus to the fallback; with focus elsewhere, leaves it', async () => {
    const h = handlers()

    // Focus on "⋯", menu shut.
    const onTrigger = renderWithProviders(<Surface shown h={h} />)
    trigger().focus()
    expect(focused()).toBe(trigger())
    onTrigger.rerender(<Surface shown={false} h={h} />)
    expect(focused()).toBe(fallback())
    onTrigger.unmount()

    // Focus inside the open menu.
    const inMenu = renderWithProviders(<Surface shown h={h} />)
    await inMenu.user.click(trigger())
    expect(focused()).toBe(item('React'))
    inMenu.rerender(<Surface shown={false} h={h} />)
    expect(menus()).toHaveLength(0)
    expect(focused()).toBe(fallback())
    inMenu.unmount()

    // Focus on something else: a build that always focuses the fallback fails here.
    const elsewhere = renderWithProviders(<Surface shown h={h} />)
    await elsewhere.user.click(trigger())
    const input = screen.getByRole('textbox', { name: 'Elsewhere' })
    input.focus()
    expect(focused()).toBe(input)
    elsewhere.rerender(<Surface shown={false} h={h} />)
    expect(focused()).toBe(input)
  })

  it('unmounting clears its own open id, and not another’s', async () => {
    const h = handlers()
    const both = (showA: boolean, showB: boolean) => (
      <>
        {showA && <div data-testid="a">{ui(ALL, h)}</div>}
        {showB && <div data-testid="b">{ui(ALL, h)}</div>}
      </>
    )
    const view = renderWithProviders(both(true, true))
    const [a, b] = triggers()
    await view.user.click(a)
    await view.user.click(b)
    expect(menus()).toHaveLength(1)
    expect(useChatStore.getState().openMessageMenu).not.toBeNull()

    view.rerender(both(false, true))

    expect(menus()).toHaveLength(1)
    expect(useChatStore.getState().openMessageMenu).toBe(trigger().getAttribute('aria-controls'))

    view.rerender(both(false, false))

    expect(useChatStore.getState().openMessageMenu).toBeNull()
  })
})

describe('MessageActions — where it opens', () => {
  it('the menu sits where placeMenu puts it, and follows a scroll', async () => {
    expect(window.innerWidth).toBe(1024)
    expect(window.innerHeight).toBe(768)
    let anchor = { top: 700, bottom: 720, left: 990, right: 1010 }
    const original = Element.prototype.getBoundingClientRect
    const spy = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (
      this: Element,
    ) {
      if (this.getAttribute('role') === 'menu') {
        return { top: 0, bottom: 150, left: 0, right: 160, width: 160, height: 150 } as DOMRect
      }
      if (this.getAttribute('aria-haspopup') === 'menu') {
        const { top, bottom, left, right } = anchor
        return { top, bottom, left, right, width: right - left, height: bottom - top } as DOMRect
      }
      return original.call(this)
    })
    try {
      const { user } = renderWithProviders(
        <>
          {ui()}
          <div>a scroller outside the menu</div>
        </>,
      )

      await user.click(trigger())

      const menu = screen.getByRole('menu')
      // 720 + 4 + 150 = 874 > 760, so above: 700 − 4 − 150. Right-aligned: 1010 − 160.
      expect(menu.style.position).toBe('fixed')
      expect(menu.style.top).toBe('546px')
      expect(menu.style.left).toBe('850px')

      anchor = { top: 300, bottom: 320, left: 990, right: 1010 }
      fireEvent.scroll(screen.getByText('a scroller outside the menu'))

      expect(screen.getByRole('menu')).toBe(menu)
      expect(menu.style.top).toBe('324px')
      expect(menu.style.left).toBe('850px')
    } finally {
      spy.mockRestore()
    }
  })
})
