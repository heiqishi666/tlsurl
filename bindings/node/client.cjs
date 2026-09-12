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
const clientKeys = {
  connectTimeoutMs: 'connect_timeout_ms', readTimeoutMs: 'read_timeout_ms',
  proxy: 'proxy', verify: 'verify', caPem: 'ca_pem', maxRedirects: 'max_redirects',
  cookies: 'cookies', userAgent: 'user_agent', httpVersion: 'http_version',
}
const requestKeys = {
  timeoutMs: 'timeout_ms', maxRedirects: 'max_redirects',
  basicAuth: 'basic_auth', bearerToken: 'bearer_token',
}
function pairs(value) { return Array.isArray(value) ? value : Object.entries(value) }
function optionsJson(options, keys) {
  const result = {}
  for (const [name, value] of Object.entries(options)) {
    if (value === undefined) continue
    if (!Object.hasOwn(keys, name)) throw new TlsurlError('INVALID_CONFIG', `unknown option: ${name}`)
    if (typeof value === 'number' && !Number.isFinite(value)) throw new TlsurlError('INVALID_CONFIG', `${name} must be finite`)
    result[keys[name]] = value
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
  async request(method, url, headersOrOptions = [], legacyBody) {
    if (!this._native) throw new TlsurlError('CLOSED', 'client is closed')
    const options = Array.isArray(headersOrOptions) || headersOrOptions == null
      ? { headers: headersOrOptions || [], body: legacyBody } : headersOrOptions
    const { headers = [], body: rawBody, json, form, params, ...rest } = options
    const hasJson = Object.hasOwn(options, 'json')
    if ([rawBody !== undefined && rawBody !== null, hasJson, form !== undefined && form !== null].filter(Boolean).length > 1) {
      throw new TlsurlError('INVALID_REQUEST', 'body, json and form are mutually exclusive')
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
    try {
      return new Response(await this._native.request(method, url, normalized, body, JSON.stringify(requestOptions)))
    } catch (error) { throw convertError(error) }
  }
  get(url, options) { return this.request('GET', url, options) }
  post(url, options) { return this.request('POST', url, options) }
  clearCookies() {
    if (!this._native) throw new TlsurlError('CLOSED', 'client is closed')
    this._native.clearCookies()
  }
  close() { this._native = null }
}
module.exports = { Client, Response, TlsurlError }
