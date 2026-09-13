# Node.js 0.1.0 预编译包

主包和五个平台原生包均为原始 CI 工件，未重新打包。每个包内包含许可证声明。

- 来源：https://github.com/heiqishi666/tlsurl/actions/runs/34744491574
- 源提交：`1911cb7d0e64bda0b68fb03761a8d69ad4a06173`
- 构建验收：31/31 作业成功，覆盖 CPython 3.10–3.14、Node 22/24。
- `SHA256SUMS` 与该次 CI 发布清单中六个 npm 包的哈希一致。

下载 `tlsurl-0.1.0.tgz` 和当前系统对应的平台包，在项目中安装两个本地文件。例如 Windows x64：

```sh
npm install --ignore-scripts ./tlsurl-win32-x64-msvc-0.1.0.tgz ./tlsurl-0.1.0.tgz
```

Linux 为 glibc >= 2.28；不支持 musl/Alpine。Windows 提供 x64，macOS 提供 Intel 与 Apple Silicon。具体平台表及使用示例见仓库根 README。

这些是可提交到 Git 的普通文件，不依赖 Actions 工件保留期限。升级时使用新版本目录，主包和平台包必须保持同一版本。
