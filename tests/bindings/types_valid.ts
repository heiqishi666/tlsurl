import { Client, Response, StreamResponse, WebSocket, MultipartPart } from 'tlsurl'

async function consumer(url: string): Promise<void> {
  const client = new Client({ tls: { minVersion: '1.2' }, platform: 'windows' })
  const part: MultipartPart = { name: 'file', file: 'payload.bin' }
  const response: Response = await client.post(url, { multipart: [part], timeoutMs: 500 })
  response.raiseForStatus().json()
  const stream: StreamResponse = await client.stream('GET', url, { signal: new AbortController().signal })
  for await (const chunk of stream) chunk.toString()
  const socket: WebSocket = await client.websocket(url, { protocols: ['echo'] })
  try { await socket.send('hello'); await socket.recv() } finally { await socket.close() }
  client.close()
}
void consumer
