# tlsurl 首发交付规格

目标：通过 PyPI/npm 安装预编译 HTTP 客户端；增强能力集中在 Rust 核心，两种语言共享协议语义。保留上游署名及许可证。本文为已定稿的实施范围，未标记通过的项目不表示已实现。

## 接口约定

- 保留现有 `Client(timeout_ms, max_response_bytes)`、`request(method, url, headers, body)` 调用兼容性。
- Python 新增关键字配置，Node 新增配置对象；所有时长使用毫秒，大小使用字节。
- 请求支持重复 Header，原始字节值；便捷接口同时接受字符串值。Header 的重复项及原始顺序由核心传递，上游合并同名 Header 的大小写行为不自行伪造。
- `params` 为有序键值对，追加到 URL 已有查询参数；保留重复键。
- `body`、`json`、`form`、`multipart` 互斥，冲突在发送前报错；显式 Content-Type 优先。JSON 与 Form 的语言适配不改变底层字节接口。
- 请求级超时覆盖客户端默认；默认 30 秒，响应缓冲上限 16 MiB。所有数值边界在进入核心前/核心中校验。
- 代理默认关闭，只有显式代理地址才启用；不隐式读取系统代理。TLS 验证默认开启，自定义 PEM 信任库需显式配置。
- HTTP 4xx/5xx 返回正常响应，`raise_for_status`/`raiseForStatus` 显式转为错误。网络错误提供稳定 `code`，消息不含带凭据的请求 URL。
- `Response` 提供 status、url、重复 headers、body 及 text/json 便捷读取；缓冲响应与流式响应使用不同类型。
- 同步 Python Client 与异步 AsyncClient 功能一致；Node 使用 Promise。关闭客户端后拒绝新请求，流式资源与在途请求的取消语义另有专项验收。
- 首发常规 CPython 3.10–3.14、Node 22/24；free-threaded Python/PyPy 不纳入此轮。系统矩阵以实测记录为准。

## 批次与验收

1. 基础请求：params、JSON/Form/Multipart、Basic/Bearer auth、Cookie 管理、代理、请求/连接超时、重定向、证书配置、响应便捷方法及结构化错误。通过本地实包协议测试和 CI。
2. TLS/HTTP：开放上游已有的版本、ALPN、cipher/curve、HTTP 版本与 Header 排列配置；浏览器预设优先使用可追踪、许可兼容的上游来源，不凭名称捏造指纹。
3. 生命周期与传输：Python/Node 取消、客户端关闭、流式读写和背压、WebSocket；先定义资源所有权，再验证取消/大文件/连接释放。
4. 平台与稳定性：最低系统版本、glibc/CPU 要求、动态依赖、证书、压力与长运行测试。额外架构只有实际构建和安装通过后才加入支持列表。
5. 文档与发布：类型检查、示例、API 文档、版本及第三方声明、工件审计、发布候选、可信发布配置和公开安装验收。

## 执行与阻塞处理

- 一批内部多个中文 commit，检查通过后统一 push；CI 等待期间推进独立文档、审计或下一批准备。
- 用工作区 `tlsurl-workflow-state.md` 记录当前提交、日志路径、成功与待处理项，压缩上下文后从该文件继续。
- 无法获得某个平台或发布账号时，记录具体证据，继续可独立推进的工作。只有实际上传并公开安装成功后才标为已发布。
- 功能实现、在当前 runner 通过、最低系统版本支持、正式发布是四种不同状态，不互相替代。
