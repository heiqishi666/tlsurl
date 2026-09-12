/// <reference types="node" />
export interface ClientOptions {
  timeoutMs?: number
  maxResponseBytes?: number
  connectTimeoutMs?: number
  readTimeoutMs?: number
  proxy?: string
  verify?: boolean
  caPem?: string
  maxRedirects?: number
  cookies?: boolean
  userAgent?: string
  httpVersion?: 'auto' | '1.1' | '2'
}
export interface Header { name: string; value: string | Uint8Array }
export type Pairs = [string, string][] | Record<string, string>
export interface RequestOptions {
  headers?: Header[] | Record<string, string | Uint8Array>
  body?: string | Uint8Array
  json?: unknown
  form?: Pairs
  params?: Pairs
  timeoutMs?: number
  maxRedirects?: number
  basicAuth?: [string, string]
  bearerToken?: string
}
export class TlsurlError extends Error { readonly code: string }
export class Response {
  readonly status: number
  readonly url: string
  readonly headers: {name: string; value: Buffer}[]
  readonly body: Buffer
  text(encoding?: BufferEncoding): string
  json(): unknown
  raiseForStatus(): this
}
export class Client {
  constructor(options?: ClientOptions)
  constructor(timeoutMs?: number, maxResponseBytes?: number)
  request(method: string, url: string, options?: RequestOptions): Promise<Response>
  request(method: string, url: string, headers?: Header[] | null, body?: Uint8Array): Promise<Response>
  get(url: string, options?: RequestOptions): Promise<Response>
  post(url: string, options?: RequestOptions): Promise<Response>
  clearCookies(): void
  close(): void
}
declare const bindings: { Client: typeof Client; Response: typeof Response; TlsurlError: typeof TlsurlError }
export default bindings
