from __future__ import annotations

import ctypes
import json
import os
import re
from ctypes import wintypes
from functools import lru_cache
from typing import Mapping


SERVICE_PREFIX = "FloatingVoiceButton/CloudASR"
_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_ERROR_NOT_FOUND = 1168
_MAX_CREDENTIAL_BYTES = 2560
_PROVIDER_PATTERN = re.compile(r"^[a-z0-9_-]{1,32}$")


class CredentialStoreError(RuntimeError):
    """Windows 凭据管理器操作失败。"""


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", wintypes.LPVOID),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


@lru_cache(maxsize=1)
def _credential_api():
    if os.name != "nt":
        raise CredentialStoreError("当前系统不支持 Windows 凭据管理器。")
    api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    api.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
    api.CredWriteW.restype = wintypes.BOOL
    api.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
    ]
    api.CredReadW.restype = wintypes.BOOL
    api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    api.CredDeleteW.restype = wintypes.BOOL
    api.CredFree.argtypes = [wintypes.LPVOID]
    api.CredFree.restype = None
    return api


def _normalize_provider(provider: str) -> str:
    normalized = str(provider or "").strip().lower()
    if not _PROVIDER_PATTERN.fullmatch(normalized):
        raise ValueError("在线识别服务标识无效。")
    return normalized


def credential_target(provider: str) -> str:
    return f"{SERVICE_PREFIX}/{_normalize_provider(provider)}"


def _windows_error(action: str) -> CredentialStoreError:
    error_code = ctypes.get_last_error()
    return CredentialStoreError(f"{action}失败（Windows 错误码：{error_code}）。")


def _write_raw(target: str, username: str, payload: bytes) -> None:
    if len(payload) > _MAX_CREDENTIAL_BYTES:
        raise CredentialStoreError("凭据信息过长，无法保存到 Windows 凭据管理器。")
    api = _credential_api()
    buffer = ctypes.create_string_buffer(payload)
    credential = _CREDENTIALW()
    credential.Type = _CRED_TYPE_GENERIC
    credential.TargetName = target
    credential.Comment = "悬浮语音按钮在线识别凭据"
    credential.CredentialBlobSize = len(payload)
    credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = username
    if not api.CredWriteW(ctypes.byref(credential), 0):
        raise _windows_error("保存在线识别凭据")


def _read_raw(target: str) -> bytes | None:
    api = _credential_api()
    result = ctypes.POINTER(_CREDENTIALW)()
    if not api.CredReadW(target, _CRED_TYPE_GENERIC, 0, ctypes.byref(result)):
        if ctypes.get_last_error() == _ERROR_NOT_FOUND:
            return None
        raise _windows_error("读取在线识别凭据")
    try:
        credential = result.contents
        return ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
    finally:
        api.CredFree(result)


def _delete_raw(target: str) -> bool:
    api = _credential_api()
    if api.CredDeleteW(target, _CRED_TYPE_GENERIC, 0):
        return True
    if ctypes.get_last_error() == _ERROR_NOT_FOUND:
        return False
    raise _windows_error("删除在线识别凭据")


class CredentialStore:
    """把在线识别密钥作为通用凭据保存在当前 Windows 用户下。"""

    def save(self, provider: str, credentials: Mapping[str, object]) -> None:
        normalized_provider = _normalize_provider(provider)
        if not isinstance(credentials, Mapping):
            raise TypeError("凭据必须是字段和值组成的映射。")
        normalized: dict[str, str] = {}
        for raw_key, raw_value in credentials.items():
            key = str(raw_key or "").strip()
            if not key or not _PROVIDER_PATTERN.fullmatch(key):
                raise ValueError("凭据字段名称无效。")
            if raw_value is None:
                continue
            normalized[key] = str(raw_value).strip()
        payload = json.dumps(
            normalized, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        _write_raw(credential_target(normalized_provider), normalized_provider, payload)

    def load(self, provider: str) -> dict[str, str]:
        payload = _read_raw(credential_target(provider))
        if payload is None:
            return {}
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CredentialStoreError("Windows 中保存的在线识别凭据已损坏。") from None
        if not isinstance(decoded, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in decoded.items()
        ):
            raise CredentialStoreError("Windows 中保存的在线识别凭据格式无效。")
        return dict(decoded)

    def delete(self, provider: str) -> bool:
        return _delete_raw(credential_target(provider))

    def exists(self, provider: str) -> bool:
        return _read_raw(credential_target(provider)) is not None


_DEFAULT_STORE = CredentialStore()


def save_credentials(provider: str, credentials: Mapping[str, object]) -> None:
    _DEFAULT_STORE.save(provider, credentials)


def load_credentials(provider: str) -> dict[str, str]:
    return _DEFAULT_STORE.load(provider)


def delete_credentials(provider: str) -> bool:
    return _DEFAULT_STORE.delete(provider)


def has_credentials(provider: str) -> bool:
    return _DEFAULT_STORE.exists(provider)
