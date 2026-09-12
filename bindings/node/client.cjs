'use strict'
const native = require('./index.js')

class TlsurlError extends Error {
  constructor(code, message) {
    super(`${code}: ${message}`)
    this.name = 'TlsurlError'
    this.code = code
  }
}
function convertError(error) {
  if (error instanceof TlsurlError) return error
  const match = /^([A-Z_]+): (.*)$/s.exec(error.message)
  return new TlsurlError(match ? match[1] : 'REQUEST', match ? match[2] : error.message)
}
class Response {
  constructor(value) { Object.assign(this, value) }
  text(encoding = 'utf8') { return this.body.toString(encoding) }
  json() { return JSON.parse(this.text()) }
  raiseForStatus() {
    if (this.status >= 400 && this.status < 600) throw new TlsurlError('HTTP_STATUS', `HTTP status ${this.status}`)
    return this
  }
}
class StreamResponse {
  constructor(value, cleanup) {
    this._native = value
    this._cleanup = cleanup
    this.status = value.status
    this.httpVersion = value.httpVersion
    this.url = value.url
    this.headers = value.headers
  }
  raiseForStatus() { return Response.prototype.raiseForStatus.call(this) }
  async nextChunk() {
    try {
      const chunk = await this._native.nextChunk()
      if (chunk == null) this._cleanup()
      return chunk
    } catch (error) { this.close(); throw convertError(error) }
  }
  close() { this._native.close(); this._cleanup() }
  async *[Symbol.asyncIterator]() {
    try {
      for (;;) {
        const chunk = await this.nextChunk()
        if (chunk == null) return
        yield chunk
      }
    } finally { this.close() }
  }
}
const clientKeys = {
  connectTimeoutMs: 'connect_timeout_ms', readTimeoutMs: 'read_timeout_ms',
  proxy: 'proxy', verify: 'verify', caPem: 'ca_pem', maxRedirects: 'max_redirects',
  cookies: 'cookies', userAgent: 'user_agent', httpVersion: 'http_version',
  tls: 'tls', http2: 'http2', identity: 'identity',
  profile: 'profile', platform: 'platform', decompress: 'decompress',
}
const requestKeys = {
  timeoutMs: 'timeout_ms', maxRedirects: 'max_redirects',
  basicAuth: 'basic_auth', bearerToken: 'bearer_token',
}
const nestedKeys = {
  tls: { minVersion: 'min_version', maxVersion: 'max_version', alpn: 'alpn', cipherList: 'cipher_list', curvesList: 'curves_list', sigalgsList: 'sigalgs_list', grease: 'grease', permuteExtensions: 'permute_extensions', sni: 'sni' },
  http2: { initialWindowSize: 'initial_window_size', initialConnectionWindowSize: 'initial_connection_window_size', maxFrameSize: 'max_frame_size', maxHeaderListSize: 'max_header_list_size', headerTableSize: 'header_table_size', enablePush: 'enable_push', pseudoOrder: 'pseudo_order' },
  identity: { certificatePem: 'certificate_pem', privateKeyPem: 'private_key_pem' },
}
function pairs(value) { return Array.isArray(value) ? value : Object.entries(value) }
function optionsJson(options, keys) {
  const result = {}
  for (const [name, value] of Object.entries(options)) {
    if (value === undefined) continue
    if (!Object.hasOwn(keys, name)) throw new TlsurlError('INVALID_CONFIG', `unknown option: ${name}`)
    if (typeof value === 'number' && !Number.isFinite(value)) throw new TlsurlError('INVALID_CONFIG', `${name} must be finite`)
    result[keys[name]] = Object.hasOwn(nestedKeys, name) && value != null ? optionsJson(value, nestedKeys[name]) : value
  }
  return result
}
class Client {
  constructor(timeoutMs = 30000, maxResponseBytes = 16777216) {
    let options = {}
    if (typeof timeoutMs === 'object' && timeoutMs !== null) {
      const { timeoutMs: timeout = 30000, maxResponseBytes: limit = 16777216, ...rest } = timeoutMs
      timeoutMs = timeout
      maxResponseBytes = limit
      options = rest
    }
    try {
      this._native = new native.Client(timeoutMs, maxResponseBytes, JSON.stringify(optionsJson(options, clientKeys)))
    } catch (error) { throw convertError(error) }
  }
  request(method, url, headersOrOptions = [], legacyBody) {
    return this._send(false, method, url, headersOrOptions, legacyBody)
  }
  stream(method, url, options = {}) { return this._send(true, method, url, options) }
  async _send(streaming, method, url, headersOrOptions, legacyBody) {
    if (!this._native) throw new TlsurlError('CLOSED', 'client is closed')
    const options = Array.isArray(headersOrOptions) || headersOrOptions == null
      ? { headers: headersOrOptions || [], body: legacyBody } : headersOrOptions
    const { headers = [], body: rawBody, json, form, multipart, bodyFile, params, signal, ...rest } = options
    const hasJson = Object.hasOwn(options, 'json')
    if ([rawBody !== undefined && rawBody !== null, hasJson, form !== undefined && form !== null, multipart != null, bodyFile != null].filter(Boolean).length > 1) {
      throw new TlsurlError('INVALID_REQUEST', 'body, json, form, multipart and bodyFile are mutually exclusive')
    }
    const normalized = (Array.isArray(headers) ? headers : Object.entries(headers).map(([name, value]) => ({ name, value })))
      .map(({ name, value }) => ({ name, value: Buffer.from(value) }))
    let body = rawBody == null ? undefined : Buffer.from(rawBody)
    let contentType
    if (hasJson) {
      body = Buffer.from(JSON.stringify(json))
      contentType = 'application/json'
    } else if (form != null) {
      body = Buffer.from(new URLSearchParams(pairs(form)).toString())
      contentType = 'application/x-www-form-urlencoded'
    }
    if (contentType && !normalized.some(h => h.name.toLowerCase() === 'content-type')) normalized.push({ name: 'Content-Type', value: Buffer.from(contentType) })
    const requestOptions = optionsJson(rest, requestKeys)
    if (params != null) requestOptions.params = pairs(params)
    if (bodyFile != null) requestOptions.body_file = bodyFile
    if (multipart != null) {
      const chunks = []
      let offset = 0
      requestOptions.multipart = multipart.map(part => {
        if (Object.keys(part).some(key => !['name', 'data', 'file', 'filename', 'contentType'].includes(key))) throw new TlsurlError('INVALID_REQUEST', 'unknown multipart field')
        if ((part.data != null) === (part.file != null)) throw new TlsurlError('INVALID_REQUEST', 'multipart requires exactly one of data or file')
        if (part.file != null) return { name: part.name, file: part.file, filename: part.filename, content_type: part.contentType }
        const chunk = Buffer.from(part.data)
        const descriptor = { name: part.name, offset, length: chunk.length, filename: part.filename, content_type: part.contentType }
        offset += chunk.length
        chunks.push(chunk)
        return descriptor
      })
      body = Buffer.concat(chunks)
    }
    if (signal != null && !(signal instanceof AbortSignal)) throw new TlsurlError('INVALID_CONFIG', 'signal must be an AbortSignal')
    const cancellation = new native.Cancellation()
    let streamRef
    const abort = () => { cancellation.cancel(); streamRef?.deref()?.close() }
    const cleanup = () => signal?.removeEventListener('abort', abort)
    signal?.addEventListener('abort', abort, { once: true })
    if (signal?.aborted) abort()
    try {
      const result = await this._native[streaming ? 'stream' : 'request'](method, url, normalized, body, JSON.stringify(requestOptions), cancellation)
      if (signal?.aborted) {
        if (streaming) result.close()
        throw new TlsurlError('CANCELLED', 'operation cancelled')
      }
      if (streaming) {
        streamRef = new WeakRef(result)
        return new StreamResponse(result, cleanup)
      }
      cleanup()
      return new Response(result)
    } catch (error) { cleanup(); throw convertError(error) }
  }
  get(url, options) { return this.request('GET', url, options) }
  post(url, options) { return this.request('POST', url, options) }
  setCookie(url, value) {
    if (!this._native) throw new TlsurlError('CLOSED', 'client is closed')
    try { this._native.setCookie(url, value) } catch (error) { throw convertError(error) }
  }
  cookies(url) {
    if (!this._native) throw new TlsurlError('CLOSED', 'client is closed')
    try { return this._native.cookies(url) } catch (error) { throw convertError(error) }
  }
  clearCookies() {
    if (!this._native) throw new TlsurlError('CLOSED', 'client is closed')
    this._native.clearCookies()
  }
  close() { this._native = null }
}
module.exports = { Client, Response, StreamResponse, TlsurlError, availableProfiles: native.availableProfiles }
