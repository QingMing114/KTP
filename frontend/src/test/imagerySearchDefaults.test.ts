import { expect, it } from 'vitest'
import { defaultManualImageryDates, assistantImagerySearch } from '../features/workspace-assistant/imagerySearchDefaults'

it('initializes a full year of manual dates instead of a single day without changing the input date', () => {
  const now = new Date(2026, 9, 14, 15, 30)
  const timestamp = now.getTime()
  expect(defaultManualImageryDates(now)).toEqual({ start: '2025-10-14', end: '2026-10-14' })
  expect(now.getTime()).toBe(timestamp)
})

it('does not send manual card dates to the assistant in automatic mode', () => {
  expect(assistantImagerySearch(true, '2026-10-14', '2026-10-14')).toBeUndefined()
  expect(assistantImagerySearch(true, '2030-01-01', '2020-01-01')).toBeUndefined()
  expect(assistantImagerySearch(false, '2026-06-01', '2026-06-30')).toEqual({ start_date: '2026-06-01', end_date: '2026-06-30', max_cloud_cover: 20 })
})
