import { Client, MultipartPart } from 'tlsurl'

new Client({ platform: 'not-a-platform' })
new Client({ tls: { minVersion: '9.9' } })
new Client().get('https://example.org', { timeotMs: 1 })
new Client().post('https://example.org', { bodyFile: 123 })
const missing: MultipartPart = { name: 'missing-source' }
const conflict: MultipartPart = { name: 'conflict', data: 'text', file: 'file.bin' }
void missing
void conflict
