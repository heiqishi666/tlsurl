# 验证范围与复现

验收以构建后的 wheel 和 npm 包为对象。构建成功、当前 runner 测试通过、最低系统兼容和正式发布分别记录，不能互相替代。

## 实包功能测试

`tests/bindings/` 包含基础请求、TLS/HTTP2、流式读取、文件上传和 WebSocket 测试。覆盖证书信任、主机名校验、mTLS、协议协商、实际连接取消、背压、超时及关闭后的资源释放。服务端记录连接状态，避免只验证调用方收到取消异常。

测试服务通过 `node -p process.execPath` 解析真实 Node 可执行文件，避免 Windows 启动器的子进程在测试结束后遗留。

## 类型声明

安装构建后的 wheel、npm 主包与平台包，再执行：

```sh
python -m pip install mypy==1.19.1
npm ci --prefix tests/bindings
python tests/bindings/typecheck.py --node-module dist/consumer/node_modules/tlsurl
```

Python 使用 mypy strict 检查 3.10 与 3.14 目标；Node 使用 TypeScript strict。正例必须通过，错误 TLS 版本、HTTP2 参数、Multipart 字段和请求参数等反例必须在指定行被拒绝。Python 类型辅助类同时验证运行时可导入。

## 本地持续负载记录

Windows x64、Python 3.13.0、Node 24.9.0，在本机回环 HTTP 服务上顺序运行。每批包含 16 个并发 1 KiB 缓冲请求和一个 64 KiB 流，每十批取消一次等待中的流。预热五批后计数。

| 指标 | Python | Node |
|---|---:|---:|
| 实际运行秒数（含收尾） | 300.23 | 306.02 |
| 缓冲请求 | 1,444,688 | 2,760,352 |
| 完整流 | 90,293 | 172,522 |
| 主动取消 | 9,029 | 17,252 |
| 非预期错误 | 0 | 0 |
| 基线 RSS（字节） | 36,782,080 | 58,781,696 |
| 负载阶段采样峰值 RSS（字节） | 48,930,816 | 166,182,912 |
| 收尾 RSS（字节） | 49,147,904 | 169,947,136 |
| 关闭客户端后服务端连接 | 1 | 1 |

最后一个连接为指标观察请求。连接复用及关闭释放断言通过。RSS 是采样值，不能证明没有瞬时峰值或长期内存泄漏；当前脚本也将收尾采样纳入峰值门限。首次测量发现 ctypes 类型重复创建干扰内存采样，修复并重新完整运行后才记录上表。

复现：

```sh
python tests/bindings/stress.py --seconds 300 --node-module dist/consumer/node_modules/tlsurl --output dist/stress
```

时长为每种语言的负载时长，收尾另计；CI 使用每种语言 10 秒的短验收。报告保存实际次数、RSS 与连接状态。这个用例不包含 TLS/WebSocket 持续负载，不代表公网吞吐、最低系统、旧 CPU 或数日运行结果；TLS/WebSocket 由独立协议测试覆盖。

## 平台与发布边界

二进制审计检查架构、动态依赖、符号版本、部署版本和入口符号。收集阶段检查五个平台审计报告与包的哈希及源码提交一致。兼容矩阵及未覆盖平台见 [平台支持](platform-support.md)。CI 最新状态应以对应提交的 GitHub Actions 结果为准。只有官方仓库上传及公开安装验收完成后才标记发布成功。
