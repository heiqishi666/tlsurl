const assert = require('node:assert/strict')
const fs = require('node:fs')
const [base, modulePath, secondsText, output] = process.argv.slice(2)
const { Client } = require(modulePath)
const seconds = Number(secondsText)
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
const expected = Buffer.from(Array.from({ length: 1024 }, (_, i) => i % 256))
async function main() {
  const initialServer = await (await fetch(base + '/metrics')).json()
  const client = new Client()
  let requests = 0, streams = 0, cancellations = 0, rounds = 0
  async function batch() {
    await Promise.all(Array.from({ length: 16 }, async () => {
      assert.deepEqual((await client.get(base + '/stream?size=1024&id=stress-node')).body, expected)
      requests++
    }))
    const response = await client.stream('GET', base + '/stream?size=65536&id=stress-node-stream')
    let bytes = 0
    for await (const chunk of response) bytes += chunk.length
    assert.equal(bytes, 65536)
    streams++
    if (++rounds % 10 === 0) {
      const controller = new AbortController()
      const response = await client.stream('GET', base + '/hold?id=stress-node-cancel', { signal: controller.signal })
      const pending = response.nextChunk()
      controller.abort()
      await assert.rejects(pending, { code: 'CANCELLED' })
      cancellations++
    }
  }
  for (let i = 0; i < 5; i++) await batch()
  global.gc?.()
  const baseline = process.memoryUsage().rss
  let peak = baseline
  const start = performance.now()
  let nextLog = start + 30000
  const initial = { requests, streams, cancellations }
  while (performance.now() - start < seconds * 1000) {
    await batch()
    peak = Math.max(peak, process.memoryUsage().rss)
    if (performance.now() >= nextLog) {
      console.log(JSON.stringify({ language: 'node', elapsedSeconds: Math.round((performance.now() - start) / 1000), requests: requests - initial.requests, rssBytes: process.memoryUsage().rss, errors: 0 }))
      nextLog += 30000
    }
  }
  const active = await (await fetch(base + '/metrics')).json()
  assert(active.connections - initialServer.connections < requests / 2, 'connection pool was not reused')
  client.close()
  let final
  for (let i = 0; i < 100; i++) {
    final = await (await fetch(base + '/metrics')).json()
    if (final.activeConnections <= 2) break
    await sleep(50)
  }
  assert(final.activeConnections <= 2, `connections retained after close: ${JSON.stringify(final)}`)
  global.gc?.()
  peak = Math.max(peak, process.memoryUsage().rss)
  assert(peak - baseline < 128 * 1024 * 1024, `excessive RSS growth: ${peak - baseline}`)
  const report = { language: 'node', runtime: process.version, elapsedSeconds: (performance.now() - start) / 1000,
    requests: requests - initial.requests, streams: streams - initial.streams, cancellations: cancellations - initial.cancellations,
    errors: 0, baselineRssBytes: baseline, peakRssBytes: peak, finalRssBytes: process.memoryUsage().rss, server: final }
  fs.writeFileSync(output, JSON.stringify(report, null, 2) + '\n')
  console.log(JSON.stringify(report))
}
main().catch(error => { console.error(error); process.exitCode = 1 })
