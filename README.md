# tlsurl

[![Native packages](https://github.com/heiqishi666/tlsurl/actions/workflows/native-packages.yml/badge.svg)](https://github.com/heiqishi666/tlsurl/actions/workflows/native-packages.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

**支持自定义 TLS 指纹与一键随机 JA3 / JA4 的 Rust HTTP 客户端，提供 Python 和 Node.js 跨平台预编译包。**

tlsurl 基于 [wreq](https://github.com/penumbra-x/rquest) 的协议实现，通过共享 Rust 核心提供 Python 同步/异步接口与 Node.js Promise 接口。可以发送常规 HTTP 请求，也可以配置 TLS、HTTP/2 和浏览器预设，处理流式下载、文件上传及 WebSocket 通信。

项目目标是让使用者安装对应平台的工件即可调用，无需自行编译 Rust 或 BoringSSL。协议能力集中在核心实现，两种语言保留各自常用的调用方式。

> 当前为开发预览。**Python 0.1.0 已发布到 [PyPI](https://pypi.org/project/tlsurl/0.1.0/)**；npm 尚未发布，Node.js 请使用 GitHub Actions 工件，不要将 `npm install tlsurl` 当作当前可用入口。发布配置见[发布说明](docs/publishing.md)。

## 功能

- **请求与会话**：GET/POST 等 HTTP 方法、查询参数、JSON、Form、Multipart、重复 Header、Basic/Bearer 认证、Cookie 管理、重定向和显式代理。
- **自定义 TLS 指纹**：配置密码套件、曲线、签名算法、ALPN、GREASE 与扩展排列；支持一键随机配置和种子复现。
- **TLS 与 HTTP/2**：证书校验、自定义 CA、mTLS、TLS 版本、ALPN、密码套件、曲线与 HTTP/2 参数配置。
- **浏览器预设**：使用 wreq-util 提供的 Chrome、Firefox、Safari 等预设，可查询实际可用名称并覆盖配置。
- **流式传输**：按需读取响应、流式文件上传、背压、超时和主动取消。
- **WebSocket**：文本与二进制消息、双向通信、关闭握手和取消。
- **语言支持**：Python 同步/asyncio API 和类型声明；Node.js Promise、AbortSignal、CommonJS/ES modules 与 TypeScript 类型。
- **预编译分发**：Python wheel；npm 主包自动选择对应平台的原生包。CI 检查安装、协议行为、二进制依赖、版本和工件哈希。

浏览器预设用于配置协议行为，不保证与真实浏览器所有行为完全一致，也不保证任意服务端都接受请求。

## 一键随机 TLS 指纹

Python：

```python
from tlsurl import Client

with Client(random_tls=True) as client:
    response = client.get("https://example.com")
    print(response.status)
```

Node.js：

```javascript
import { Client } from 'tlsurl'

const client = new Client({ randomTls: true })
try {
  console.log((await client.get('https://example.com')).status)
} finally {
  client.close()
}
```

需要复现某组配置时，使用 Python `Client(random_tls=True, random_tls_seed=42)` 或 Node.js `new Client({ randomTls: true, randomTlsSeed: 42 })`。种子范围为 `0`～`4294967295`，只能与随机模式一起使用。

- **每个 Client 生成一次配置**，连接池复用不会重新生成；需要换一组配置就新建 Client。未传种子时使用系统随机源。
- 随机选择现代密码套件组合，并排列套件、曲线与签名算法；同时改变影响 JA3 和 JA4 的字段。保留 TLS 1.2/1.3、RSA/ECDSA 兼容套件和证书校验。
- 随机模式与 `tls`、`profile`、`platform` 互斥，混用会报 `INVALID_CONFIG`。可以继续设置代理、CA、HTTP/2 参数、超时等。
- 同版本、同种子、同 SNI/ALPN 条件下可复现指纹配置；TLS 密钥和握手随机数仍由 TLS 库安全生成。不同种子可能出现相同指纹，不保证全局唯一；升级底层 TLS 库后也不保证指纹不变。

[JA3](https://github.com/salesforce/ja3) 和 [JA4](https://github.com/FoxIO-LLC/ja4/blob/main/technical_details/JA4.md) 是服务端从 ClientHello 计算出的摘要。这里改变的是实际握手参数，不能将任意 JA3/JA4 哈希字符串直接指定为握手结果。JA4 会对密码套件和扩展排序，因此仅打乱扩展顺序并不足以改变 JA4。随机配置不等同于真实浏览器预设，也不保证服务端接受。

## 手工自定义 TLS 指纹

需要精确控制时，直接指定握手参数：

```python
from tlsurl import Client

with Client(tls={
    "min_version": "1.2",
    "max_version": "1.3",
    "alpn": ["h2", "http/1.1"],
    "cipher_list": "ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES128-GCM-SHA256",
    "curves_list": "X25519:P-256:P-384",
    "sigalgs_list": "ecdsa_secp256r1_sha256:rsa_pss_rsae_sha256:rsa_pkcs1_sha256",
    "grease": True,
    "permute_extensions": True,
}) as client:
    print(client.get("https://example.com").status)
```

Node.js 使用 `new Client({ tls: { ... } })`，对应字段为 `minVersion`、`maxVersion`、`alpn`、`cipherList`、`curvesList`、`sigalgsList`、`grease`、`permuteExtensions`。列表字符串使用 BoringSSL 格式；TLS 1.3 密码套件还有底层默认规则，不能把配置字符串当作完整 ClientHello。完整字段及优先级见 [TLS / HTTP 配置](docs/native-bindings.md#tls--http-配置)。

想以浏览器配置为基础，可以使用 `profile="chrome_149"`，再通过 `tls` / `http2` 覆盖所需字段；未覆盖字段保留预设值。

## 支持平台

| 系统 | 架构 | 工件 |
| --- | --- | --- |
| Linux（glibc ≥ 2.28） | x64、ARM64 | manylinux wheel、GNU npm 原生包 |
| Windows | x64 | wheel、MSVC npm 原生包 |
| macOS | Intel、Apple Silicon | wheel、对应架构 npm 原生包 |

当前完整 CI 覆盖常规 **CPython 3.10–3.14** 和 **Node.js 22/24**。macOS 扩展的构建部署目标为 11.0，但 Node.js 24 本身要求至少 macOS 13.5；最终运行要求还受 Python/Node.js 发行版本影响。Windows 可能需要 VC Runtime。

尚未提供 Alpine/musl、Windows ARM64、32 位、移动系统、PyPy 或 free-threaded Python 工件。上述构建与版本矩阵不等于最低系统版本和所有旧 CPU 都经过实机测试，详情见[平台支持](docs/platform-support.md)。

## 从 PyPI 安装 Python 包

```shell
python -m pip install --only-binary=:all: --index-url https://pypi.org/simple tlsurl==0.1.0
```

安装后可直接使用上面的 Python 示例，无需编译 Rust。`--only-binary=:all:` 确保只安装预编译 wheel；若当前系统没有匹配工件，会直接报错。支持范围见上方平台表。

## 下载 GitHub 工件（Node.js / Python 离线安装）

### 1. 下载

在 [Native packages 工作流](https://github.com/heiqishi666/tlsurl/actions/workflows/native-packages.yml)中选择**全部作业成功**的运行，下载 `native-release` artifact，并解压到 `artifacts/`。

其中包含五个 wheel、五个平台 npm 包、一个 npm 主包、五份平台审计报告及 `SHA256SUMS`。下载 Actions artifact 通常需要登录 GitHub；也可通过已登录的 GitHub CLI 下载：

```sh
# 将 RUN_ID 替换为所选成功运行的编号
gh run download RUN_ID --repo heiqishi666/tlsurl --name native-release --dir artifacts
```

### 2. Python

建议先创建虚拟环境，再让 pip 从本地目录选择匹配的 wheel：

```sh
python -m venv .venv
# 激活环境：Windows PowerShell 使用 .\.venv\Scripts\Activate.ps1；macOS/Linux 使用 source .venv/bin/activate
python -m pip install --no-index --only-binary=:all: --find-links ./artifacts tlsurl==0.1.0
```

### 3. Node.js

在你的 Node.js 项目中，同时安装主包和**一个与当前系统匹配的平台包**。例如 Windows x64：

```sh
npm install --ignore-scripts --registry=https://registry.npmjs.org ./artifacts/tlsurl-win32-x64-msvc-0.1.0.tgz ./artifacts/tlsurl-0.1.0.tgz
```

其他平台替换上面的平台包文件名：

| 平台 | 平台包文件名 |
| --- | --- |
| Linux x64 | `tlsurl-linux-x64-gnu-0.1.0.tgz` |
| Linux ARM64 | `tlsurl-linux-arm64-gnu-0.1.0.tgz` |
| macOS Intel | `tlsurl-darwin-x64-0.1.0.tgz` |
| macOS Apple Silicon | `tlsurl-darwin-arm64-0.1.0.tgz` |

主包和平台包必须使用相同版本；如果下载的版本不同，请同步替换上述版本号。保留 npm optionalDependencies，不要使用 `--omit=optional`。

## Python 快速开始

### 同步请求

```python
from tlsurl import Client

with Client(timeout_ms=10000) as client:
    response = client.get("https://example.com", params=[("source", "tlsurl")])
    response.raise_for_status()
    print(response.status, response.http_version)
    print(response.text())
```

### asyncio 请求

```python
import asyncio
from tlsurl import AsyncClient

async def main():
    async with AsyncClient(timeout_ms=10000) as client:
        response = await client.get("https://example.com")
        response.raise_for_status()
        print(response.text())

asyncio.run(main())
```

发送 JSON 使用 `client.post(url, json={"name": "demo"})`，解析 JSON 响应使用 `response.json()`。非 JSON 响应会产生语言原生的解析异常。

## Node.js 快速开始

将以下内容保存为 `example.mjs`，运行 `node example.mjs`：

```javascript
import { Client } from 'tlsurl'

const client = new Client({ timeoutMs: 10000 })
try {
  const response = await client.get('https://example.com', {
    params: [['source', 'tlsurl']],
  })
  response.raiseForStatus()
  console.log(response.status, response.httpVersion)
  console.log(response.text())
} finally {
  client.close()
}
```

CommonJS 可使用 `const { Client } = require('tlsurl')`。发送 JSON 使用 `client.post(url, { json: { name: 'demo' } })`。

## 浏览器预设

```python
from tlsurl import Client, available_profiles

print(available_profiles())
with Client(profile="chrome_149", platform="windows") as client:
    response = client.get("https://example.com")
    print(response.status)
```

Node.js 对应 `availableProfiles()` 和 `new Client({ profile: 'chrome_149', platform: 'windows' })`。这里的 `platform` 控制预设 Header，不是选择安装包架构；省略时采用上游默认 macos，与运行机器的系统无关。

## 流式下载与取消

Python 使用上下文管理器确保提前退出时释放响应：

```python
from tlsurl import Client

with Client() as client:
    with client.stream("GET", "https://example.com") as response:
        response.raise_for_status()
        with open("page.html", "wb") as output:
            for chunk in response:
                output.write(chunk)
```

Node.js 请求接受 `AbortSignal`：

```javascript
import { Client } from 'tlsurl'

const client = new Client()
const controller = new AbortController()
const timer = setTimeout(() => controller.abort(), 5000)
try {
  const response = await client.get('https://example.com', { signal: controller.signal })
  console.log(response.status)
} catch (error) {
  console.error(error.code, error.message)
} finally {
  clearTimeout(timer)
  client.close()
}
```

文件上传使用 Python `body_file=path` / Node.js `bodyFile: path`，Multipart 文件项使用 `{name, file}`。流式迭代、异步下载和 WebSocket 完整示例见[API 文档](docs/native-bindings.md)。

## 默认行为

- TLS 证书校验默认开启；系统代理不会自动启用，代理必须显式指定。
- 默认请求总超时 30 秒，缓冲响应上限 16 MiB；流式响应不受该累计大小上限约束，应用应按需要自行限制。
- HTTP 4xx/5xx 正常返回响应；需要时调用 `raise_for_status()` / `raiseForStatus()`。
- 重用 Client 可以复用连接池和 Cookie；用完显式关闭。关闭后拒绝新请求，已提交的请求可继续完成。
- Python 网络错误为 `tlsurl.Error`，Node.js 为 `TlsurlError`，可读取 `code`，例如 `TIMEOUT`、`TLS`、`CONNECT`、`CANCELLED`。

## 开发、构建与更多文档

构建者需要 Rust、C/C++ 工具链及 BoringSSL 构建依赖；使用预编译工件的调用方不需要安装 Rust。构建入口为 `python scripts/build_native.py`，环境准备及各平台限制见下方文档。

- [完整 API 与构建说明](docs/native-bindings.md)
- [平台支持与二进制审计](docs/platform-support.md)
- [测试范围与持续负载验证](docs/validation.md)
- [首发交付规格](docs/delivery-plan.md)
- [发布流程与账号配置](docs/publishing.md)
- [上游 wreq 原始说明](docs/upstream-wreq.md)

## 来源与许可证

tlsurl 基于 wreq，并保留其源于 [reqwest](https://github.com/seanmonstar/reqwest) 的项目历史及原始声明。浏览器预设来自 wreq-util。上游 Rust crate 的能力不全部等同于 Python/Node.js 已公开的接口，绑定范围以本项目 API 文档为准。

本项目采用 [Apache-2.0](LICENSE) 许可证。第三方组件保留各自条款，完整文本随安装包分发，也可查看[第三方许可证汇编](docs/THIRD_PARTY_LICENSES.txt)和[补充来源记录](docs/licenses/README.md)。
