# Python 使用教程

适用于 `tlsurl 0.1.0`，Python 3.10–3.14。本文使用已发布的原生包，不需要编译 Rust。

[文档索引](README.md) · [返回首页](../README.md) · [Node.js 教程](node-tutorial.md) · [完整 API 与协议说明](native-bindings.md)

## 章节目录

1. [安装](#install)
2. [简单请求](#simple)
3. [Header 与参数](#headers-params)
4. [复杂请求](#complex)
5. [表单与正文](#body)
6. [连续请求](#session)
7. [Cookie（CK）](#cookies)
8. [引用自带的浏览器指纹](#profiles)
9. [自定义 TLS 指纹](#custom-tls)
10. [随机 TLS 指纹（JA3/JA4）](#random-tls)
11. [异步与并发请求](#concurrency)
12. [文件上传与流式下载](#files)
13. [错误、超时与代理](#errors)

<a id="install"></a>

## 安装

建议在虚拟环境中执行：

```shell
python -m pip install --only-binary=:all: --index-url https://pypi.org/simple tlsurl==0.1.0
```

下面每个 Python 代码块可单独保存成 `.py` 文件运行。请求示例使用公开的 HTTP 回显服务 `https://httpbin.org`，用于展示发送内容；实际业务请替换 URL、凭据和字段。该示例服务的可用性不属于 tlsurl 的保证。文件上传需先准备示例文件，代理示例需已有代理服务。

<a id="simple"></a>

## 简单请求

```python
from tlsurl import Client

with Client() as client:
    response = client.get("https://httpbin.org/get")
    response.raise_for_status()
    print(response.status)        # HTTP 状态码
    print(response.url)           # 重定向后的最终 URL
    print(response.http_version)  # 实际 HTTP 版本
    print(response.json())        # 仅在响应正文为 JSON 时使用
    print(response.text())        # 默认按 UTF-8 解码
    print(len(response.body))     # 原始 bytes 长度
```

`with` 结束自动关闭客户端。已缓冲的响应正文可以反复读取。HTML/图片响应不要调用 `json()`；图片等二进制数据使用 `body`。

只有 `get()`、`post()` 提供快捷方法，其他方法使用 `request()`：

```python
from tlsurl import Client

with Client() as client:
    response = client.request("PATCH", "https://httpbin.org/anything", json={"enabled": True})
    response.raise_for_status()
    print(response.json())
```

<a id="headers-params"></a>

## Header 与参数

普通 Header 用字典；需要同名重复字段时使用元组列表。`params` 是 URL 查询参数，不是请求正文；键和值使用字符串。

```python
from tlsurl import Client

common_headers = {"User-Agent": "my-python-app/1.0", "Accept": "application/json"}
with Client() as client:
    response = client.get(
        "https://httpbin.org/get?source=tutorial",
        headers={**common_headers, "X-Request-Id": "demo-001", "Referer": "https://example.com/"},
        params=[("q", "中文 空格"), ("page", "1"), ("tag", "python"), ("tag", "tls")],
    )
    response.raise_for_status()
    print(response.json())
    for name, value in response.headers:
        print(name, value.decode("latin-1"))  # 响应 Header 的值是 bytes

    repeated = client.get(
        "https://httpbin.org/headers",
        headers=[("Accept", "application/json"), ("X-Demo", "one"), ("X-Demo", "two")],
    )
    repeated.raise_for_status()
    print(repeated.json())
```

- 简单查询也可写 `params={"page": "1", "size": "20"}`。重复键用列表，不能靠字典保存。
- 参数会自动编码并追加到 URL；已有 `?page=1` 时再传 `page=2` 会形成两个值，不是替换。
- Header 值可用 `str` 或 `bytes`。不要把含换行的完整浏览器请求头直接作为一个值。
- `Client(headers=...)` 不是当前 API；复用上面的 `common_headers` 字典，按请求合并即可。默认 UA 可通过 `Client(user_agent="my-app/1.0")` 设置。
- HTTP/2 会规范化 Header 名称；传入列表不代表任意线上字节顺序都能保持。

<a id="complex"></a>

## 复杂请求

同一次 POST 可组合：查询参数、JSON 正文、Header、Bearer 认证、超时和重定向策略。

```python
from tlsurl import Client

with Client(timeout_ms=15000, connect_timeout_ms=5000, max_redirects=5) as client:
    response = client.post(
        "https://httpbin.org/post",
        params={"source": "desktop", "page": "1"},
        headers={"Accept": "application/json", "X-Trace-Id": "demo-002"},
        json={"name": "测试", "items": [{"id": 1, "enabled": True}]},
        bearer_token="demo-token",  # 替换为自己的业务 Token
        timeout_ms=10000,           # 此请求覆盖客户端总超时
        max_redirects=0,            # 此请求不自动跟随重定向
    )
    response.raise_for_status()
    print(response.json())
```

`json=` 自动序列化并在未指定时添加 `Content-Type: application/json`。Basic 认证改用 `basic_auth=("username", "password")`；Bearer、Basic、手写 `Authorization` 三选一，不要混用。参数 Token 只负责构造请求头，不自动获取或刷新登录凭据。

<a id="body"></a>

## 表单与正文

```python
from tlsurl import Client

with Client() as client:
    form_response = client.post(
        "https://httpbin.org/post",
        form=[("name", "demo"), ("tag", "a"), ("tag", "b")],
    )
    form_response.raise_for_status()
    print(form_response.json())

    raw_response = client.post(
        "https://httpbin.org/post",
        headers={"Content-Type": "application/octet-stream"},
        body=b"\x00\x01\x02hello",
    )
    raw_response.raise_for_status()
    print(raw_response.json())
```

`form` 为 URL 编码表单，会自动设置对应 Content-Type。`body` 为原始字符串或字节。**`json`、`form`、`body`、`body_file`、`multipart` 每次只能选一个**；它们都可以与 `params` 同时使用。Multipart 不要手写 boundary。

<a id="session"></a>

## 连续请求

同一会话复用一个 Client，可保留 Cookie 和连接池。下面先接收服务器的 Set-Cookie，再发送后续请求：

```python
from tlsurl import Client

with Client() as client:
    first = client.get("https://httpbin.org/cookies/set", params={"session": "demo-session"})
    first.raise_for_status()

    second = client.get("https://httpbin.org/cookies")
    second.raise_for_status()
    print(second.json())

    for page in range(1, 4):
        response = client.get("https://httpbin.org/get", params={"page": str(page)})
        response.raise_for_status()
        print(page, response.status)
```

真实业务中把第一步换为登录接口，后续请求保持使用同一 Client。库只管理服务端 Cookie；返回在 JSON 里的 access token 需要自己读取，再通过 `bearer_token` 传入。不同账号使用不同 Client，避免共享 Cookie。不要在每次循环后关闭还要继续使用的 Client。

<a id="cookies"></a>

## Cookie（CK）

CK 通常指 Cookie。有三种用法：自动管理服务端 Set-Cookie、手工写入 Cookie 存储、发送原始 Cookie Header。

手工写入存储，每次传入**一条 Set-Cookie 格式**的内容：

```python
from tlsurl import Client

url = "https://httpbin.org/cookies"
with Client() as client:
    client.set_cookie(url, "session=demo-session; Path=/; Secure; HttpOnly")
    client.set_cookie(url, "theme=dark; Path=/; Secure")
    print(client.cookies(url))  # [(name, value), ...]，只返回匹配此 URL 的项
    response = client.get(url)
    response.raise_for_status()
    print(response.json())

    client.set_cookie(url, "theme=; Max-Age=0; Path=/; Secure")  # 删除同路径 Cookie
    client.clear_cookies()  # 清空此 Client 的整个 Cookie 存储
```

粘贴已有的 `name=value; name2=value2` 字符串，则使用请求头：

```python
from tlsurl import Client

with Client(cookies=False) as client:
    response = client.get(
        "https://httpbin.org/cookies",
        headers={"Cookie": "session=demo-session; theme=dark"},
    )
    response.raise_for_status()
    print(response.json())
```

原始 Cookie Header 不包含 `Path`、`Domain`、`Secure` 等属性，也不会被导入 Cookie 存储。这里关闭自动 Cookie，避免手工 Header 与自动存储混用。`set_cookie()` 中的 URL 必须对应目标站点；域、路径、Secure、过期规则仍生效，HTTP 来源不能写入 Secure Cookie。读取/打印真实 Cookie 可能包含登录凭据，示例值只是演示。

<a id="profiles"></a>

## 引用自带的浏览器指纹

```python
from tlsurl import Client, available_profiles

profiles = available_profiles()
print(profiles)  # 以当前安装包实际返回的名称为准
assert "chrome_149" in profiles
with Client(profile="chrome_149", platform="windows") as client:
    response = client.get("https://httpbin.org/get")
    response.raise_for_status()
    print(response.status, response.http_version)
```

预设还包括 `firefox_151`、`safari_26.4` 等。`platform` 支持 `windows/macos/linux/android/ios`，影响预设 Header；它不是安装包平台选择，也不要求与本机系统一致。省略时使用上游默认 `macos`。

预设包含 TLS、HTTP/2 和 Header 配置。只改 User-Agent 不会把 TLS 指纹变成对应浏览器。预设不代表运行了真实浏览器，也不会执行网页 JavaScript。

需要保留预设大部分设置、只覆盖部分字段时，可以使用：

```python
from tlsurl import Client

with Client(
    profile="chrome_149",
    platform="windows",
    tls={"max_version": "1.2"},
    http2={"initial_window_size": 1048576},
) as client:
    response = client.get("https://httpbin.org/get")
    response.raise_for_status()
    print(response.status)
```

显式字段覆盖对应预设字段，其他字段保留；覆盖后不能再认为它与原预设指纹完全一致。

<a id="custom-tls"></a>

## 自定义 TLS 指纹

```python
from tlsurl import Client

with Client(tls={
    "min_version": "1.2",
    "max_version": "1.3",
    "alpn": ["h2", "http/1.1"],
    "cipher_list": "ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES128-GCM-SHA256",
    "curves_list": "X25519:P-256:P-384",
    "sigalgs_list": "ecdsa_secp256r1_sha256:rsa_pss_rsae_sha256:rsa_pkcs1_sha256",
    "grease": True,
    "permute_extensions": False,
    "sni": True,
}) as client:
    response = client.get("https://httpbin.org/get")
    response.raise_for_status()
    print(response.status, response.http_version)
```

列表字符串采用 BoringSSL 格式，不是 JA3 原始数字串。TLS 1.3 套件仍受底层默认规则影响，不能把 `cipher_list` 当作整个 ClientHello。ALPN 只支持 h2/http/1.1，强制 `http_version="1.1"` 或 `"2"` 时优先于 ALPN 配置。

JA3/JA4 是服务端从实际 ClientHello 计算的摘要；没有 `ja3="哈希"`、`ja4="哈希"` 这样的设置接口。修改这些参数可能改变指纹，也可能降低目标服务器兼容性。不要通过关闭证书校验来解决指纹配置错误。

<a id="random-tls"></a>

## 随机 TLS 指纹（JA3/JA4）

一键开启，不需要手工填写套件：

```python
from tlsurl import Client

with Client(random_tls=True) as client:
    response = client.get("https://httpbin.org/get")
    response.raise_for_status()
    print(response.status)
```

同一会话稳定使用一组配置，并用种子复现：

```python
from tlsurl import Client

with Client(random_tls=True, random_tls_seed=42) as client:
    for page in (1, 2):
        response = client.get("https://httpbin.org/get", params={"page": str(page)})
        response.raise_for_status()
        print(response.status)
```

需要每次请求重新随机，就显式新建无种子的客户端：

```python
from tlsurl import Client

for _ in range(3):
    with Client(random_tls=True) as client:
        response = client.get("https://httpbin.org/get")
        response.raise_for_status()
        print(response.status)
```

每个 Client 只生成一次配置，不是每次请求或每条新连接都换配置。新建 Client 也会失去旧 Client 的 Cookie 和连接池，适合独立请求；需要连续登录会话时优先复用 Client。

随机模式使用 TLS 1.2/1.3，随机套件组合、套件/曲线/签名算法排列，实际 JA3 和 JA4 均有握手测试覆盖。种子范围 `0..4294967295`，必须同时启用 `random_tls=True`。同版本、相同 SNI/ALPN 条件下可复现配置；TLS 密钥仍安全随机。不同种子不保证绝不碰撞，升级底层库后不保证哈希不变。

**`random_tls=True` 与 `tls`、`profile`、`platform` 互斥**；可以搭配 Header、Cookie、代理、CA、超时和 HTTP/2 参数。仅打乱扩展顺序不保证改变 JA4。随机配置不等同于真实浏览器预设。

<a id="concurrency"></a>

## 异步与并发请求

异步顺序请求仍然逐个 `await`；独立请求可以 `gather` 并发。下面一次仅发三个请求，并等所有结果返回后关闭客户端：

```python
import asyncio
from tlsurl import AsyncClient

async def main():
    async with AsyncClient(random_tls=True) as client:
        first = await client.get("https://httpbin.org/get", params={"step": "first"})
        first.raise_for_status()
        results = await asyncio.gather(
            *(client.get("https://httpbin.org/get", params={"page": str(n)}) for n in range(1, 4)),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                print("请求失败:", result)
            else:
                result.raise_for_status()
                print(result.status)

asyncio.run(main())
```

登录、刷新令牌等有先后依赖的操作不要并发。大量 URL 应分批或用 `asyncio.Semaphore` 控制并发数量；同一个 AsyncClient 的并发请求共享 Cookie。同步 `Client.get()` 不要放到事件循环中当作异步调用。

<a id="files"></a>

## 文件上传与流式下载

先在工作目录准备 `demo.txt`；它作为普通文件上传，不会预先整体读入 Python 内存：

```python
from tlsurl import Client

with Client() as client:
    response = client.post("https://httpbin.org/post", multipart=[
        {"name": "title", "data": "demo"},
        {"name": "attachment", "file": "demo.txt", "filename": "demo.txt", "content_type": "text/plain"},
    ])
    response.raise_for_status()
    print(response.status)
```

上传原始文件改用 `client.post(url, body_file="demo.txt")`，不要与 multipart 同时传入，也不要手工设置文件上传的 Content-Length/Transfer-Encoding。文件上传遇到需保留正文的 307/308 不自动重传，返回响应供调用者处理。

流式下载会写入当前目录的 `download.bin`：

```python
from tlsurl import Client

with Client() as client:
    with client.stream("GET", "https://httpbin.org/bytes/1024") as response:
        response.raise_for_status()
        with open("download.bin", "wb") as output:
            for chunk in response:
                output.write(chunk)
```

默认缓冲响应上限为 16 MiB，流式下载不使用这个累计上限；下载大小限制需业务自行控制。提前退出循环仍应关闭响应。异步流式及 WebSocket 见 [API 文档](native-bindings.md#流式响应与取消)。

<a id="errors"></a>

## 错误、超时与代理

```python
from tlsurl import Client, Error

try:
    with Client(timeout_ms=10000, connect_timeout_ms=3000, read_timeout_ms=5000) as client:
        response = client.get("https://httpbin.org/status/404")
        response.raise_for_status()  # 不调用时 404/500 也会正常返回 Response
except Error as error:
    print(error.code, str(error))
```

超时单位都是毫秒，正整数。请求 `timeout_ms` 覆盖客户端总超时，流式请求的超时也覆盖正文读取。常见错误码：`HTTP_STATUS`、`TIMEOUT`、`TLS`、`CONNECT`、`DNS`、`INVALID_CONFIG`、`INVALID_REQUEST`、`FILE_IO`、`BODY_TOO_LARGE`、`CLOSED`、`CANCELLED`。JSON 解析失败是 Python 原生 JSON 异常，不是 `tlsurl.Error`。库不自动重试业务请求，尤其不要盲目重试有副作用的 POST。

已有本地代理时这样配置（将端口替换为自己的）：

```python
from tlsurl import Client

with Client(proxy="http://127.0.0.1:7890", timeout_ms=10000) as client:
    response = client.get("https://httpbin.org/get")
    response.raise_for_status()
    print(response.status)
```

默认不读取系统代理。自定义 CA 使用 `ca_pem=Path("ca.pem").read_text()`（先 `from pathlib import Path`），传 PEM 内容而不是路径；它替换默认信任库。证书校验默认开启。
