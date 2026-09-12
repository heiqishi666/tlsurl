# 预编译包发布

入口为 `.github/workflows/publish-native.yml`，仅手动触发。默认 `publish=false`，只校验工件、PyPI已发布内容并执行npm dry-run；不会上传。普通push及上游release-plz不会触发这个发布入口。

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

工作流成功仍须进行官方仓库公开安装验收：在干净环境固定该版本安装wheel和npm包，禁用源码构建，检查实际平台二进制及基础请求。还需下载注册表工件并核对候选哈希；未完成这些步骤前不标为正式交付完成。
