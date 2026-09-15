/**
 * REST stubbed at the network edge, so `openapi-fetch` and TanStack Query run
 * for real (design, Framework 3).
 *
 * **Messaging stubs are typed from the generated `src/types/messaging.ts`**
 * (register D23). A stub is addressed by its OpenAPI path and its body must be
 * that operation's success response, so a stub that no longer matches the API
 * fails `tsc` rather than passing a test against a shape the server never
 * sends. Auth has no generated types yet, so its stubs use the interfaces in
 * `lib/auth/api.ts` — the same ones the app trusts.
 *
 * Every request that reaches a stub is recorded, so a test can assert what was
 * sent as well as what came back. Anything unstubbed fails the test
 * (`onUnhandledRequest: 'error'` in `setup.ts`).
 */

import { http, HttpResponse, type DefaultBodyType } from 'msw'
import { setupServer } from 'msw/node'

import type { Profile, TokenPair, Workspace, WorkspaceMember } from '../lib/auth/api'
import type { paths } from '../types/messaging'

export const MESSAGING_URL: string = import.meta.env.VITE_MESSAGING_URL ?? 'http://localhost:8002'
export const AUTH_URL: string = import.meta.env.VITE_AUTH_URL ?? 'http://localhost:8001'

export const server = setupServer()

type Method = 'get' | 'post' | 'patch' | 'delete'

type JsonOf<T> = T extends { content: { 'application/json': infer B } } ? B : never

/** The 200 or 201 body an operation declares. */
type SuccessBody<Op> = Op extends { responses: infer R }
  ? { [S in keyof R]: S extends 200 | 201 ? JsonOf<R[S]> : never }[keyof R]
  : never

type RequestJson<Op> = Op extends { requestBody?: infer B } ? JsonOf<NonNullable<B>> : undefined

/** OpenAPI paths that declare `method` with a JSON success body. */
type PathsWith<M extends Method> = {
  [P in keyof paths]: [SuccessBody<paths[P][M]>] extends [never] ? never : P
}[keyof paths]

type Body<P extends keyof paths, M extends Method> = SuccessBody<paths[P][M]>

interface Context<P extends keyof paths, M extends Method> {
  params: Record<string, string>
  body: RequestJson<paths[P][M]>
  request: Request
}

type Reply<P extends keyof paths, M extends Method> =
  | Body<P, M>
  | ((context: Context<P, M>) => Body<P, M> | Promise<Body<P, M>>)

export interface ProblemBody {
  type?: string
  title?: string
  status?: number
  detail?: string
  errors?: Record<string, string[]>
}

export interface Recorded {
  method: string
  url: URL
  body: unknown
}

const recorded: Recorded[] = []

/** Every request a stub answered, in order. Reset after each test. */
export function requests(): readonly Recorded[] {
  return recorded
}

export function resetRequests(): void {
  recorded.length = 0
}

async function record(request: Request): Promise<unknown> {
  const text = await request.clone().text()
  const body = text ? JSON.parse(text) : undefined
  recorded.push({ method: request.method, url: new URL(request.url), body })
  return body
}

/** `/api/v1/channels/{channel_id}` → MSW's `/api/v1/channels/:channel_id`. */
function route(base: string, path: string): string {
  return base + path.replace(/\{(\w+)\}/g, ':$1')
}

function params(raw: Record<string, string | readonly string[] | undefined>) {
  return Object.fromEntries(Object.entries(raw).map(([k, v]) => [k, String(v)]))
}

function problemResponse(status: number, body: ProblemBody) {
  return HttpResponse.json(
    { status, ...body },
    { status, headers: { 'Content-Type': 'application/problem+json' } },
  )
}

function stub<M extends Method>(method: M, status: number) {
  return <P extends PathsWith<M>>(path: P, reply: Reply<P, M>): void => {
    server.use(
      http[method](route(MESSAGING_URL, path), async ({ request, params: raw }) => {
        const body = (await record(request)) as RequestJson<paths[P][M]>
        const payload =
          typeof reply === 'function'
            ? await (reply as (c: Context<P, M>) => Body<P, M>)({
                params: params(raw),
                body,
                request,
              })
            : reply
        return HttpResponse.json(payload as DefaultBodyType, { status })
      }),
    )
  }
}

export const messaging = {
  get: stub('get', 200),
  post: stub('post', 201),
  patch: stub('patch', 200),
  delete: stub('delete', 200),

  /** A 204 with no body, for the routes that declare no success content. */
  noContent(method: Method, path: keyof paths): void {
    server.use(
      http[method](route(MESSAGING_URL, path), async ({ request }) => {
        await record(request)
        return new HttpResponse(null, { status: 204 })
      }),
    )
  },

  /** An RFC 7807 answer, the only shape a non-2xx ever takes on this platform. */
  problem(method: Method, path: keyof paths, status: number, body: ProblemBody): void {
    server.use(
      http[method](route(MESSAGING_URL, path), async ({ request }) => {
        await record(request)
        return problemResponse(status, body)
      }),
    )
  },
}

function authJson<T extends DefaultBodyType>(method: Method, path: string, reply: T) {
  server.use(
    http[method](AUTH_URL + path, async ({ request }) => {
      await record(request)
      return HttpResponse.json(reply)
    }),
  )
}

export const auth = {
  /** The workspace directory `useWorkspaceMembers` reads, as one page. */
  members(members: WorkspaceMember[]): void {
    authJson('get', '/api/v1/workspaces/:workspaceId/members', { items: members, nextCursor: null })
  },
  refresh: (pair: TokenPair) => authJson('post', '/api/v1/auth/refresh', { ...pair }),
  exchange: (pair: TokenPair) => authJson('post', '/api/v1/auth/token', { ...pair }),
  switchWorkspace: (pair: TokenPair) =>
    authJson('post', '/api/v1/auth/switch-workspace', { ...pair }),
  me: (profile: Profile) => authJson('get', '/api/v1/users/me', { ...profile }),
  workspaces: (items: Workspace[]) => authJson('get', '/api/v1/workspaces', { items }),
  logout(): void {
    server.use(
      http.post(`${AUTH_URL}/api/v1/auth/logout`, async ({ request }) => {
        await record(request)
        return new HttpResponse(null, { status: 204 })
      }),
    )
  },
  problem(method: Method, path: string, status: number, body: ProblemBody): void {
    server.use(
      http[method](AUTH_URL + path, async ({ request }) => {
        await record(request)
        return problemResponse(status, body)
      }),
    )
  },
}
