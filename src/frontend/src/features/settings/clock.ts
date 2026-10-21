/**
 * The clock preference, and the one place a time is formatted for display
 * (register D28).
 *
 * `hourCycle` rather than `hour12`: `hour12: false` can print midnight as
 * "24:05" in some engines, `h23` cannot. With no preference the options are
 * exactly what the app used before the preference existed — the browser's locale
 * decides — and no `hourCycle` key is present at all.
 *
 * The preference reaches the three components that show a time through a
 * context, provided once by `ChatLayout` from the preferences query, so a leaf
 * stays free of tokens and queries and re-renders when the choice changes
 * without any message being refetched.
 */

import { createContext, useContext } from 'react'

import type { Clock } from '../../lib/auth/api'

/** `undefined` is Automatic: the browser's locale. */
export const ClockContext = createContext<Clock | undefined>(undefined)

export function useClock(): Clock | undefined {
  return useContext(ClockContext)
}

const HOUR_CYCLE = { '12h': 'h12', '24h': 'h23' } as const

function hourCycle(clock: Clock | undefined): { hourCycle?: 'h12' | 'h23' } {
  return clock === undefined ? {} : { hourCycle: HOUR_CYCLE[clock] }
}

export function timeOptions(clock?: Clock): Intl.DateTimeFormatOptions {
  return { hour: '2-digit', minute: '2-digit', ...hourCycle(clock) }
}

export function dateTimeOptions(clock?: Clock): Intl.DateTimeFormatOptions {
  return { dateStyle: 'medium', timeStyle: 'short', ...hourCycle(clock) }
}

export function formatTime(iso: string, clock?: Clock): string {
  return new Date(iso).toLocaleTimeString([], timeOptions(clock))
}

export function formatDateTime(iso: string, clock?: Clock): string {
  return new Date(iso).toLocaleString([], dateTimeOptions(clock))
}
