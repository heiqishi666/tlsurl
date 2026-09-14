# GitHub Packages 安装

`@knight-bili/tlsurl@0.1.0` 和五个平台包已公开发布到 [GitHub Packages](https://github.com/users/knight-bili/packages?repo_name=tlsurl)，并通过五平台实际安装及协议测试。原生二进制来自已通过31项检查的构建34814012776。

## 认证和安装

GitHub 的 npm registry 即使是公开包也要求认证。使用具有 `read:packages` 权限的 GitHub personal access token (classic)，在下方登录提示中作为密码输入。不要使用 npm Token，也不要将令牌写入项目或提交记录。[GitHub 官方说明](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-npm-registry)

在自己的 Node 项目中执行：

```sh
npm config set "@knight-bili:registry" "https://npm.pkg.github.com" --location=project
npm login --registry=https://npm.pkg.github.com --auth-type=legacy
npm install @knight-bili/tlsurl@0.1.0
```

```javascript
import { Client } from '@knight-bili/tlsurl'

const client = new Client({ randomTls: true })
try {
  const response = await client.get('https://example.com')
  console.log(response.status, response.text())
} finally {
  client.close()
}
```

如需保持原有 `from 'tlsurl'` 或 `require('tlsurl')`，在完成上述 registry 配置与登录后使用 npm 别名安装：

```sh
npm install tlsurl@npm:@knight-bili/tlsurl@0.1.0
```

平台包同样在 GitHub Packages，主包通过 npm 别名自动安装适配当前系统的原生包。保留 optionalDependencies，不要使用 `--omit=optional`。支持 Node.js 22/24；平台限制见[平台说明](platform-support.md)。

## 离线方式

不配置 GitHub Packages 凭据时，可从 [Release v0.1.0](https://github.com/knight-bili/tlsurl/releases/tag/v0.1.0) 下载未加作用域的主包和对应平台包，按[Node教程](node-tutorial.md#install)安装。下载的文件使用 Release 自带 SHA256SUMS 校验。

## npm 官方注册表状态

npm 首发中四个 Linux/macOS 平台包已成功，Windows 包被名称反垃圾机制误判，主包尚未上传。账号所有者需联系 npm Support；解除后使用原候选补发。当前不能把 `npm install tlsurl` 作为官方可用入口，GitHub Packages 是独立的分发入口。
