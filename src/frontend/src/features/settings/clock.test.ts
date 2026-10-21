/**
 * The clock preference's options and output (issue Req 7; plan Decision 23).
 *
 * `hourCycle` rather than `hour12`: `hour12: false` can print midnight as "24:05"
 * in some engines, `h23` cannot. Proven here in the suite's own locale, with
 * instants built in local time so "13:05" holds in any time zone.
 */

import { describe, expect, it } from 'vitest'

import { dateTimeOptions, formatDateTime, formatTime, timeOptions } from './clock'

const afternoon = new Date(2026, 8, 15, 13, 5).toISOString()
const justAfterMidnight = new Date(2026, 8, 15, 0, 5).toISOString()

describe('timeOptions and dateTimeOptions', () => {
  it('give today’s options when the clock is Automatic', () => {
    expect(timeOptions()).toStrictEqual({ hour: '2-digit', minute: '2-digit' })
    expect(timeOptions(undefined)).toStrictEqual({ hour: '2-digit', minute: '2-digit' })
    expect(dateTimeOptions()).toStrictEqual({ dateStyle: 'medium', timeStyle: 'short' })
  })

  it('add h12 for the 12-hour clock', () => {
    expect(timeOptions('12h')).toStrictEqual({ hour: '2-digit', minute: '2-digit', hourCycle: 'h12' })
    expect(dateTimeOptions('12h')).toStrictEqual({
      dateStyle: 'medium',
      timeStyle: 'short',
      hourCycle: 'h12',
    })
  })

  it('add h23 for the 24-hour clock', () => {
    expect(timeOptions('24h')).toStrictEqual({ hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
    expect(dateTimeOptions('24h')).toStrictEqual({
      dateStyle: 'medium',
      timeStyle: 'short',
      hourCycle: 'h23',
    })
  })
})

describe('formatTime and formatDateTime', () => {
  it('print 13:05 on the 24-hour clock, and 00:05 just after midnight, never 24:05', () => {
    expect(formatTime(afternoon, '24h')).toMatch(/^13:05/)
    expect(formatTime(justAfterMidnight, '24h')).toMatch(/^00:05/)
    expect(formatDateTime(afternoon, '24h')).toContain('13:05')
    expect(formatDateTime(justAfterMidnight, '24h')).toContain('00:05')
    expect(formatDateTime(justAfterMidnight, '24h')).not.toContain('24:05')
  })

  it('print 1:05, never 13, on the 12-hour clock, and 12:05 just after midnight', () => {
    expect(formatTime(afternoon, '12h')).toMatch(/^0?1:05/)
    expect(formatTime(afternoon, '12h')).not.toContain('13')
    expect(formatTime(justAfterMidnight, '12h')).toMatch(/^12:05/)
    expect(formatDateTime(afternoon, '12h')).toMatch(/\b0?1:05/)
    expect(formatDateTime(afternoon, '12h')).not.toContain('13:05')
  })

  it('print exactly what the browser did before, when the clock is Automatic', () => {
    expect(formatTime(afternoon)).toBe(
      new Date(afternoon).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    )
    expect(formatDateTime(afternoon)).toBe(
      new Date(afternoon).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }),
    )
  })
})
