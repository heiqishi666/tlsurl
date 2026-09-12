# 第三方许可证来源

这些补充文件用于 crate 压缩包未携带许可证原文的情况。每个目录按 crate 名称和版本区分，SOURCE.md 记录发布包 `.cargo_vcs_info.json` 对应的源码提交、文件地址和原文 SHA-256。保留原始文本，不以项目自身 Apache-2.0 许可证覆盖依赖条款。

完整汇编见 `docs/THIRD_PARTY_LICENSES.txt`，包含两种绑定在五个发布目标上的普通依赖及构建依赖。包含某项不代表它必然链接到每个平台工件；这是保守的文本集合。许可证文本来自锁定的 crate 内容及上述补充文件，不对依赖重新授权。

依赖升级后重新生成：

```sh
python scripts/license_inventory.py --output dist/license-inventory.json --bundle docs/THIRD_PARTY_LICENSES.txt
```

缺少文本时汇编命令失败，先补查对应版本来源。清单记录的 crate 内路径在注册表源码目录下；补充项的 LICENSE 位于本目录对应版本子目录，本地 crate 使用项目 LICENSE。
