"""Public configuration types; importing these requires no extra dependency."""
from os import PathLike
from typing import Literal, Mapping, TypedDict

Headers = list[tuple[str, str | bytes]] | Mapping[str, str | bytes]
Pairs = list[tuple[str, str]] | Mapping[str, str]
FilePath = str | PathLike[str]
TlsVersion = Literal["1.0", "1.1", "1.2", "1.3"]
Platform = Literal["windows", "macos", "linux", "android", "ios"]
HttpVersion = Literal["auto", "1.1", "2"]


class TlsOptions(TypedDict, total=False):
    min_version: TlsVersion
    max_version: TlsVersion
    alpn: list[Literal["h2", "http/1.1"]]
    cipher_list: str
    curves_list: str
    sigalgs_list: str
    grease: bool
    permute_extensions: bool
    sni: bool


class Http2Options(TypedDict, total=False):
    initial_window_size: int
    initial_connection_window_size: int
    max_frame_size: int
    max_header_list_size: int
    header_table_size: int
    enable_push: bool
    pseudo_order: list[Literal["method", "path", "authority", "scheme"]]


class Identity(TypedDict):
    certificate_pem: str
    private_key_pem: str


class _PartMetadata(TypedDict, total=False):
    filename: str
    content_type: str


class MultipartData(_PartMetadata):
    name: str
    data: str | bytes


class MultipartFile(_PartMetadata):
    name: str
    file: FilePath


MultipartPart = MultipartData | MultipartFile
