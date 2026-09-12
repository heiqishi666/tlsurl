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
- Python 异步取消通过 pyo3-async-runtimes 传递；Node AbortSignal 尚未实现。

指纹预设、流式读取、WebSocket、Node AbortSignal 仍待后续实现。首发范围与后续队列见 [交付规格](delivery-plan.md)。

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
当前缓冲响应可以反复访问 body；后续流式响应将采用不同的对象和一次消费语义。

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

Python Multipart 字段使用 `name/data/filename/content_type`，Node 使用 `name/data/filename/contentType`；当前文件内容由调用者读成 bytes/Buffer，上传编码由 Rust 生成，尚不是磁盘流式上传。`body/json/form/multipart` 互斥；参数支持重复键，追加而不覆盖 URL 已有查询。params 和 form 使用字符串键值对。

客户端配置为 Python `connect_timeout_ms/read_timeout_ms/proxy/verify/ca_pem/max_redirects/cookies/user_agent/http_version`；Node 对应 camelCase。`http_version` 为 `auto/1.1/2`。`ca_pem` 是 PEM 内容，替换默认信任库；`verify=False` 仅在显式配置时关闭证书校验。重定向上限 0 表示不跟随。

请求配置为 Python `params/json/form/multipart/basic_auth/bearer_token/timeout_ms/max_redirects`；Node 对应 camelCase。认证选项互斥，也不允许与显式 Authorization Header 混用。响应 `text()` 默认 UTF-8，`json()` 解析失败保留语言原生 JSON 异常。

Cookie 按上游域、路径、Secure 和过期规则接受与选择；`set_cookie` 不绕过这些规则，例如从 HTTP 来源写入 Secure Cookie 会被忽略。`cookies=False` 禁止自动收发存储 Cookie，但显式 Cookie Header 仍由调用者控制。

`close()` 释放客户端持有的连接池引用并拒绝新请求；已经提交的请求可继续完成。Python 支持 `with Client()` / `async with AsyncClient()`。强制取消在途请求仍属于后续生命周期阶段。

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

## 构建

构建机需要 Rust 1.94.0、Python、Node 24、CMake、Perl、libclang；Windows 另需 MSVC、Windows SDK、NASM。
Windows 构建输出目录必须使用 ASCII 路径，避免 NASM 无法读取中文路径。
SDK、工具链只属于构建机依赖，用户安装工件不需要这些工具。

```text
python -m pip install maturin==1.15.0 libclang==18.1.1 ninja==1.13.2
python scripts/build_native.py
```

Linux 必须在 manylinux_2_28 容器中运行，不能直接将新版 Ubuntu 的产物标成 manylinux。
macOS 拟定最低 11.0，须以目标平台验证结果为准。
Cargo.lock 和 npm package-lock.json 随仓库提交，构建使用锁文件。

工件位于 `dist/wheels` 与 `dist/npm`。主 npm tarball 只包含加载器、类型声明和许可证，通过固定版本的 optionalDependencies 引用五个平台包；各平台包单独携带原生二进制。发行 manifest 在打包暂存目录中生成，开发环境安装不会尝试下载尚未发布的平台包。

工作流汇总五个平台的输出，检查主包内容一致、平台包齐全、版本一致、二进制存在以及 wheel 不重复，再生成 `native-release` 工件和 `SHA256SUMS`。这个工件包含五个 wheel、五个平台 npm tarball 和一个 npm 主包。

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
- 随后提交 `f80c2806` 的五平台 CI 已全部通过，包含 Linux/macOS 实际构建、CPython 3.13/Node 24 安装与协议测试：[运行记录](https://github.com/heiqishi666/tlsurl/actions/runs/34705604255)。本轮扩展版本矩阵尚需新的 CI 结果确认。
- 上游 dev-dependency `sysinfo 0.39.x` 声明 Rust 1.95；本轮未改动上游依赖，也未用 Rust 1.94 宣称全仓 `cargo test --workspace` 通过。绑定构建不依赖该 benchmark 依赖。

工作流只生成 GitHub Actions 工件，不上传 PyPI/npm。正式发布时必须先上传所有平台 npm 包，核验可下载后再上传主包，避免用户安装时缺少对应的可选依赖。聚合包的安装前提是保留 optionalDependencies，不能使用 `--omit=optional`。
上游自带 CI/发布流程尚未改造，不要推送版本标签触发原 wreq 发布任务。

原代码及协议来自 wreq/reqwest；所有分发包保留 Apache-2.0 LICENSE。
