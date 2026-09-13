# 预编译包发布

入口为 `.github/workflows/publish-native.yml`，仅手动触发。`registry` 可选 `pypi`（默认）、`npm` 或 `both`。默认 `publish=false`，校验工件及所选注册表；选择 npm 时另执行 npm dry-run，不会上传。普通push及上游release-plz不会触发这个发布入口。

## 选择候选

先让当前main提交的Native packages完整31个作业通过，记录run ID。在同一main提交上运行Publish native packages，填写该run ID。工作流校验仓库、提交、分支、事件、工作流路径和全部作业结果，下载native-release，再核对16份文件校验和、版本、五平台审计与第三方声明。若main已有后续提交，需要先为新提交跑完整CI。

首次先用publish=false跑完演练。当前开发版0.1.0尚未正式发布，仓库内的预览说明应在候选定稿时同步确认。

## 账号配置

GitHub仓库为heiqishi666/tlsurl，工作流文件名为publish-native.yml，environment为native-release。

- PyPI：为tlsurl配置上述GitHub可信发布者；新包可在账户Publishing页面配置pending publisher。工作流使用短期OIDC身份，不读取本地.pypirc。
- npm：六个包均需发布权限（tlsurl及五个平台包）。已有包可分别配置上述可信发布者，并允许直接npm publish。首发尚无包设置入口时，可由包所有者提供限定权限的NPM_TOKEN仓库secret用于首次发布；随后配置六个包的可信发布者并移除该token。不要把token写进源码或提交记录。
- npm使用GitHub托管Node24运行环境，可信发布要求npm至少11.5.1及Node至少22.14。

配置依据：[npm可信发布](https://docs.npmjs.com/trusted-publishers/)、[PyPI可信发布](https://docs.pypi.org/trusted-publishers/using-a-publisher/)。账号拥有者的授权和站点配置不能由仓库文件代替。

## 正式发布与重试

确认演练成功且发布账号已配置后，以相同run ID设置publish=true。依次发布五个npm平台包、npm主包，最后通过PyPI官方action上传wheel。没有重新编译，使用通过矩阵测试的原工件。

发布中断后可重跑同一候选。npm比较注册表SHA-512，PyPI比较每个文件SHA-256；仅相同内容可跳过。冲突立即失败，不覆盖、不自动换版本、不撤回已有包。已发布部分保留并按相同候选补传。网络错误不会当作包不存在。

正式上传后，工作流下载官方注册表中的11个压缩包核对候选哈希，并保存registry-verification.json。随后五个平台独立runner从PyPI/npm固定版本公开安装，Python禁止源码构建、npm禁用安装脚本，再执行基础请求、TLS、流式、上传和WebSocket测试（Python3.13/Node24）。候选构建CI另覆盖Python3.10–3.14与Node22/24。注册表一致性和公开安装均通过后才可标记本轮发布验收完成。


## 仅发布 PyPI

PyPI Pending Publisher 配置完成后，无需 npm 账号。运行入口选择 `registry=pypi`，先 `publish=false` 演练，通过后再用同一候选 `publish=true`。npm 发布、npm 注册表归档核验均跳过；只上传五个 wheel，并从 PyPI 下载核对字节。

五个平台的公开安装测试从 PyPI 安装 Python 包；Node 测试伴随包来自该候选的已审计 GitHub 工件，以保留跨语言握手比较。此时不能把 Node 测试称为 npm 公开安装成功。`registry=npm` 时对称处理：Node 从 npm 安装，Python 测试伴随包来自 GitHub 工件；`both` 时两者均从官方注册表安装。

Node 用户暂时按 README 下载 GitHub 工件安装，不需要 npm 账号。正式发布某一语言后，应分别更新其安装说明，不能将另一语言也标为已发布。
