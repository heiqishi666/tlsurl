# tlsurl 文档索引

[项目首页](../README.md) · [Python 教程](python-tutorial.md) · [Node.js 教程](node-tutorial.md)

## 第一次使用

1. **选择语言并安装**：[Python 从 PyPI 安装](python-tutorial.md#install)；[Node 从 Release 或 GitHub Packages 安装](node-tutorial.md#install)。
2. **跑通一个 GET**：[Python](python-tutorial.md#simple) / [Node](node-tutorial.md#simple)。
3. **按场景加配置**：下面的表格直达代码示例；登录后连续请求先看「会话和 Cookie」，指纹配置看「TLS 指纹」。

Python 0.1.0 已发布 PyPI；Node 0.1.0 可从 [Release](https://github.com/knight-bili/tlsurl/releases/tag/v0.1.0) 离线安装，或使用 [GitHub Packages](github-packages.md)。npm 官方主包尚未上传，不能直接 `npm install tlsurl`。两个教程均基于当前 0.1.0 API。

## 按场景查教程

| 阶段 | 我想做什么 | Python | Node.js |
| --- | --- | --- | --- |
| 请求入门 | GET、状态码、正文、其他 HTTP 方法 | [简单请求](python-tutorial.md#simple) | [简单请求](node-tutorial.md#simple) |
| 请求入门 | 自定义 Header、User-Agent、重复 Header、URL 参数 | [Header 与参数](python-tutorial.md#headers-params) | [Header 与参数](node-tutorial.md#headers-params) |
| 请求入门 | POST JSON + 参数 + 认证 + 超时 | [复杂请求](python-tutorial.md#complex) | [复杂请求](node-tutorial.md#complex) |
| 请求入门 | Form、重复字段、原始二进制正文 | [表单与正文](python-tutorial.md#body) | [表单与正文](node-tutorial.md#body) |
| 会话和 Cookie | 登录后连续请求、循环分页、复用连接 | [连续请求](python-tutorial.md#session) | [连续请求](node-tutorial.md#session) |
| 会话和 Cookie | 设置、读取、删除 CK；粘贴 Cookie 字符串 | [Cookie](python-tutorial.md#cookies) | [Cookie](node-tutorial.md#cookies) |
| TLS 指纹 | 引用内置 Chrome/Firefox/Safari 预设 | [自带指纹](python-tutorial.md#profiles) | [自带指纹](node-tutorial.md#profiles) |
| TLS 指纹 | 修改套件、曲线、签名算法、ALPN | [自定义指纹](python-tutorial.md#custom-tls) | [自定义指纹](node-tutorial.md#custom-tls) |
| TLS 指纹 | 一键随机、种子复现、每次新建随机会话 | [随机指纹](python-tutorial.md#random-tls) | [随机指纹](node-tutorial.md#random-tls) |
| 进阶功能 | 异步/并发请求与客户端生命周期 | [asyncio](python-tutorial.md#concurrency) | [Promise](node-tutorial.md#concurrency) |
| 进阶功能 | Multipart 上传、文件流式下载 | [文件](python-tutorial.md#files) | [文件](node-tutorial.md#files) |
| 进阶功能 | 状态异常、网络超时、取消 | [错误与超时](python-tutorial.md#errors) | [错误与取消](node-tutorial.md#errors) |
| 进阶功能 | 代理、自定义证书信任库 | [代理与 CA](python-tutorial.md#errors) | [代理与 CA](node-tutorial.md#proxy) |

## 两种语言的常用字段对照

| 用途 | Python | Node.js | 放在哪里 |
| --- | --- | --- | --- |
| 查询参数 | `params={"page": "1"}` | `params: {page: '1'}` | 请求 |
| 请求头 | `headers={"X-Id": "demo"}` | `headers: {'X-Id': 'demo'}` | 请求 |
| JSON 正文 | `json={"name": "demo"}` | `json: {name: 'demo'}` | 请求 |
| Bearer 认证 | `bearer_token="..."` | `bearerToken: '...'` | 请求 |
| 总超时，毫秒 | `timeout_ms=10000` | `timeoutMs: 10000` | Client 默认值或请求覆盖 |
| 默认 UA | `user_agent="..."` | `userAgent: '...'` | Client |
| 关闭自动 Cookie | `cookies=False` | `cookies: false` | Client |
| 写入 Cookie | `client.set_cookie(url, value)` | `client.setCookie(url, value)` | Client 方法 |
| 读取 Cookie | `client.cookies(url)` | `client.cookies(url)` | Client 方法 |
| 清空 Cookie | `client.clear_cookies()` | `client.clearCookies()` | Client 方法 |
| 浏览器预设 | `profile="chrome_149"` | `profile: 'chrome_149'` | Client |
| 手工 TLS | `tls={...}` | `tls: {...}` | Client |
| 一键随机 TLS | `random_tls=True` | `randomTls: true` | Client |
| 随机种子 | `random_tls_seed=42` | `randomTlsSeed: 42` | Client，须启用随机模式 |
| HTTP 状态检查 | `response.raise_for_status()` | `response.raiseForStatus()` | Response 方法 |

请求 URL、Header、params、正文属于每次请求；TLS/预设/随机策略属于客户端。随机模式与手工 TLS、profile、platform 互斥；预设与手工 TLS 则可组合，按字段覆盖。JA3/JA4 是握手摘要，不是能直接设置的任意哈希。

## API、平台与发布资料

| 文档 | 什么时候看 |
| --- | --- |
| [原生绑定 API](native-bindings.md) | 完整配置范围、生命周期、HTTP/2、mTLS、流式与 WebSocket |
| [平台支持](platform-support.md) | Linux glibc、Windows/macOS 架构和运行时要求 |
| [验证范围](validation.md) | 已验证内容与测试边界 |
| [GitHub Packages](github-packages.md) | 作用域包安装、认证及 npm 别名 |
| [发布说明](publishing.md) | PyPI/npm 单独发布、可信发布配置与发布记录 |
| [Node 二进制包](../bin/node/0.1.0/README.md) | 获取原始 tgz、来源提交和 SHA-256 清单 |
| [交付规格](delivery-plan.md) | 项目交付范围及历史实施计划 |
| [上游说明](upstream-wreq.md) | 原 wreq 项目介绍与来源 |

教程示例使用演示 URL 和凭据；连接真实业务接口时应替换这些值。默认启用证书校验，默认不读取系统代理。

## 示例核验

2026-09-13：Python 教程 19 个、Node 教程 20 个完整代码块已使用 0.1.0 原生包在本地 HTTPS 回显服务上执行通过。核验时替换演示地址、注入测试 CA 并提供临时代理和上传文件；检查了实际 Header、重复查询参数、JSON 认证、Cookie 和文件内容。文档中的公网示例服务未作为这次验收依赖。
