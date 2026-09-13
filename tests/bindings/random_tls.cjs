const assert = require('node:assert/strict')
const { Client } = require(process.argv[2])
const urls = JSON.parse(process.argv[3])
const caPem = process.argv[4]
async function main() {
  for (let seed = 0; seed < 16; seed++) {
    const client = new Client({ randomTls: true, randomTlsSeed: seed, caPem })
    try {
      for (const url of urls) assert.equal((await client.get(url)).status, 200)
      assert.equal((await client.get(process.argv[5])).json().tlsVersion, 'TLSv1.2')
    } finally { client.close() }
  }
  for (const options of [
    { randomTls: true, tls: {} }, { randomTls: true, profile: 'chrome_149' },
    { randomTlsSeed: 1 }, { randomTls: true, randomTlsSeed: -1 },
    { randomTls: true, randomTlsSeed: 2 ** 32 }, { randomTls: true, randomTlsSeed: 0.5 },
    { randomTls: true, randomTlsSeed: true }, { randomTls: 1 },
  ]) assert.throws(() => new Client(options), error => error.code === 'INVALID_CONFIG')
}
main().catch(error => { console.error(error); process.exitCode = 1 })
