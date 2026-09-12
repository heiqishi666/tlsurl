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
  tls?: TlsOptions
  http2?: Http2Options
  identity?: {certificatePem: string; privateKeyPem: string}
  profile?: string
  platform?: 'windows' | 'macos' | 'linux' | 'android' | 'ios'
  decompress?: boolean
}
export interface TlsOptions {
  minVersion?: '1.0' | '1.1' | '1.2' | '1.3'
  maxVersion?: '1.0' | '1.1' | '1.2' | '1.3'
  alpn?: ('h2' | 'http/1.1')[]
  cipherList?: string
  curvesList?: string
  sigalgsList?: string
  grease?: boolean
  permuteExtensions?: boolean
  sni?: boolean
}
export interface Http2Options {
  initialWindowSize?: number
  initialConnectionWindowSize?: number
  maxFrameSize?: number
  maxHeaderListSize?: number
  headerTableSize?: number
  enablePush?: boolean
  pseudoOrder?: ('method' | 'path' | 'authority' | 'scheme')[]
}
export interface Header { name: string; value: string | Uint8Array }
export type Pairs = [string, string][] | Record<string, string>
export interface MultipartPart {
  name: string
  data?: string | Uint8Array
  file?: string
  filename?: string
  contentType?: string
}
export interface RequestOptions {
  signal?: AbortSignal
  headers?: Header[] | Record<string, string | Uint8Array>
  body?: string | Uint8Array
  bodyFile?: string
  json?: unknown
  form?: Pairs
  params?: Pairs
  multipart?: MultipartPart[]
  timeoutMs?: number
  maxRedirects?: number
  basicAuth?: [string, string]
  bearerToken?: string
}
export class TlsurlError extends Error { readonly code: string }
export function availableProfiles(): string[]
export class Response {
  readonly status: number
  readonly httpVersion: string
  readonly url: string
  readonly headers: {name: string; value: Buffer}[]
  readonly body: Buffer
  text(encoding?: BufferEncoding): string
  json(): unknown
  raiseForStatus(): this
}
export class StreamResponse implements AsyncIterable<Buffer> {
  readonly status: number
  readonly httpVersion: string
  readonly url: string
  readonly headers: {name: string; value: Buffer}[]
  nextChunk(): Promise<Buffer | null>
  close(): void
  raiseForStatus(): this
  [Symbol.asyncIterator](): AsyncIterator<Buffer>
}
export interface WebSocketOptions {
  headers?: Header[] | Record<string, string | Uint8Array>
  protocols?: string[]
  timeoutMs?: number
  operationTimeoutMs?: number
  maxMessageBytes?: number
  signal?: AbortSignal
}
export interface WebSocketMessage {
  kind: 'text' | 'binary' | 'ping' | 'pong' | 'close'
  data: Buffer
  code?: number
}
export class WebSocket implements AsyncIterable<WebSocketMessage> {
  readonly protocol?: string
  send(data: string | Uint8Array): Promise<void>
  ping(data?: string | Uint8Array): Promise<void>
  pong(data?: string | Uint8Array): Promise<void>
  recv(): Promise<WebSocketMessage | null>
  close(code?: number, reason?: string): Promise<void>
  abort(): void
  [Symbol.asyncIterator](): AsyncIterator<WebSocketMessage>
}
export class Client {
  constructor(options?: ClientOptions)
  constructor(timeoutMs?: number, maxResponseBytes?: number)
  request(method: string, url: string, options?: RequestOptions): Promise<Response>
  request(method: string, url: string, headers?: Header[] | null, body?: Uint8Array): Promise<Response>
  websocket(url: string, options?: WebSocketOptions): Promise<WebSocket>
  stream(method: string, url: string, options?: RequestOptions): Promise<StreamResponse>
  get(url: string, options?: RequestOptions): Promise<Response>
  post(url: string, options?: RequestOptions): Promise<Response>
  clearCookies(): void
  setCookie(url: string, value: string): void
  cookies(url: string): {name: string; value: string}[]
  close(): void
}
declare const bindings: { Client: typeof Client; Response: typeof Response; StreamResponse: typeof StreamResponse; WebSocket: typeof WebSocket; TlsurlError: typeof TlsurlError; availableProfiles: typeof availableProfiles }
export default bindings
