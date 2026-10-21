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

import type {
  Clock,
  Preferences,
  Profile,
  TokenPair,
  Workspace,
  WorkspaceMember,
} from '../lib/auth/api'
import { ASSET_URL, AUTH_URL, MESSAGING_URL } from '../lib/config'
import type { components as AssetComponents } from '../types/asset'
import type { paths } from '../types/messaging'

// The same values the app calls, so a stub cannot drift from the real URL.
export { ASSET_URL, AUTH_URL, MESSAGING_URL }

/** Where the presigned PUT of the tests goes: Garage, as the browser reaches it. */
export const GARAGE_URL = 'http://garage.test'

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
  /** Parsed JSON; for a body that is not JSON (a file PUT), `{ size }`. */
  body: unknown
  contentType: string | null
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
  const contentType = request.headers.get('content-type')
  const buffer = await request.clone().arrayBuffer()
  let body: unknown
  if (contentType && !contentType.includes('json')) {
    // A file's bytes are not JSON, and a test only needs to know how many arrived.
    body = buffer.byteLength > 0 ? { size: buffer.byteLength } : undefined
  } else {
    const text = new TextDecoder().decode(buffer)
    body = text ? JSON.parse(text) : undefined
  }
  recorded.push({ method: request.method, url: new URL(request.url), body, contentType })
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

  /**
   * A 204 with no body, for the routes that declare no success content.
   * `onRequest` sees the path parameters, so a stub can change what a later
   * read returns — a removal the next list no longer includes.
   */
  noContent(
    method: Method,
    path: keyof paths,
    onRequest?: (params: Record<string, string>) => void,
  ): void {
    server.use(
      http[method](route(MESSAGING_URL, path), async ({ request, params: raw }) => {
        await record(request)
        onRequest?.(params(raw))
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

type AssetSchemas = AssetComponents['schemas']

/** Asset's public routes: what each takes, and the success body it answers with. */
interface AssetRoutes {
  '/api/v1/assets/upload-url': {
    request: AssetSchemas['UploadUrlRequest']
    response: AssetSchemas['UploadUrlResponse']
    status: 201
  }
  '/api/v1/assets/{assetId}/confirm': {
    request: undefined
    response: AssetSchemas['AssetResponse']
    status: 200
  }
}

interface AssetContext<P extends keyof AssetRoutes> {
  params: Record<string, string>
  body: AssetRoutes[P]['request']
  request: Request
}

type AssetReply<P extends keyof AssetRoutes> =
  | AssetRoutes[P]['response']
  | ((context: AssetContext<P>) => AssetRoutes[P]['response'] | Promise<AssetRoutes[P]['response']>)

const ASSET_STATUS: { [P in keyof AssetRoutes]: AssetRoutes[P]['status'] } = {
  '/api/v1/assets/upload-url': 201,
  '/api/v1/assets/{assetId}/confirm': 200,
}

/** What `asset.acceptUploads` can hold back or change, so a test can look between steps. */
export interface UploadScript {
  /** Held until this settles: the step is "in flight" for as long as the test wants. */
  hold?: { uploadUrl?: Promise<unknown>; put?: Promise<unknown>; confirm?: Promise<unknown> }
  /** What `confirm` answers; `ready` by default. */
  confirmAs?: { status: 'ready' | 'failed'; failureReason?: string }
}

export const asset = {
  /** A success answer for one of Asset's public routes, typed from `types/asset.ts` (D23). */
  post<P extends keyof AssetRoutes>(path: P, reply: AssetReply<P>): void {
    server.use(
      http.post(route(ASSET_URL, path), async ({ request, params: raw }) => {
        const body = (await record(request)) as AssetRoutes[P]['request']
        const payload =
          typeof reply === 'function'
            ? await (reply as (c: AssetContext<P>) => AssetRoutes[P]['response'])({
                params: params(raw),
                body,
                request,
              })
            : reply
        return HttpResponse.json(payload as DefaultBodyType, { status: ASSET_STATUS[path] })
      }),
    )
  },

  problem(path: keyof AssetRoutes, status: number, body: ProblemBody): void {
    server.use(
      http.post(route(ASSET_URL, path), async ({ request }) => {
        await record(request)
        return problemResponse(status, body)
      }),
    )
  },

  /**
   * The whole handshake, working: `upload-url` reserves `asset-<fileName>`, the PUT
   * to Garage succeeds, and `confirm` answers with the size and type it was given.
   * `script` holds a step or fails the confirm. Returns the id each file will get.
   */
  acceptUploads(script: UploadScript = {}): { assetIdFor: (fileName: string) => string } {
    const reserved = new Map<string, AssetSchemas['UploadUrlRequest']>()
    asset.post('/api/v1/assets/upload-url', async ({ body }) => {
      await script.hold?.uploadUrl
      const assetId = `asset-${body.fileName}`
      reserved.set(assetId, body)
      return {
        assetId,
        uploadUrl: `${GARAGE_URL}/collabhub-assets/${assetId}`,
        method: 'PUT',
        headers: { 'Content-Type': body.contentType },
        expiresAt: '2026-10-01T09:15:00Z',
      }
    })
    asset.post('/api/v1/assets/{assetId}/confirm', async ({ params: { assetId } }) => {
      await script.hold?.confirm
      const upload = reserved.get(assetId)
      if (!upload) throw new Error(`confirm for an asset nothing reserved: ${assetId}`)
      const outcome = script.confirmAs ?? { status: 'ready' as const }
      return {
        id: assetId,
        fileName: upload.fileName,
        contentType: upload.contentType,
        sizeBytes: upload.sizeBytes,
        status: outcome.status,
        failureReason: outcome.failureReason ?? null,
      }
    })
    garage.put(200, script.hold?.put)
    return { assetIdFor: (fileName) => `asset-${fileName}` }
  },
}

/** The store the presigned URL points at. Only the PUT is ever called from the SPA. */
export const garage = {
  /** Accept every PUT; `hold` keeps it in flight until the promise settles. */
  put(status = 200, hold?: Promise<unknown>): void {
    server.use(
      http.put(`${GARAGE_URL}/*`, async ({ request }) => {
        await record(request)
        await hold
        return new HttpResponse(null, { status })
      }),
    )
  },

  /** A network error with no status: what a browser reports for a PUT Garage refused (no CORS on a failure). */
  putFails(): void {
    server.use(
      http.put(`${GARAGE_URL}/*`, async ({ request }) => {
        await record(request)
        return HttpResponse.error()
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

/** A refusal a reply function returns instead of a body: the RFC 7807 answer with `status`. */
export class Refused {
  status: number
  body: ProblemBody
  constructor(status: number, body: ProblemBody = {}) {
    this.status = status
    this.body = body
  }
}

type AuthReply<Body, Out> =
  | Out
  | ((body: Body) => Out | Refused | Promise<Out | Refused>)

/**
 * A JSON answer that may be computed from the request and held in flight: the
 * request is recorded on arrival, before the reply is awaited. A function reply
 * may return `Refused` to answer with a problem instead.
 */
function authReply<Body, Out>(method: Method, path: string, reply: AuthReply<Body, Out>): void {
  server.use(
    http[method](AUTH_URL + path, async ({ request }) => {
      const body = (await record(request)) as Body
      const answer =
        typeof reply === 'function'
          ? await (reply as (b: Body) => Out | Refused | Promise<Out | Refused>)(body)
          : reply
      if (answer instanceof Refused) return problemResponse(answer.status, answer.body)
      return HttpResponse.json(answer as DefaultBodyType)
    }),
  )
}

export const auth = {
  /** `PATCH /users/me`; a promise reply holds the request in flight. */
  updateMe: (reply: AuthReply<{ displayName: string }, Profile>): void =>
    authReply('patch', '/api/v1/users/me', reply),
  /** `GET /users/me/preferences`; a function is asked on every request. */
  preferences: (reply: Preferences | (() => Preferences | Promise<Preferences>)): void =>
    authReply<undefined, Preferences>('get', '/api/v1/users/me/preferences', reply),
  /** `PATCH /users/me/preferences`; a promise reply holds it, `Refused` fails it. */
  updatePreferences: (reply: AuthReply<{ clock: Clock | null }, Preferences>): void =>
    authReply('patch', '/api/v1/users/me/preferences', reply),
  /**
   * `GET /users/me`, answered per call. `call` counts from 1 and restarts when this
   * is called again; a promise reply holds that read in flight.
   */
  meBy(reply: (call: number) => Profile | Promise<Profile>): void {
    let calls = 0
    authReply<undefined, Profile>('get', '/api/v1/users/me', () => reply(++calls))
  },
  /** The workspace directory `useWorkspaceMembers` reads, as one page. */
  members(members: WorkspaceMember[]): void {
    authJson('get', '/api/v1/workspaces/:workspaceId/members', { items: members, nextCursor: null })
  },
  /**
   * The directory, answered per call and per workspace. `call` counts from 1 for
   * each workspace, and restarts when this is called again. `reply` may return a
   * promise, which is how a test holds a fetch in flight: the request is recorded
   * on arrival, before the reply is awaited.
   */
  membersBy(
    reply: (workspaceId: string, call: number) => WorkspaceMember[] | Promise<WorkspaceMember[]>,
  ): void {
    const calls = new Map<string, number>()
    server.use(
      http.get(AUTH_URL + '/api/v1/workspaces/:workspaceId/members', async ({ request, params: raw }) => {
        await record(request)
        const workspaceId = String(raw.workspaceId)
        const call = (calls.get(workspaceId) ?? 0) + 1
        calls.set(workspaceId, call)
        const items = await reply(workspaceId, call)
        return HttpResponse.json({ items, nextCursor: null })
      }),
    )
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
