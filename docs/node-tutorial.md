# Node.js 使用教程

适用于 `tlsurl 0.1.0`，Node.js 22/24。当前 npm 官方主包尚未上传；使用 Release 的 `.tgz` 工件，或从 GitHub Packages 安装。

[文档索引](README.md) · [返回项目首页](../README.md) · [Python 教程](python-tutorial.md) · [完整 API](native-bindings.md)

## 章节目录

1. [安装与运行方式](#install)
2. [简单请求](#simple)
3. [Header 与参数](#headers-params)
4. [复杂请求](#complex)
5. [表单与正文](#body)
6. [连续请求](#session)
7. [Cookie（CK）](#cookies)
8. [引用自带的浏览器指纹](#profiles)
9. [自定义 TLS 指纹](#custom-tls)
10. [随机 TLS 指纹（JA3/JA4）](#random-tls)
11. [并发请求](#concurrency)
12. [文件上传与流式下载](#files)
13. [错误、超时与取消](#errors)
14. [代理与自定义 CA](#proxy)

<a id="install"></a>

## 安装与运行方式

推荐从 [v0.1.0 Release](https://github.com/knight-bili/tlsurl/releases/tag/v0.1.0) 下载主包和对应平台包，再按下方命令安装。也可按 [GitHub Packages 说明](github-packages.md) 使用 `npm install tlsurl@npm:@knight-bili/tlsurl@0.1.0`，保持本教程的 `import ... from 'tlsurl'` 不变。

以下仓库 bin 链接保留历史离线工件：

从 [bin/node/0.1.0](../bin/node/0.1.0) 下载主包 `tlsurl-0.1.0.tgz` 和匹配的平台包，放进自己的 Node 项目 `artifacts/` 目录。例如 Windows x64：

```shell
npm install --ignore-scripts ./artifacts/tlsurl-win32-x64-msvc-0.1.0.tgz ./artifacts/tlsurl-0.1.0.tgz
```

其他平台的文件名见 [首页平台包表](../README.md#安装-nodejs-预编译包)。主包、平台包同版本，保留 optionalDependencies，不要使用 `--omit=optional`。不需要 npm 账号或本地 Rust 编译器。

**下面每个 JavaScript 示例均可单独保存为 `demo.mjs`，执行 `node demo.mjs`**。这样可直接使用 `import` 和顶层 `await`。CommonJS 的 `.cjs` 使用 `const { Client } = require('tlsurl')`，并将含 await 的代码放入 `async function main()`，最后 `main().catch(console.error)`。

请求示例使用公开 HTTP 回显服务 `https://httpbin.org`；实际业务请替换 URL、凭据和字段。示例服务的可用性不属于 tlsurl 的保证。上传示例需准备文件，代理示例需已有代理服务。

<a id="simple"></a>

## 简单请求

```javascript
import { Client } from 'tlsurl'

const client = new Client()
try {
  const response = await client.get('https://httpbin.org/get')
  response.raiseForStatus()
  console.log(response.status)
  console.log(response.url)          // 重定向后的最终 URL
  console.log(response.httpVersion)  // 实际 HTTP 版本
  console.log(response.json())       // 同步解析已缓冲的 JSON
  console.log(response.text())       // 默认 UTF-8
  console.log(response.body.length)  // Buffer 长度
} finally {
  client.close()
}
```

网络方法返回 Promise，必须 `await`；`response.json()` / `text()` 为同步方法。HTML/图片不要调用 `json()`，二进制内容直接使用 `body`。同一缓冲正文可以反复访问。

只有 `get()`、`post()` 提供快捷方法，其他方法调用 `request()`：

```javascript
import { Client } from 'tlsurl'

const client = new Client()
try {
  const response = await client.request('PATCH', 'https://httpbin.org/anything', { json: { enabled: true } })
  response.raiseForStatus()
  console.log(response.json())
} finally {
  client.close()
}
```

<a id="headers-params"></a>

## Header 与参数

Header 一般使用对象；同名重复字段使用 `{name, value}` 数组。`params` 是 URL 查询参数，键和值使用字符串。

```javascript
import { Client } from 'tlsurl'

const commonHeaders = { 'User-Agent': 'my-node-app/1.0', Accept: 'application/json' }
const client = new Client()
try {
  const response = await client.get('https://httpbin.org/get?source=tutorial', {
    headers: { ...commonHeaders, 'X-Request-Id': 'demo-001', Referer: 'https://example.com/' },
    params: [['q', '中文 空格'], ['page', '1'], ['tag', 'node'], ['tag', 'tls']],
  })
  response.raiseForStatus()
  console.log(response.json())
  for (const { name, value } of response.headers) console.log(name, value.toString('latin1'))

  const repeated = await client.get('https://httpbin.org/headers', {
    headers: [
      { name: 'Accept', value: 'application/json' },
      { name: 'X-Demo', value: 'one' },
      { name: 'X-Demo', value: 'two' },
    ],
  })
  repeated.raiseForStatus()
  console.log(repeated.json())
} finally {
  client.close()
}
```

简单查询也可写 `params: { page: '1', size: '20' }`；重复键使用二元数组。参数自动编码，并追加到 URL 而不是覆盖已有同名参数。

请求 Header 值支持字符串或 Uint8Array/Buffer；响应值为 Buffer。不要把 Python 的 Header 元组列表照搬成 Node 的数组，Node 需要 `{name, value}` 对象。HTTP/2 会规范化 Header 名称，不能靠列表保证任意线上字节顺序。

`new Client({headers: ...})` 不是当前 API。复用 `commonHeaders`，每次请求合并自己的 Header；默认 UA 可使用 `new Client({userAgent: 'my-app/1.0'})` 设置。

<a id="complex"></a>

## 复杂请求

```javascript
import { Client } from 'tlsurl'

const client = new Client({ timeoutMs: 15000, connectTimeoutMs: 5000, maxRedirects: 5 })
try {
  const response = await client.post('https://httpbin.org/post', {
    params: { source: 'desktop', page: '1' },
    headers: { Accept: 'application/json', 'X-Trace-Id': 'demo-002' },
    json: { name: '测试', items: [{ id: 1, enabled: true }] },
    bearerToken: 'demo-token', // 替换为自己的业务 Token
    timeoutMs: 10000,         // 此请求覆盖客户端总超时
    maxRedirects: 0,          // 此请求不跟随重定向
  })
  response.raiseForStatus()
  console.log(response.json())
} finally {
  client.close()
}
```

`json` 自动序列化并在未指定时添加 `Content-Type: application/json`。Basic 认证使用 `basicAuth: ['username', 'password']`；Basic、Bearer、显式 Authorization Header 三选一。库不自动申请或刷新 access token。

<a id="body"></a>

## 表单与正文

```javascript
import { Client } from 'tlsurl'

const client = new Client()
try {
  const formResponse = await client.post('https://httpbin.org/post', {
    form: [['name', 'demo'], ['tag', 'a'], ['tag', 'b']],
  })
  formResponse.raiseForStatus()
  console.log(formResponse.json())

  const rawResponse = await client.post('https://httpbin.org/post', {
    headers: { 'Content-Type': 'application/octet-stream' },
    body: Buffer.from([0, 1, 2, 104, 105]),
  })
  rawResponse.raiseForStatus()
  console.log(rawResponse.json())
} finally {
  client.close()
}
```

`form` 为 URL 编码表单，支持对象或字符串键值对数组。`body` 为原始字符串/字节。**`json`、`form`、`body`、`bodyFile`、`multipart` 每次只能选一个**，它们均可与 params 同用。Multipart 不要手写 boundary。

<a id="session"></a>

## 连续请求

```javascript
import { Client } from 'tlsurl'

const client = new Client()
try {
  const first = await client.get('https://httpbin.org/cookies/set', { params: { session: 'demo-session' } })
  first.raiseForStatus()
  const second = await client.get('https://httpbin.org/cookies')
  second.raiseForStatus()
  console.log(second.json())

  for (let page = 1; page <= 3; page++) {
    const response = await client.get('https://httpbin.org/get', { params: { page: String(page) } })
    response.raiseForStatus()
    console.log(page, response.status)
  }
} finally {
  client.close()
}
```

真实登录时把第一步换为登录接口，继续复用同一个 Client 即可保留服务端 Cookie 和连接池。JSON 返回的 token 需要自己读取并传入 `bearerToken`；不同账号使用不同 Client。循环中每次 `await` 表示顺序执行；不要用没有等待结果的 `forEach(async ...)` 来管理整个会话生命周期。

<a id="cookies"></a>

## Cookie（CK）

自动 Cookie 默认开启，服务端 Set-Cookie 会进入客户端存储。手工写入时每次传**一条 Set-Cookie 格式**的值：

```javascript
import { Client } from 'tlsurl'

const url = 'https://httpbin.org/cookies'
const client = new Client()
try {
  client.setCookie(url, 'session=demo-session; Path=/; Secure; HttpOnly')
  client.setCookie(url, 'theme=dark; Path=/; Secure')
  console.log(client.cookies(url)) // [{name, value}, ...]，只返回与此 URL 匹配的项
  const response = await client.get(url)
  response.raiseForStatus()
  console.log(response.json())
  client.setCookie(url, 'theme=; Max-Age=0; Path=/; Secure')
  client.clearCookies()
} finally {
  client.close()
}
```

浏览器复制出的原始 Cookie 字符串应放进请求头：

```javascript
import { Client } from 'tlsurl'

const client = new Client({ cookies: false })
try {
  const response = await client.get('https://httpbin.org/cookies', {
    headers: { Cookie: 'session=demo-session; theme=dark' },
  })
  response.raiseForStatus()
  console.log(response.json())
} finally {
  client.close()
}
```

Cookie Header 不带 Path/Domain/Secure 等属性，也不会自动导入 Cookie 存储。示例关闭自动 Cookie，避免两种来源混用。存储仍遵守域、路径、Secure 和过期规则；HTTP 来源不能写入 Secure Cookie。不要将真实登录 Cookie 留在日志里。

<a id="profiles"></a>

## 引用自带的浏览器指纹

```javascript
import { Client, availableProfiles } from 'tlsurl'

console.log(availableProfiles()) // 以安装包实际返回名称为准
const client = new Client({ profile: 'chrome_149', platform: 'windows' })
try {
  const response = await client.get('https://httpbin.org/get')
  response.raiseForStatus()
  console.log(response.status, response.httpVersion)
} finally {
  client.close()
}
```

还可选择 `firefox_151`、`safari_26.4` 等已编译预设。`platform` 支持 windows/macos/linux/android/ios，影响预设 Header，不是本机平台包选择；省略时上游默认 macos。

预设同时包含 TLS、HTTP/2、Header 设置，不等同于只换 User-Agent，也不执行网页 JavaScript。可以按字段覆盖预设：

```javascript
import { Client } from 'tlsurl'

const client = new Client({
  profile: 'chrome_149',
  platform: 'windows',
  tls: { maxVersion: '1.2' },
  http2: { initialWindowSize: 1048576 },
})
try {
  const response = await client.get('https://httpbin.org/get')
  response.raiseForStatus()
  console.log(response.status)
} finally {
  client.close()
}
```

只有显式字段覆盖，未指定字段保留预设；覆盖后不能认为指纹仍与原预设完全相同。

<a id="custom-tls"></a>

## 自定义 TLS 指纹

```javascript
import { Client } from 'tlsurl'

const client = new Client({ tls: {
  minVersion: '1.2',
  maxVersion: '1.3',
  alpn: ['h2', 'http/1.1'],
  cipherList: 'ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES128-GCM-SHA256',
  curvesList: 'X25519:P-256:P-384',
  sigalgsList: 'ecdsa_secp256r1_sha256:rsa_pss_rsae_sha256:rsa_pkcs1_sha256',
  grease: true,
  permuteExtensions: false,
  sni: true,
} })
try {
  const response = await client.get('https://httpbin.org/get')
  response.raiseForStatus()
  console.log(response.status, response.httpVersion)
} finally {
  client.close()
}
```

套件、曲线、签名算法使用 BoringSSL 格式；TLS 1.3 套件仍受底层默认规则影响，不能把 cipherList 当作完整 ClientHello。ALPN 只支持 h2/http/1.1，显式 `httpVersion: '1.1'` 或 `'2'` 优先。

没有 `ja3: '哈希'`、`ja4: '哈希'` 这样的设置项。JA3/JA4 是实际握手的摘要，不能从任意哈希直接还原握手。自定义组合可能影响服务器兼容性，证书校验应保持开启。

<a id="random-tls"></a>

## 随机 TLS 指纹（JA3/JA4）

```javascript
import { Client } from 'tlsurl'

const client = new Client({ randomTls: true })
try {
  const response = await client.get('https://httpbin.org/get')
  response.raiseForStatus()
  console.log(response.status)
} finally {
  client.close()
}
```

同一会话保留随机配置，用种子复现：

```javascript
import { Client } from 'tlsurl'

const client = new Client({ randomTls: true, randomTlsSeed: 42 })
try {
  for (const page of ['1', '2']) {
    const response = await client.get('https://httpbin.org/get', { params: { page } })
    response.raiseForStatus()
    console.log(response.status)
  }
} finally {
  client.close()
}
```

如果需要每次重新随机，显式创建新的无种子客户端：

```javascript
import { Client } from 'tlsurl'

for (let i = 0; i < 3; i++) {
  const client = new Client({ randomTls: true })
  try {
    const response = await client.get('https://httpbin.org/get')
    response.raiseForStatus()
    console.log(response.status)
  } finally {
    client.close()
  }
}
```

随机配置**每个 Client 生成一次**。新建客户端会失去原 Cookie 与连接池，连续登录会话优先复用同一客户端。随机模式限制 TLS 1.2/1.3，改变实际 JA3/JA4 相关配置，并非随机打印哈希。

种子为 `0..4294967295` 的整数，必须配合 `randomTls: true`。同版本、相同 SNI/ALPN 条件下复现配置，不参与 TLS 密钥生成。不同种子可能碰撞，升级底层库后不保证指纹不变。

**随机模式与 `tls`、`profile`、`platform` 互斥**；Header、Cookie、CA、代理、超时和 HTTP/2 参数仍可单独配置。仅打乱扩展顺序不保证改变 JA4，随机配置不等同于真实浏览器。

<a id="concurrency"></a>

## 并发请求

独立请求可以并发；下面一次仅发三个请求，等待全部结果后关闭 Client：

```javascript
import { Client } from 'tlsurl'

const client = new Client({ randomTls: true })
try {
  const results = await Promise.allSettled(
    ['1', '2', '3'].map(page => client.get('https://httpbin.org/get', { params: { page } })),
  )
  for (const result of results) {
    if (result.status === 'rejected') console.error(result.reason)
    else {
      result.value.raiseForStatus()
      console.log(result.value.status)
    }
  }
} finally {
  client.close()
}
```

大量 URL 应分批控制并发，登录与刷新令牌等有依赖的步骤保持顺序。并发请求共享同一客户端的 Cookie。`Promise.allSettled` 等待所有请求结束，避免第一项失败就提前退出等待。

<a id="files"></a>

## 文件上传与流式下载

先准备当前目录的 `demo.txt`：

```javascript
import { Client } from 'tlsurl'

const client = new Client()
try {
  const response = await client.post('https://httpbin.org/post', { multipart: [
    { name: 'title', data: 'demo' },
    { name: 'attachment', file: 'demo.txt', filename: 'demo.txt', contentType: 'text/plain' },
  ] })
  response.raiseForStatus()
  console.log(response.status)
} finally {
  client.close()
}
```

原始文件使用 `{bodyFile: 'demo.txt'}`，不能与 multipart 同传。文件由原生层按需读取，勿手写 Content-Length/Transfer-Encoding。文件上传遇到需要保留正文的 307/308 时不自动重传，由调用者检查后处理。

流式下载写入当前目录的 `download.bin`：

```javascript
import { open } from 'node:fs/promises'
import { Client } from 'tlsurl'

const client = new Client()
try {
  const response = await client.stream('GET', 'https://httpbin.org/bytes/1024')
  try {
    response.raiseForStatus()
    const output = await open('download.bin', 'w')
    try {
      for await (const chunk of response) {
        let offset = 0
        while (offset < chunk.length) {
          const { bytesWritten } = await output.write(chunk, offset, chunk.length - offset)
          if (bytesWritten === 0) throw new Error('文件写入未取得进展')
          offset += bytesWritten
        }
      }
    } finally { await output.close() }
  } finally { response.close() }
} finally { client.close() }
```

默认缓冲上限 16 MiB；流式下载不使用这个累计上限，业务应自行限制下载量。流式迭代支持背压，结束、break 或异常后仍应妥善关闭文件和响应。WebSocket 见 [API 文档](native-bindings.md#websocket)。

<a id="errors"></a>

## 错误、超时与取消

```javascript
import { Client, TlsurlError } from 'tlsurl'

const client = new Client({ timeoutMs: 10000, connectTimeoutMs: 3000, readTimeoutMs: 5000 })
try {
  const response = await client.get('https://httpbin.org/status/404')
  response.raiseForStatus() // 不调用时 404/500 也正常返回 Response
} catch (error) {
  if (error instanceof TlsurlError) console.error(error.code, error.message)
  else throw error
} finally {
  client.close()
}
```

超时单位为毫秒、正整数，请求 timeoutMs 覆盖客户端总超时。常见错误码：HTTP_STATUS、TIMEOUT、TLS、DNS、CONNECT、INVALID_CONFIG、INVALID_REQUEST、FILE_IO、BODY_TOO_LARGE、CANCELLED、CLOSED。JSON 解析异常是原生 SyntaxError。库不自动重试业务请求，尤其不要盲目重试有副作用的 POST。

主动取消请求使用 AbortSignal：

```javascript
import { Client } from 'tlsurl'

const client = new Client()
const controller = new AbortController()
const timer = setTimeout(() => controller.abort(), 1000)
try {
  const response = await client.get('https://httpbin.org/delay/3', { signal: controller.signal })
  console.log(response.status)
} catch (error) {
  if (error.code === 'CANCELLED') console.log('请求已取消')
  else throw error
} finally {
  clearTimeout(timer)
  client.close()
}
```

关闭客户端会拒绝新请求；已经提交的请求仍可继续，取消单次传输应使用 AbortSignal，不能把 `client.close()` 当作取消全部请求。

<a id="proxy"></a>

## 代理与自定义 CA

已有本地代理时，把端口换为自己的代理服务：

```javascript
import { Client } from 'tlsurl'

const client = new Client({ proxy: 'http://127.0.0.1:7890', timeoutMs: 10000 })
try {
  const response = await client.get('https://httpbin.org/get')
  response.raiseForStatus()
  console.log(response.status)
} finally {
  client.close()
}
```

默认不读取系统代理。自定义 CA 使用 `caPem: readFileSync('ca.pem', 'utf8')`（先从 `node:fs` 导入 readFileSync），传内容而不是文件路径；它替换默认信任库。证书校验默认开启。
