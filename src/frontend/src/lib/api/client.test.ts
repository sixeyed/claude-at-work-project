import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { messaging, MESSAGING_URL, server } from '../../test/api'
import { bearer, describeError, problemFrom, problemFromBody, ProblemError } from './client'

describe('problemFrom', () => {
  it('keeps the field errors from a problem document', async () => {
    messaging.problem('post', '/api/v1/channels', 400, {
      title: 'Validation error',
      detail: 'A channel name is required.',
      errors: { name: ['A channel name is required.'] },
    })

    const response = await fetch(`${MESSAGING_URL}/api/v1/channels`, { method: 'POST' })
    const problem = await problemFrom(response)

    expect(problem).toBeInstanceOf(ProblemError)
    expect(problem.status).toBe(400)
    expect(problem.title).toBe('Validation error')
    expect(problem.message).toBe('A channel name is required.')
    expect(problem.fieldError('name')).toBe('A channel name is required.')
  })

  it('says something when a proxy answers with no problem document at all', async () => {
    server.use(
      http.get(`${MESSAGING_URL}/api/v1/channels`, () =>
        HttpResponse.text('<html>bad gateway</html>', { status: 502, statusText: 'Bad Gateway' }),
      ),
    )

    const problem = await problemFrom(await fetch(`${MESSAGING_URL}/api/v1/channels`))

    expect(problem.status).toBe(502)
    expect(problem.message).toBe('Bad Gateway')
    expect(problem.errors).toEqual({})
  })

  it('uses the title when there is no detail', async () => {
    messaging.problem('get', '/api/v1/channels', 403, { title: 'Forbidden' })

    const problem = await problemFrom(await fetch(`${MESSAGING_URL}/api/v1/channels`))

    expect(problem.message).toBe('Forbidden')
  })
})

describe('problemFromBody', () => {
  it('builds the same error from a socket acknowledgement', () => {
    const problem = problemFromBody(400, {
      title: 'Validation error',
      detail: 'A message cannot be empty.',
      errors: { body: ['A message cannot be empty.'] },
    })

    expect(problem.status).toBe(400)
    expect(problem.message).toBe('A message cannot be empty.')
    expect(problem.fieldError('body')).toBe('A message cannot be empty.')
  })

  it('never produces an error with no message', () => {
    const problem = problemFromBody(503, undefined)

    expect(problem.message).toBe('Something went wrong.')
    expect(problem.fieldError('body')).toBeUndefined()
  })
})

describe('describeError', () => {
  it('shows an error’s own message', () => {
    expect(describeError(new Error('Not connected. Try again in a moment.'))).toBe(
      'Not connected. Try again in a moment.',
    )
  })

  it('does not show whatever else was thrown', () => {
    expect(describeError({ stack: 'secret' })).toBe('Something went wrong.')
  })
})

describe('bearer', () => {
  it('is an Authorization header', () => {
    expect(bearer('abc.def.ghi')).toEqual({ Authorization: 'Bearer abc.def.ghi' })
  })
})

describe('the test harness', () => {
  it('fails a request that nothing stubbed', async () => {
    await expect(fetch(`${MESSAGING_URL}/api/v1/channels`)).rejects.toThrow()
  })

  it('types a stub from the OpenAPI document', () => {
    // @ts-expect-error — `items` holds channels, and a number is not one. If
    // this line stops being an error, stubs can drift from the API (D23).
    messaging.get('/api/v1/channels', { items: [1], nextCursor: null })
  })
})
