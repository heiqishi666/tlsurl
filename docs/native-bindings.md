# tlsurl 原生绑定

基于上游 wreq 提交 `12ccf64bb00e79db6eabd4bc3ccf82871d3eb5a5`。
保留根 crate 名称和 API，新增共享核心及两种语言绑定。当前版本是开发预览，尚未发布到 PyPI/npm。

## 已实现的接口

- Python `Client.request()`、`AsyncClient.request()`；Node `Client.request()` 返回 Promise。
- 参数：HTTP method、URL、有序 Header 列表、可选二进制 Body。
- 返回：status、最终 URL、重复 Header 列表、二进制 Body。
- Client 复用连接池及 Cookie store；启用默认重定向和 TLS 证书校验。
- 默认总超时 30 秒、最大缓冲响应 16 MiB；配置均须为正整数。
- 不读取系统代理，通过 `proxy` 显式配置 HTTP/HTTPS/SOCKS 代理；目前本地测试覆盖 HTTP 正向代理。
- 支持查询参数追加、JSON、Form、Multipart、Basic/Bearer 认证、Cookie 读写及清空、请求级超时和重定向限制。
- HTTP 4xx/5xx 返回响应；Python `Error.code`、Node `TlsurlError.code` 提供网络错误分类；通过 `raise_for_status()` / `raiseForStatus()` 显式检查 HTTP 状态。
- Python 支持 asyncio 取消；Node 支持 AbortSignal。取消会中止对应传输，流式响应另提供 close。

流式读取、文件上传、WebSocket 与 Node AbortSignal 已实现，接口与生命周期见下文。首发范围与验收队列见 [交付规格](delivery-plan.md)。

```python
from tlsurl import Client, AsyncClient

response = Client().request("GET", "https://example.com")
print(response.status, response.body.decode("utf-8"))

# 在 asyncio 事件循环中：
# response = await AsyncClient().request("GET", "https://example.com")
```

```javascript
import { Client } from 'tlsurl'
const response = await new Client().request('GET', 'https://example.com')
console.log(response.status, response.body.toString('utf8'))
```

响应 Header 的 value 在 Python 中是 bytes，在 Node 中是 Buffer，避免有损文本转换。请求 Header 同样使用 bytes/Buffer。
HTTP/1 请求保留自定义 Header 名称大小写；上游会将同名重复字段分组，并采用首次出现的名称拼写，不能保证同名字段分别使用不同大小写或任意交错顺序。响应名称采用上游解析后的形式。
缓冲响应可以反复访问 body；流式响应使用独立对象和一次消费语义。

## 基础请求与配置

```python
with Client(connect_timeout_ms=5000, max_redirects=5, user_agent="my-app/1.0") as client:
    response = client.post("https://example.com/api", params=[("page", "1")], json={"name": "demo"})
    response.raise_for_status()
    data = response.json()
    client.set_cookie("https://example.com", "session=value; Path=/; Secure")
    selected = client.cookies("https://example.com/api")
    client.clear_cookies()
```

```javascript
const client = new Client({ connectTimeoutMs: 5000, maxRedirects: 5, userAgent: 'my-app/1.0' })
try {
  const response = await client.post('https://example.com/upload', {
    multipart: [
      { name: 'title', data: 'demo' },
      { name: 'file', filename: 'data.bin', contentType: 'application/octet-stream', data: Buffer.from([0, 1, 2]) },
    ],
  })
  response.raiseForStatus()
} finally {
  client.close()
}
```

Python Multipart 字段使用 `name/data/file/filename/content_type`，Node 使用 `name/data/file/filename/contentType`；data 与 file 二选一，file 是磁盘路径，默认 filename 取文件名。上传编码由 Rust 生成。`body/body_file/json/form/multipart` 互斥（Node 使用 bodyFile）；参数支持重复键，追加而不覆盖 URL 已有查询。params 和 form 使用字符串键值对。

客户端配置为 Python `connect_timeout_ms/read_timeout_ms/proxy/verify/ca_pem/max_redirects/cookies/user_agent/http_version`；Node 对应 camelCase。`http_version` 为 `auto/1.1/2`。`ca_pem` 是 PEM 内容，替换默认信任库；`verify=False` 仅在显式配置时关闭证书校验。重定向上限 0 表示不跟随。

请求配置为 Python `params/json/form/multipart/basic_auth/bearer_token/timeout_ms/max_redirects`；Node 对应 camelCase。认证选项互斥，也不允许与显式 Authorization Header 混用。响应 `text()` 默认 UTF-8，`json()` 解析失败保留语言原生 JSON 异常。

Cookie 按上游域、路径、Secure 和过期规则接受与选择；`set_cookie` 不绕过这些规则，例如从 HTTP 来源写入 Secure Cookie 会被忽略。`cookies=False` 禁止自动收发存储 Cookie，但显式 Cookie Header 仍由调用者控制。

`close()` 释放客户端持有的连接池引用并拒绝新请求；已经提交的请求可继续完成。Python 支持 `with Client()` / `async with AsyncClient()`。单独请求可通过 Python asyncio 取消或 Node AbortSignal 中止；流式响应拥有独立 close。

## TLS / HTTP 配置

Python 客户端接受 `tls={...}`、`http2={...}`、`identity={...}`；Node 接受对应对象，字段使用 camelCase。响应 `http_version` / `httpVersion` 表示实际收到的 HTTP 协议版本。

| 配置 | Python 字段 | 含义 |
| --- | --- | --- |
| tls | min_version / max_version | 显式 TLS 版本界限，支持 1.0～1.3，最小值不得超过最大值 |
| tls | alpn | 有序 `h2` / `http/1.1` 列表；不支持 HTTP/3 |
| tls | cipher_list / curves_list / sigalgs_list | BoringSSL 格式的密码套件、曲线、签名算法列表 |
| tls | grease / permute_extensions / sni | GREASE、扩展随机排列、SNI 开关 |
| http2 | initial_window_size / initial_connection_window_size | 流和连接窗口，按协议范围检查 |
| http2 | max_frame_size / max_header_list_size / header_table_size | 帧、Header 列表及 HPACK 表参数 |
| http2 | enable_push / pseudo_order | 服务端推送与伪 Header 顺序；后者必须恰好包含 method/path/authority/scheme |
| identity | certificate_pem / private_key_pem | mTLS 客户端证书链与 PKCS#8 PEM 私钥内容 |

强制 `http_version="1.1"/"2"` 优先于 ALPN 列表。仅在明确指定时改变 TLS 选项；这里提供可验证的协议配置，不将任意配置宣称为真实浏览器指纹。

```python
client = Client(
    ca_pem=ca_text,
    tls={"min_version": "1.2", "max_version": "1.3", "alpn": ["h2", "http/1.1"]},
    http2={"initial_window_size": 1048576, "pseudo_order": ["method", "path", "authority", "scheme"]},
    identity={"certificate_pem": client_certificate, "private_key_pem": client_private_key},
)
```

`tests/bindings/protocol.py` 通过本地 Node TLS/HTTP2 服务验证信任库、主机名拒绝、协议版本、ALPN、指定密码套件、mTLS、HTTP/2 SETTINGS 和伪 Header 实际顺序。测试证书仅供本地测试，不能部署到真实服务或导入系统信任库。

## 浏览器预设与解压

预设来自锁定的 [wreq-util 3.0.0-rc.14](https://github.com/0x676e67/wreq-util/tree/v3.0.0-rc.14)，该发布包声明 Apache-2.0，依赖 wreq 6.0.0-rc 系列。通过 Cargo patch 复用本项目的 wreq 核心，避免额外链接另一份客户端。

Python `available_profiles()` / Node `availableProfiles()` 返回实际编译的 133 个预设名称，例如 `chrome_149`、`firefox_151`、`safari_26.4`。`Client(profile="chrome_149", platform="windows")` 对应 Node `new Client({profile: 'chrome_149', platform: 'windows'})`。platform 可取 windows/macos/linux/android/ios，影响预设 Header；省略时使用上游默认 macos，与运行机器的系统无关。

预设先应用，随后显式 TLS/HTTP2 字段逐项覆盖，未指定字段保留预设值；请求提供 Header 顺序时覆盖默认顺序。配置修改后不再承诺与原预设完全相同。测试覆盖三个代表性浏览器的真实 TLS/HTTP2 连接，以及 Chrome UA、HTTP2 表大小和覆盖规则；未逐一对照真实浏览器的全部指纹。

默认启用 gzip、deflate、Brotli、Zstd 自动解压，缓冲大小限制作用于解压后的字节。`decompress=False` / `{decompress: false}` 可保留压缩响应字节；若同时使用带 Accept-Encoding 的预设，服务端仍可能发送压缩响应，调用者须自行处理。

## 流式响应与取消

`Client.stream(method, url, ...)` 返回独立的 StreamResponse，读取响应头后即可返回，不先缓冲完整正文。请求配置与普通 request 一致。流式读取不使用 max_response_bytes 总量限制；下载到内存时，调用者应自行限制累计大小。请求超时仍覆盖正文读取，解压选项同样生效。

Python 同步：

```python
with Client() as client:
    with client.stream("GET", url) as response:
        response.raise_for_status()
        with open("download.bin", "wb") as output:
            for chunk in response:
                output.write(chunk)
```

Python 异步：

```python
async with AsyncClient() as client:
    async with await client.stream("GET", url) as response:
        async for chunk in response:
            await consume(chunk)
```

也可使用 `next_chunk()` / `await next_chunk_async()`；EOF 返回 None。asyncio Task 取消会释放底层请求；取消正在等待的 next_chunk_async 会同时关闭该响应。同步读取可由另一个线程调用 response.close() 中断。需要提前退出 Python 循环时使用上述上下文管理，不依赖生成器垃圾回收的时机。

Node：

```javascript
const controller = new AbortController()
const response = await client.stream('GET', url, { signal: controller.signal })
try {
  response.raiseForStatus()
  for await (const chunk of response) await consume(chunk)
} finally {
  response.close()
}
```

也可调用 `await response.nextChunk()`，EOF 返回 null。for-await 循环正常结束、break 或异常退出时自动关闭响应。AbortSignal 可用于普通请求和流式请求，在响应头到达前后均可中止；已经 abort 的 signal 不发送请求。监听器在完成/关闭后移除，取消返回 `CANCELLED`。

response.close() 幂等，唤醒等待中的读取并释放正文；关闭后的读取返回 CANCELLED。EOF 前的并发读取会串行执行，但应用应使用一个消费者以保持处理顺序。Rust 核心按调用拉取数据，没有持续读取正文的应用层后台队列；HTTP/TLS/内核仍有正常协议缓冲。用户自己累计 chunk 或保留未关闭的响应仍会占用内存/连接。

`tests/bindings/stream.py` 验证完整二进制流、超过缓冲上限的流式下载、128 MiB 响应暂停消费后的背压、提前关闭/取消后的服务端连接关闭、正文超时及重复取消。文件上传与 WebSocket 见后续章节。

## 文件流式上传

Python `client.post(url, body_file=path)`，Node `client.post(url, {bodyFile: path})` 直接上传文件。Multipart 使用 `{name: "attachment", file: path}`，可以与 data 字段混合；filename 省略时取文件名，content_type/contentType 可显式指定。Python 接受字符串或 PathLike 路径，Node 接受字符串路径。

Rust 异步打开文件，按下游需要读取，每次最多 64 KiB；语言层不先读取完整文件。文件须为普通文件，调用者应在上传期间保持内容不变。长度取自打开的文件，追加的内容不会超出声明长度。原始文件和 Multipart 文件的 Content-Length/Transfer-Encoding 由核心管理，不接受手动覆盖。缺失或不可访问文件返回 FILE_IO。

文件正文不可重放：当前收到需要保留正文的 307/308 重定向时返回该响应，不自动重新打开/上传文件；调用者可检查目标后显式发起新请求。取消会释放请求与文件读取资源，语义与前一节一致。任意 Python/Node 生成器上传尚未开放。

`tests/bindings/upload.py` 验证实包上传的字节数与 SHA-256、空文件、混合 Multipart、冲突配置、缺失文件、307 行为和 128 MiB 文件取消。Node 用例还检查上传开始后的 RSS 增量小于 64 MiB，防止退化为整文件缓冲；这不是所有业务负载的内存上限承诺。

## WebSocket

Python `Client.websocket(url, ...)` 返回同步 WebSocket；`await AsyncClient.websocket(url, ...)` 返回 AsyncWebSocket。Node 使用 `await client.websocket(url, options)`。仅接受 ws/wss，当前使用 HTTP/1.1 Upgrade；TLS 信任、代理、Cookie 和客户端预设复用同一 Rust 客户端，不宣称已验证 HTTP/2 Extended CONNECT。

连接选项：headers、protocols、timeout_ms/timeoutMs（握手超时）、operation_timeout_ms/operationTimeoutMs（每次收发及关闭握手超时，默认 30000）、max_message_bytes/maxMessageBytes（收发消息上限，默认 16 MiB）。Node 还接受 signal，连接前后均可取消。

`send(str)` 发送文本，`send(bytes/Uint8Array)` 发送二进制。`recv()` 返回含 kind、data、code 的消息：kind 为 text/binary/ping/pong/close，data 始终为原始字节，code 仅用于关闭消息。Python 使用 `message.data.decode()`，Node 使用 `message.data.toString()` 读取文本。protocol 属性为协商结果。异步连接的 send/recv/ping/pong/close 均须 await。

```python
async with AsyncClient() as client:
    async with await client.websocket("wss://example.org/socket", protocols=["chat"]) as socket:
        await socket.send("hello")
        message = await socket.recv()
```

```javascript
const socket = await client.websocket('wss://example.org/socket', {protocols: ['chat']})
try {
  await socket.send('hello')
  const message = await socket.recv()
} finally {
  await socket.close()
}
```

接收与发送独立串行化，可以先等待 recv 再从同一连接发送，不会因读锁阻塞发送。一次只应安排一个消息消费者。Python 支持同步/异步迭代，Node 支持 for-await；提前退出 Python 迭代时配合上下文管理保证及时关闭。

ping/pong 控制负载最多 125 字节；接收到 Ping 会立即刷新自动 Pong。close(code=1000, reason="") 发起并等待关闭握手，在操作超时内完成或报 TIMEOUT，并释放连接；reason 最多 123 个 UTF-8 字节。关闭会中断等待中的 recv，返回 CLOSED。收到远端 Close 后返回带关闭码的最后消息并释放连接。

abort() 立即释放连接，等待中的操作返回 CANCELLED。Python asyncio 取消收发会 abort；Node 使用建立连接时传入的 AbortSignal。关闭 Client 不强制关闭已交出的 WebSocket，调用者拥有该连接，必须通过上下文管理、close 或 abort 释放。

`tests/bindings/websocket.py` 使用固定版本的 [ws 测试服务](https://github.com/websockets/ws)（仅测试依赖，不进入分发包），验证 WS/WSS、自定义 CA、Cookie/子协议、文本/二进制/分片、双向收发、Ping/Pong、关闭握手、大小限制、超时及取消。运行前执行 `npm ci --prefix tests/bindings --ignore-scripts --omit=optional`。

## 构建

构建机需要 Rust 1.94.0、Python、Node 24、CMake、Perl、libclang；Windows 另需 MSVC、Windows SDK、NASM。
Windows 构建输出目录必须使用 ASCII 路径，避免 NASM 无法读取中文路径。
SDK、工具链只属于构建机依赖，用户安装工件不需要这些工具。

```text
python -m pip install maturin==1.15.0 libclang==18.1.1 ninja==1.13.2
python scripts/build_native.py
```

Linux 必须在 manylinux_2_28 容器中运行，不能直接将新版 Ubuntu 的产物标成 manylinux。
macOS 原生扩展部署目标为 11.0，但 Node 24 本身要求至少 macOS 13.5；构建目标和运行时要求见 [平台支持与审计](platform-support.md)。
Cargo.lock 和 npm package-lock.json 随仓库提交，构建使用锁文件。

工件位于 `dist/wheels` 与 `dist/npm`。主 npm tarball 只包含加载器、类型声明和许可证，通过固定版本的 optionalDependencies 引用五个平台包；各平台包单独携带原生二进制。发行 manifest 在打包暂存目录中生成，开发环境安装不会尝试下载尚未发布的平台包。

工作流汇总五个平台的输出，检查主包内容一致、平台包齐全、版本一致、二进制存在以及 wheel 不重复，再生成 `native-release` 工件和 `SHA256SUMS`。这个工件包含五个 wheel、五个平台 npm tarball、一个 npm 主包及五份与包哈希绑定的平台审计报告。

## 验证与发布边界

Native packages 工作流覆盖 Linux x64/ARM64、Windows x64、macOS Intel/ARM64。
每个作业构建、安装 wheel 和 npm tarball，再运行同一组协议测试；当前测试运行时为 CPython 3.13、Node 24。
`abi3-py310` 是编译目标，不等于 Python 3.10～3.14 全版本验收已经完成。
兼容性作业复用上述工件，在五个平台分别安装 CPython 3.10、3.11、3.12、3.13、3.14，每组再用 Node 22 和 24 验证安装与调用，共 25 个作业、50 组运行时组合。这里指常规 GIL 版 CPython，不包括 free-threaded Python、PyPy 或未列出的系统架构。

测试使用独立本地 registry 和空 npm 缓存安装主包，提供全部五个平台包，断言只安装一个匹配的平台包，并验证 CommonJS 与 ESM 包入口；安装关闭生命周期脚本，wheel 使用 `--no-index --only-binary=:all:`。这些作业不安装 Rust 工具链、不执行编译，但宿主 runner 可能预装编译器，不能当作严格无编译器系统的验证。

完整版本矩阵的结果以对应提交的 GitHub Actions 状态为准；正式发布前仍需最低系统版本及动态库依赖审计、发布账号与 Trusted Publishing 配置。

```text
python tests/bindings/smoke.py --node-module dist/consumer/node_modules/tlsurl
```

加 `--https` 会访问 example.com，验证公开 HTTPS 以及与 Python ssl / Node crypto 共存；其结果依赖网络。
离线用例覆盖二进制回显、重复 Header、Cookie/重定向、HTTP 错误响应、并发、超时和响应大小限制。
同时验证本地不可信 TLS 证书被拒绝，以及 Node Buffer 在调用后修改不影响已提交的请求。

### 2026-09-13 本地验证

- Windows x64、CPython 3.13.0、Node 24.9.0：release wheel 和 npm tarball 构建、安装、联调通过。
- 联调时 PATH 只保留系统目录及 Node 启动器，未暴露 Rust/MSVC；Python 从独立消费虚拟环境加载 wheel，Node 从独立消费目录加载 npm tarball。
- 三个新增 crate 的 `cargo clippy --locked -- -D warnings` 通过；Native packages 工作流通过 actionlint 检查。
- Windows 动态依赖检查：Python 扩展依赖 python3.dll、系统 DLL 与 VC Runtime；Node 扩展依赖系统 DLL 与 VC Runtime，均未依赖外部 libssl/libcrypto DLL。消费机器仍须满足 Python/Node 本身及 VC Runtime 的要求。
- 随后提交 `f80c2806` 的五平台 CI 已全部通过，包含 Linux/macOS 实际构建、CPython 3.13/Node 24 安装与协议测试：[运行记录](https://github.com/heiqishi666/tlsurl/actions/runs/34705604255)。后续基础请求与 TLS 配置批次分别通过完整 31 作业矩阵：[基础请求](https://github.com/heiqishi666/tlsurl/actions/runs/34708937263)、[TLS 配置](https://github.com/heiqishi666/tlsurl/actions/runs/34709361700)。浏览器预设与流式批次以各自新运行记录为准。
- 上游 dev-dependency `sysinfo 0.39.x` 声明 Rust 1.95；本轮未改动上游依赖，也未用 Rust 1.94 宣称全仓 `cargo test --workspace` 通过。绑定构建不依赖该 benchmark 依赖。

工作流只生成 GitHub Actions 工件，不上传 PyPI/npm。正式发布时必须先上传所有平台 npm 包，核验可下载后再上传主包，避免用户安装时缺少对应的可选依赖。聚合包的安装前提是保留 optionalDependencies，不能使用 `--omit=optional`。
上游自带 CI/发布流程尚未改造，不要推送版本标签触发原 wreq 发布任务。

原代码及协议来自 wreq/reqwest；所有分发包保留 Apache-2.0 LICENSE。
