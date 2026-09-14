# 预编译包发布

入口为 `.github/workflows/publish-native.yml`，仅手动触发。`registry` 可选 `pypi`（默认）、`npm` 或 `both`。默认 `publish=false`，校验工件及所选注册表；选择 npm 时另执行 npm dry-run，不会上传。普通push及上游release-plz不会触发这个发布入口。

## 选择候选

先让当前main提交的Native packages完整31个作业通过，记录run ID。在同一main提交上运行Publish native packages，填写该run ID。工作流校验仓库、提交、分支、事件、工作流路径和全部作业结果，下载native-release，再核对16份文件校验和、版本、五平台审计与第三方声明。若main已有后续提交，需要先为新提交跑完整CI。

首次先用publish=false跑完演练。Python 0.1.0 已上传 PyPI；npm 首发部分成功，Windows 包被名称反垃圾机制拦截，主包尚未上传。GitHub Packages 六包及五平台安装已完成，详见文末记录。新版本仍需先完成候选 CI 和演练。

## 账号配置

GitHub仓库为knight-bili/tlsurl，工作流文件名为publish-native.yml，environment为native-release。

- PyPI：为tlsurl配置上述GitHub可信发布者；新包可在账户Publishing页面配置pending publisher。工作流使用短期OIDC身份，不读取本地.pypirc。
- npm：六个包均需发布权限（tlsurl及五个平台包）。已有包可分别配置上述可信发布者，并允许直接npm publish。首发尚无包设置入口时，可由包所有者提供限定权限的NPM_TOKEN仓库secret用于首次发布；随后配置六个包的可信发布者并移除该token。不要把token写进源码或提交记录。
- npm使用GitHub托管Node24运行环境，可信发布要求npm至少11.5.1及Node至少22.14。

配置依据：[npm可信发布](https://docs.npmjs.com/trusted-publishers/)、[PyPI可信发布](https://docs.pypi.org/trusted-publishers/using-a-publisher/)。账号拥有者的授权和站点配置不能由仓库文件代替。

## 正式发布与重试

确认演练成功且发布账号已配置后，以相同run ID设置publish=true。选择 `both` 时依次发布五个 npm 平台包、npm 主包，最后通过 PyPI 官方 action 上传 wheel；单选时只发布对应注册表。没有重新编译，使用通过矩阵测试的原工件。

发布中断后可重跑同一候选。npm比较注册表SHA-512，PyPI比较每个文件SHA-256；仅相同内容可跳过。冲突立即失败，不覆盖、不自动换版本、不撤回已有包。已发布部分保留并按相同候选补传。网络错误不会当作包不存在。

正式上传后，工作流下载所选官方注册表中的压缩包（PyPI 5 个、npm 6 个、both 11 个）核对候选哈希，并保存 registry-verification.json。随后五个平台独立 runner 从所选注册表固定版本公开安装，未发布语言的测试伴随包来自候选工件；Python 禁止源码构建、npm 禁用安装脚本，再执行基础请求、TLS、流式、上传和 WebSocket 测试（Python 3.13/Node 24）。候选构建CI另覆盖Python3.10–3.14与Node22/24。注册表一致性和公开安装均通过后才可标记本轮发布验收完成。


## 仅发布 PyPI

PyPI Pending Publisher 配置完成后，无需 npm 账号。运行入口选择 `registry=pypi`，先 `publish=false` 演练，通过后再用同一候选 `publish=true`。npm 发布、npm 注册表归档核验均跳过；只上传五个 wheel，并从 PyPI 下载核对字节。

五个平台的公开安装测试从 PyPI 安装 Python 包；Node 测试伴随包来自该候选的已审计 GitHub 工件，以保留跨语言握手比较。此时不能把 Node 测试称为 npm 公开安装成功。`registry=npm` 时对称处理：Node 从 npm 安装，Python 测试伴随包来自 GitHub 工件；`both` 时两者均从官方注册表安装。

Node 用户可按 README 下载 Release 工件离线安装，或使用 GitHub Packages。正式发布某一语言后，应分别更新其安装说明，不能将另一语言也标为已发布。


## PyPI 0.1.0 发布记录

- 候选提交：`1911cb7d0e64bda0b68fb03761a8d69ad4a06173`。
- 构建验收：[34744491574](https://github.com/heiqishi666/tlsurl/actions/runs/34744491574)，31 个作业全部成功。
- PyPI 单独演练：[34745552365](https://github.com/heiqishi666/tlsurl/actions/runs/34745552365)。
- 上传及公开安装验收：[34745607074](https://github.com/heiqishi666/tlsurl/actions/runs/34745607074)。首次上传后 PyPI JSON 尚未同步，回读失败；等待版本可见后重跑同一候选，已上传同哈希文件自动跳过。
- 最终发布流程 6/6 作业成功，五个 PyPI wheel 回读哈希一致，五个平台公开安装及协议测试全部通过。
- 此次仅上传 PyPI；当时 npm 未上传，后续首发情况见下文。


## npm 与 GitHub 首发记录（2026-09-14）

- 候选提交 `15ea3660a9e598e1f93a0f7f819d68f032fc68ca`；[构建34814012776](https://github.com/knight-bili/tlsurl/actions/runs/34814012776)最终31/31通过。首次一个macOS ARM64抓包转发测试发生BrokenPipe，保留失败证据后同候选单项重跑通过，没有修改产品或放宽校验。
- [npm预检34816409783](https://github.com/knight-bili/tlsurl/actions/runs/34816409783)成功；[正式上传34816520867](https://github.com/knight-bili/tlsurl/actions/runs/34816520867)中四个Linux/macOS包成功，`tlsurl-win32-x64-msvc`被npm返回`Package name triggered spam detection`，主包未上传。需账号所有者联系npm支持；解除后重跑该原始发布任务的失败作业，按原候选补发，不能覆盖或换包内容。
- npm的`NPM_TOKEN`已证明有效；保留已发布四包，尚不能宣称npm完整发布或公开安装验收成功。PyPI本轮未重发。
- [GitHub Packages流程34816919015](https://github.com/knight-bili/tlsurl/actions/runs/34816919015)6/6成功：六个公开作用域包、官方归档哈希、Linux x64/ARM64、Windows x64和macOS Intel/ARM64安装及协议测试全部通过。
- GitHub包由同一验收工件转换名称为`@knight-bili/tlsurl`和五个平台包；主包使用npm别名依赖保持原生加载器的本地依赖名，未重新编译。发布入口`.github/workflows/publish-github-package.yml`固定本次版本/来源，使用Actions短期GITHUB_TOKEN，未来版本应重新选择验收候选。
- [Release v0.1.0](https://github.com/knight-bili/tlsurl/releases/tag/v0.1.0)提供正式PyPI五个wheel、已验收Node六个tgz、安装说明、来源记录和SHA256SUMS；Python与Node来源提交分别记录，不把新构建的Python同版本工件作为已发布PyPI文件。
- `bin/node/0.1.0`保留源提交`1911cb7d`的旧离线工件；其哈希与本次Node发布候选不同，核验Release应使用Release自带清单。
