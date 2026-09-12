const http = require('node:http')
const states = new Map()
const block = Buffer.from(Array.from({ length: 32768 }, (_, i) => i % 256))
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost')
  const id = url.searchParams.get('id')
  if (url.pathname === '/state') {
    res.end(JSON.stringify(states.get(id) || null))
    return
  }
  const state = { produced: 0, closed: false, finished: false }
  states.set(id, state)
  res.on('close', () => { state.closed = true })
  if (url.pathname === '/delayed') {
    const timer = setTimeout(() => res.end('late'), 10000)
    res.on('close', () => clearTimeout(timer))
    return
  }
  res.writeHead(200, { 'Content-Type': 'application/octet-stream', 'X-Stream': 'yes' })
  res.flushHeaders()
  if (url.pathname === '/hold') return
  const size = Number(url.searchParams.get('size') || 1048576)
  function write() {
    while (state.produced < size && !res.destroyed) {
      const chunk = block.subarray(0, Math.min(block.length, size - state.produced))
      state.produced += chunk.length
      if (!res.write(chunk)) { res.once('drain', write); return }
    }
    if (!res.destroyed) { state.finished = true; res.end() }
  }
  write()
})
server.listen(0, '127.0.0.1', () => console.log(JSON.stringify({ port: server.address().port })))
