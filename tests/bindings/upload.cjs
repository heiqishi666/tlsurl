const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')
const [base, modulePath, directory] = process.argv.slice(2)
const { Client } = require(modulePath)
const file = path.join(directory, 'payload.bin')
const empty = path.join(directory, 'empty.bin')
const huge = path.join(directory, 'huge.bin')
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
async function waitState(id, predicate) {
  for (let i = 0; i < 150; i++) {
    const state = await (await fetch(`${base}/state?id=${id}`)).json()
    if (predicate(state)) return state
    await sleep(20)
  }
  throw new Error(`upload socket state did not converge: ${id}`)
}
async function main() {
  const client = new Client()
  const payload = fs.readFileSync(file)
  const result = (await client.post(`${base}/upload?id=node-file`, { bodyFile: file })).json()
  assert.equal(result.sha256, crypto.createHash('sha256').update(payload).digest('hex'))
  assert.equal(result.size, payload.length)
  assert.equal(Number(result.length), payload.length)
  assert.equal((await client.post(`${base}/upload?id=node-empty`, { bodyFile: empty })).json().size, 0)
  const multipart = (await client.post(`${base}/upload-multipart?id=node-multipart`, { multipart: [
    { name: 'note', data: 'hello' },
    { name: 'file', file, contentType: 'application/octet-stream' },
  ] })).json()
  const wire = Buffer.from(multipart.body, 'base64')
  assert(wire.includes(payload))
  assert(wire.includes(Buffer.from('name="note"\r\n\r\nhello')))
  assert(wire.includes(Buffer.from('filename="payload.bin"')))
  assert.equal(Number(multipart.length), wire.length)
  await assert.rejects(client.post(base + '/upload', { bodyFile: file + '.missing' }), { code: 'FILE_IO' })
  await assert.rejects(client.post(base + '/upload', { bodyFile: file, body: 'conflict' }), { code: 'INVALID_REQUEST' })
  await assert.rejects(client.post(base + '/upload', { bodyFile: file, headers: { 'Content-Length': '1' } }), { code: 'INVALID_REQUEST' })
  await assert.rejects(client.post(base + '/upload', { multipart: [{ name: 'bad', file, data: 'conflict' }] }), { code: 'INVALID_REQUEST' })
  assert.equal((await client.post(base + '/upload-redirect', { bodyFile: file })).status, 307)
  const controller = new AbortController()
  const baseline = process.memoryUsage().rss
  const pending = client.post(`${base}/upload-slow?id=node-upload-cancel`, { bodyFile: huge, signal: controller.signal })
  await waitState('node-upload-cancel', s => s?.received > 0)
  assert(process.memoryUsage().rss - baseline < 64 * 1024 * 1024, 'file was buffered in memory')
  controller.abort()
  await assert.rejects(pending, { code: 'CANCELLED' })
  const final = await waitState('node-upload-cancel', s => s?.closed)
  assert(final.received < fs.statSync(huge).size)
  client.close()
  console.log('Node raw/multipart file upload, hashes, framing, bounded memory and cancellation checks passed')
}
main().catch(error => { console.error(error); process.exitCode = 1 })
