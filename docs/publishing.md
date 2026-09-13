# 预编译包发布

入口为 `.github/workflows/publish-native.yml`，仅手动触发。`registry` 可选 `pypi`（默认）、`npm` 或 `both`。默认 `publish=false`，校验工件及所选注册表；选择 npm 时另执行 npm dry-run，不会上传。普通push及上游release-plz不会触发这个发布入口。

## 选择候选

先让当前main提交的Native packages完整31个作业通过，记录run ID。在同一main提交上运行Publish native packages，填写该run ID。工作流校验仓库、提交、分支、事件、工作流路径和全部作业结果，下载native-release，再核对16份文件校验和、版本、五平台审计与第三方声明。若main已有后续提交，需要先为新提交跑完整CI。

首次先用publish=false跑完演练。Python 开发预览版 0.1.0 已上传 PyPI，npm 尚未发布。新版本仍需先完成候选 CI 和演练。

## 账号配置

GitHub仓库为heiqishi666/tlsurl，工作流文件名为publish-native.yml，environment为native-release。

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

Node 用户暂时按 README 下载 GitHub 工件安装，不需要 npm 账号。正式发布某一语言后，应分别更新其安装说明，不能将另一语言也标为已发布。


## PyPI 0.1.0 发布记录

- 候选提交：`1911cb7d0e64bda0b68fb03761a8d69ad4a06173`。
- 构建验收：[34744491574](https://github.com/heiqishi666/tlsurl/actions/runs/34744491574)，31 个作业全部成功。
- PyPI 单独演练：[34745552365](https://github.com/heiqishi666/tlsurl/actions/runs/34745552365)。
- 上传及公开安装验收：[34745607074](https://github.com/heiqishi666/tlsurl/actions/runs/34745607074)。首次上传后 PyPI JSON 尚未同步，回读失败；等待版本可见后重跑同一候选，已上传同哈希文件自动跳过。
- 最终发布流程 6/6 作业成功，五个 PyPI wheel 回读哈希一致，五个平台公开安装及协议测试全部通过。
- npm 未上传；用户继续下载 GitHub 的 npm 工件安装。
