const http = require('node:http')
const https = require('node:https')
const fs = require('node:fs')
const path = require('node:path')
const { WebSocketServer } = require('ws')
const states = new Map()
function handler(req, res) {
  const url = new URL(req.url, 'http://localhost')
  res.end(JSON.stringify(states.get(url.searchParams.get('id')) || null))
}
const plain = http.createServer(handler)
const secure = https.createServer({
  cert: fs.readFileSync(path.join(__dirname, 'certs/server.pem')),
  key: fs.readFileSync(path.join(__dirname, 'certs/server-key.pem')),
}, handler)
secure.on('tlsClientError', () => {})
const websocket = new WebSocketServer({ noServer: true })
for (const server of [plain, secure]) {
  server.on('upgrade', (req, socket, head) => {
    const url = new URL(req.url, 'http://localhost')
    const state = { closed: false, code: null, reason: '', pongs: 0 }
    states.set(url.searchParams.get('id'), state)
    socket.on('error', () => {})
    socket.on('close', () => { state.closed = true })
    if (url.pathname === '/hang') {
      // An upgraded HTTP socket may remain half-open after peer FIN.
      socket.on('end', () => { state.peerEnded = true; socket.end() })
      socket.resume()
      return
    }
    if (url.pathname === '/reject') {
      socket.end('HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n')
      return
    }
    websocket.handleUpgrade(req, socket, head, ws => {
      ws.on('error', () => {})
      ws.on('close', (code, reason) => { state.code = code; state.reason = reason.toString() })
      ws.on('pong', data => { if (data.toString() === 'probe') state.pongs++ })
      if (url.pathname === '/headers') ws.send(JSON.stringify(req.headers))
      ws.on('message', (data, binary) => {
        const text = binary ? '' : data.toString()
        if (text === 'server-close') ws.close(4001, 'bye')
        else if (text === 'server-ping') ws.ping('probe')
        else if (text === 'large') ws.send(Buffer.alloc(2048))
        else if (text === 'fragment') { ws.send('first', { fin: false }); ws.send('second', { fin: true }) }
        else ws.send(data, { binary })
      })
    })
  })
}
plain.listen(0, '127.0.0.1', () => secure.listen(0, '127.0.0.1', () => {
  console.log(JSON.stringify({ port: plain.address().port, tlsPort: secure.address().port }))
}))
