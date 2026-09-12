const assert = require('node:assert/strict')
const crypto = require('node:crypto')
const { pathToFileURL } = require('node:url')
const path = require('node:path')
const [base, modulePath, tlsBase, https] = process.argv.slice(2)
const { Client } = require(modulePath)

async function main() {
  const esm = await import(pathToFileURL(path.join(modulePath, 'index.mjs')))
  assert.equal(esm.Client, Client)
  assert.equal(crypto.randomBytes(8).length, 8)
  await assert.rejects(new Client().request('GET', tlsBase))
  const client = new Client()
  const payload = Buffer.from(Array.from({ length: 256 }, (_, i) => i))
  let response = await client.request('POST', base + '/echo', [], payload)
  assert.equal(response.status, 200)
  assert.deepEqual(response.body, payload)
  const mutable = Buffer.from('original')
  const pending = client.request('POST', base + '/echo', [], mutable)
  mutable.fill(0)
  assert.equal((await pending).body.toString(), 'original')
  assert.deepEqual(response.headers.filter(h => h.name === 'x-duplicate').map(h => h.value.toString()), ['one', 'two'])
  response = await client.request('GET', base + '/headers', [
    { name: 'X-Input', value: Buffer.from('one') },
    { name: 'X-Input', value: Buffer.from('two') },
  ])
  assert.deepEqual(JSON.parse(response.body), ['one', 'two'])
  response = await client.request('GET', base + '/header-names', [
    { name: 'X-Input', value: Buffer.from('one') },
    { name: 'x-InPut', value: Buffer.from('two') },
  ])
  assert.deepEqual(JSON.parse(response.body), ['X-Input', 'X-Input'])
  response = await client.request('GET', base + '/redirect')
  assert.equal(response.url, base + '/cookie')
  assert.equal(response.body.toString(), 'session=works')
  assert.equal((await client.request('GET', base + '/error')).status, 404)
  assert.throws(() => new Client(0), /INVALID_CONFIG/)
  for (const invalid of [-1, NaN, Infinity, 1.5, 2 ** 32]) {
    assert.throws(() => new Client(invalid), /INVALID_CONFIG/)
    assert.throws(() => new Client(30000, invalid), /INVALID_CONFIG/)
  }
  await assert.rejects(client.request('BAD METHOD', base), /INVALID_REQUEST/)
  await assert.rejects(new Client(30).request('GET', base + '/slow'), /TIMEOUT/)
  await assert.rejects(new Client(30000, 1024).request('GET', base + '/large'), /BODY_TOO_LARGE/)
  const responses = await Promise.all(Array.from({ length: 8 }, (_, i) => client.request('POST', base + '/echo', [], Buffer.from([i]))))
  assert.deepEqual(responses.map(r => r.body[0]), [0, 1, 2, 3, 4, 5, 6, 7])
  if (https) assert.equal((await client.request('GET', 'https://example.com')).status, 200)
  console.log('Node integration checks passed')
}

main().catch(error => { console.error(error); process.exitCode = 1 })
