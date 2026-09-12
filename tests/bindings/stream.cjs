const assert = require('node:assert/strict')
const [base, modulePath] = process.argv.slice(2)
const { Client } = require(modulePath)
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
async function state(id, predicate) {
  for (let i = 0; i < 100; i++) {
    const value = await (await fetch(`${base}/state?id=${id}`)).json()
    if (predicate(value)) return value
    await delay(20)
  }
  throw new Error(`server state did not converge: ${id}`)
}
async function main() {
  const client = new Client({ maxResponseBytes: 1024 })
  const response = await client.stream('GET', `${base}/stream?id=node-full`)
  assert.equal(response.status, 200)
  assert.equal(response.httpVersion, '1.1')
  assert(response.headers.some(h => h.name === 'x-stream' && h.value.toString() === 'yes'))
  let size = 0
  for await (const chunk of response) {
    for (let i = 0; i < chunk.length; i++) assert.equal(chunk[i], (size + i) % 256)
    size += chunk.length
  }
  assert.equal(size, 1048576)
  const hugeSize = 128 * 1024 * 1024
  const slow = await client.stream('GET', `${base}/stream?id=node-pull&size=${hugeSize}`)
  await slow.nextChunk()
  await delay(100)
  const progress = await state('node-pull', s => s?.produced > 0)
  assert(progress.produced < hugeSize, 'body was eagerly drained')
  slow.close()
  await state('node-pull', s => s?.closed)

  const broken = await client.stream('GET', `${base}/stream?id=node-break&size=${hugeSize}`)
  for await (const chunk of broken) { assert(chunk.length > 0); break }
  await state('node-break', s => s?.closed)
  const hold = await client.stream('GET', `${base}/hold?id=node-close`)
  const reading = hold.nextChunk()
  hold.close()
  await assert.rejects(reading, { code: 'CANCELLED' })
  await state('node-close', s => s?.closed)
  await assert.rejects(client.stream('GET', `${base}/hold?id=node-timeout`, { timeoutMs: 100 }).then(r => r.nextChunk()), { code: 'TIMEOUT' })

  for (let i = 0; i < 10; i++) {
    const id = `node-abort-${i}`
    const controller = new AbortController()
    const pending = client.get(`${base}/delayed?id=${id}`, { signal: controller.signal })
    await state(id, s => s !== null)
    controller.abort()
    await assert.rejects(pending, { code: 'CANCELLED' })
    await state(id, s => s?.closed)
  }
  const already = AbortSignal.abort()
  await assert.rejects(client.get(`${base}/delayed?id=node-preabort`, { signal: already }), { code: 'CANCELLED' })
  assert.equal(await (await fetch(`${base}/state?id=node-preabort`)).json(), null)
  const controller = new AbortController()
  const streaming = await client.stream('GET', `${base}/hold?id=node-streamabort`, { signal: controller.signal })
  const pending = streaming.nextChunk()
  controller.abort()
  await assert.rejects(pending, { code: 'CANCELLED' })
  await state('node-streamabort', s => s?.closed)
  client.close()
  await assert.rejects(client.stream('GET', base), { code: 'CLOSED' })
  console.log('Node pull streaming, early close, backpressure, timeout and transport abort checks passed')
}
main().catch(error => { console.error(error); process.exitCode = 1 })
