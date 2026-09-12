# tlsurl 原生绑定第一阶段

基于上游 wreq 提交 `12ccf64bb00e79db6eabd4bc3ccf82871d3eb5a5`。
保留根 crate 名称和 API，新增共享核心及两种语言绑定。当前版本是开发预览，尚未发布到 PyPI/npm。

## 已实现的接口

- Python `Client.request()`、`AsyncClient.request()`；Node `Client.request()` 返回 Promise。
- 参数：HTTP method、URL、有序 Header 列表、可选二进制 Body。
- 返回：status、最终 URL、重复 Header 列表、二进制 Body。
- Client 复用连接池及 Cookie store；启用默认重定向和 TLS 证书校验。
- 默认总超时 30 秒、最大缓冲响应 16 MiB；配置均须为正整数。
- 当前不读取系统代理，尚无显式代理参数。
- HTTP 4xx/5xx 返回响应；网络和参数错误抛出异常，消息前缀包含错误分类。
- Python 异步取消通过 pyo3-async-runtimes 传递；Node AbortSignal 尚未实现。

这是第一阶段安装和调用验证接口。指纹预设、高级 TLS/HTTP2 参数、结构化 JSON/Form、流式读取、WebSocket、代理和统一异常类仍待后续实现，不宣称已完成此前方案的全部能力。

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

工件位于 `dist/wheels` 与 `dist/npm`。开发阶段的主 npm tarball包含当前平台二进制，同时生成独立平台 tarball；正式统一主包及 optionalDependencies 聚合发布仍待实现，不能把任一单平台主包当作全平台正式包上传。

## 验证与发布边界

Native packages 工作流覆盖 Linux x64/ARM64、Windows x64、macOS Intel/ARM64。
每个作业构建、安装 wheel 和 npm tarball，再运行同一组协议测试；当前测试运行时为 CPython 3.13、Node 24。
`abi3-py310` 是编译目标，不等于 Python 3.10～3.14 全版本验收已经完成。
后续补充 Python 版本矩阵、Node 22、各平台无编译器隔离安装与动态库审计后再正式发布。

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
- Linux/macOS 尚未实际构建；Python 其他版本及 Node 22 尚未执行测试。
- 上游 dev-dependency `sysinfo 0.39.x` 声明 Rust 1.95；本轮未改动上游依赖，也未用 Rust 1.94 宣称全仓 `cargo test --workspace` 通过。绑定构建不依赖该 benchmark 依赖。

工作流只生成 GitHub Actions 工件，不上传 PyPI/npm。发布账号、Trusted Publishing、正式主包聚合和完整平台验收完成后再单独开放发布。
上游自带 CI/发布流程尚未改造，不要推送版本标签触发原 wreq 发布任务。

原代码及协议来自 wreq/reqwest；所有分发包保留 Apache-2.0 LICENSE。
