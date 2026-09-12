# 平台支持与工件审计

首发提供五个目标的预编译工件，常规 GIL 版 CPython 3.10–3.14 与 Node 22/24。编译目标、宿主运行时要求、实际测试系统分别记录，不用新系统上的成功替代旧系统验收。

| 工件目标 | 原生工件基线 | 当前 CI 测试环境 |
| --- | --- | --- |
| Linux x64 GNU | manylinux_2_28，glibc ≥ 2.28 | manylinux_2_28_x86_64 容器，Ubuntu runner 内核 |
| Linux ARM64 GNU | manylinux_2_28，glibc ≥ 2.28 | manylinux_2_28_aarch64 容器，ARM64 Ubuntu runner 内核 |
| Windows x64 MSVC | x64 DLL，系统 DLL 与 VC Runtime；Python 扩展另需 python3.dll | Windows Server 2022；本地 Windows 11 |
| macOS Intel | 构建部署目标 11.0，由 Mach-O 元数据审计约束 | macOS 15 Intel runner |
| macOS Apple Silicon | 构建部署目标 11.0，由 Mach-O 元数据审计约束 | macOS 15 ARM64 runner |

最终可运行范围还受所安装 Python/Node 版本约束：

- Node 22 的 macOS 基线为 11.0；Node 24 为 13.5。两者 Linux x64/ARM64 官方 GNU 二进制要求 glibc 2.28、内核 4.18；还需符合对应 libstdc++ 要求。Windows x64 为 Windows 10/Server 2016 起。具体运行时支持及系统维护状态以 [Node 22 平台说明](https://github.com/nodejs/node/blob/v22.x/BUILDING.md#platform-list)和 [Node 24 平台说明](https://github.com/nodejs/node/blob/v24.x/BUILDING.md#platform-list)为准。
- Python 3.14 官方支持 Windows 10 及更新版本；macOS 安装器支持范围需核对所选发行包。参见 [Python Windows 说明](https://docs.python.org/3.14/using/windows.html#supported-windows-versions)和 [macOS 安装说明](https://docs.python.org/3.14/using/mac.html)。本项目 macOS 工件仍以自己的 11.0 部署目标为下界。
- 未在 macOS 11/13.5、Windows 10 或旧内核真机/虚拟机完整运行全部测试，因此这些最低版本属于构建及上游运行时约束，尚不是本项目的旧系统实测承诺。

## 自动审计内容

`python scripts/audit_native.py --artifacts dist --output dist/audit/native-audit-<target>.json` 从 wheel/npm tarball 读取真正分发的二进制，检查：

1. ELF/PE/Mach-O 架构与当前构建目标一致，Python/Node 注册入口存在。
2. Linux 只依赖列出的系统库；GLIBC/GLIBCXX/CXXABI 符号版本分别不超过 2.28/3.4.25/1.3.11。
3. Windows 只依赖系统 DLL、VC Runtime，以及 Python 扩展所需的 python3.dll；不将系统 OpenSSL DLL 当作安装前置条件。
4. macOS 加载命令的最低系统版本不超过 11.0，只链接系统路径下的动态库；不携带构建机绝对运行时搜索路径。
5. 不导出未加前缀的 SSL_/OPENSSL_/CRYPTO_/EVP_/X509_ 符号，降低与 Python ssl、Node crypto 同进程共存时的符号冲突风险。实际共存另有 smoke 测试。

每份报告包含源提交、构建宿主与工具版本、包及二进制 SHA-256、动态依赖和部署元数据。Linux 使用 readelf，Windows 使用 dumpbin，macOS 使用 otool/nm，均为构建工具，不要求最终用户安装。

汇总阶段要求五份报告来自同一提交，且报告中的包哈希与实际包一致；缺少报告、修改过包或提交不一致时拒绝汇总。发行目录含 11 个安装包、5 份报告及 SHA256SUMS。`tests/bindings/test_audit.py` 覆盖错误架构、过高符号版本、外部 OpenSSL、错误入口和汇总篡改等拒绝路径。

## 已验证与待验证

- Windows 当前实包审计已通过，未发现外部 libssl/libcrypto DLL 依赖。
- 五平台审计代码已接入 CI；Linux/macOS 的报告须等待对应提交运行成功后确认。
- 五平台的 Python/Node 版本组合已有完整 CI 成功记录；每次功能变更仍需使用该提交的新结果，不能沿用旧提交证明全部功能。
- 尚未提供 musl/Alpine、Windows ARM64、32 位、Android、iOS、FreeBSD、PyPy 或 free-threaded CPython 工件。上游可编译的平台不自动等于本项目已发布可安装包的平台。
- 二进制架构与库版本审计不能证明所有旧 CPU 指令集兼容性。当前不使用本机 CPU 专用编译选项；汇编实现的运行时 CPU 分派由上游实现，旧 CPU 实机验收仍未完成。
