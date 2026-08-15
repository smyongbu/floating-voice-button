from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import io
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from datetime import datetime, timezone
from email.utils import formatdate
from typing import Callable, Mapping

from credential_store import CredentialStore


SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2
CHANNELS = 1
MAX_AUDIO_SECONDS = 55
MAX_PCM_BYTES = SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS * MAX_AUDIO_SECONDS

_PROVIDER_CATALOG = {
    "volcengine": {
        "id": "volcengine",
        "name": "火山引擎",
        "service": "大模型录音文件极速版",
        "upload_mode": "整段上传",
        "max_seconds": MAX_AUDIO_SECONDS,
        "credential_fields": [
            {"key": "app_key", "label": "应用密钥", "required": True, "secret": True},
            {
                "key": "access_key",
                "label": "访问密钥（旧版账号）",
                "required": False,
                "secret": True,
            },
        ],
    },
    "iflytek": {
        "id": "iflytek",
        "name": "科大讯飞",
        "service": "语音听写（流式版）",
        "upload_mode": "按录音时长分帧上传",
        "max_seconds": MAX_AUDIO_SECONDS,
        "credential_fields": [
            {"key": "app_id", "label": "应用编号", "required": True, "secret": True},
            {"key": "api_key", "label": "接口密钥", "required": True, "secret": True},
            {"key": "api_secret", "label": "接口密钥密码", "required": True, "secret": True},
        ],
    },
    "tencent": {
        "id": "tencent",
        "name": "腾讯云",
        "service": "一句话识别",
        "upload_mode": "整段上传",
        "max_seconds": MAX_AUDIO_SECONDS,
        "credential_fields": [
            {"key": "secret_id", "label": "密钥编号", "required": True, "secret": True},
            {"key": "secret_key", "label": "密钥", "required": True, "secret": True},
        ],
    },
    "aliyun": {
        "id": "aliyun",
        "name": "阿里云",
        "service": "一句话识别",
        "upload_mode": "整段上传",
        "max_seconds": MAX_AUDIO_SECONDS,
        "credential_fields": [
            {"key": "app_key", "label": "项目密钥", "required": True, "secret": True},
            {"key": "access_key_id", "label": "访问密钥编号", "required": True, "secret": True},
            {"key": "access_key_secret", "label": "访问密钥", "required": True, "secret": True},
        ],
    },
}

VOLCENGINE_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
TENCENT_URL = "https://asr.tencentcloudapi.com/"
IFLYTEK_HOST = "iat-api.xfyun.cn"
IFLYTEK_PATH = "/v2/iat"
IFLYTEK_URL = f"wss://{IFLYTEK_HOST}{IFLYTEK_PATH}"
ALIYUN_TOKEN_URL = "https://nls-meta.cn-shanghai.aliyuncs.com/"
ALIYUN_ASR_URL = "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/asr"


class CloudAsrError(RuntimeError):
    """在线识别失败，但异常文本不携带密钥、音频或识别正文。"""


class CloudAsrConfigurationError(CloudAsrError):
    pass


class CloudAsrRequestError(CloudAsrError):
    """可安全交给路由器判断是否允许自动回退的在线请求错误。"""

    CATEGORIES = frozenset({"transient", "authentication", "quota", "parameter", "remote"})

    def __init__(self, message: str, *, category: str = "remote") -> None:
        normalized = str(category or "remote").strip().lower()
        if normalized not in self.CATEGORIES:
            normalized = "remote"
        super().__init__(message)
        self.category = normalized


def get_provider_catalog() -> list[dict]:
    """返回可直接给设置界面使用的在线服务目录副本。"""
    return [copy.deepcopy(item) for item in _PROVIDER_CATALOG.values()]


def get_provider(provider: str) -> dict:
    normalized = str(provider or "").strip().lower()
    try:
        return copy.deepcopy(_PROVIDER_CATALOG[normalized])
    except KeyError as exc:
        raise CloudAsrConfigurationError("不支持所选的在线语音识别服务。") from None


def validate_credentials(provider: str, credentials: Mapping[str, object]) -> dict[str, str]:
    catalog = get_provider(provider)
    if not isinstance(credentials, Mapping):
        raise CloudAsrConfigurationError("在线识别凭据格式无效。")
    allowed = {field["key"] for field in catalog["credential_fields"]}
    if {str(key) for key in credentials} - allowed:
        raise CloudAsrConfigurationError("在线识别凭据包含不支持的字段。")
    normalized = {key: str(credentials.get(key) or "").strip() for key in allowed}
    missing_labels = [
        field["label"]
        for field in catalog["credential_fields"]
        if field["required"] and not normalized[field["key"]]
    ]
    if missing_labels:
        raise CloudAsrConfigurationError(
            f"{catalog['name']}缺少必要凭据：{'、'.join(missing_labels)}。"
        )
    return normalized


def _validate_pcm(pcm: bytes, sample_rate: int) -> bytes:
    if not isinstance(pcm, (bytes, bytearray, memoryview)):
        raise TypeError("录音数据必须是 16 位 PCM 字节。")
    raw = bytes(pcm)
    if not raw:
        return b""
    if int(sample_rate) != SAMPLE_RATE:
        raise CloudAsrConfigurationError("在线识别只接受 16000 Hz 的录音。")
    if len(raw) % SAMPLE_WIDTH:
        raise CloudAsrConfigurationError("录音数据不是完整的 16 位 PCM 采样。")
    if len(raw) > MAX_PCM_BYTES:
        raise CloudAsrConfigurationError(
            f"在线识别每次录音不能超过 {MAX_AUDIO_SECONDS} 秒。"
        )
    return raw


def _pcm_to_wav(pcm: bytes) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(CHANNELS)
        target.setsampwidth(SAMPLE_WIDTH)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(pcm)
    return output.getvalue()


def _json_bytes(payload: Mapping) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _header(headers, name: str) -> str:
    if headers is None:
        return ""
    value = headers.get(name) if hasattr(headers, "get") else None
    if value is not None:
        return str(value)
    lowered = name.lower()
    for key, candidate in getattr(headers, "items", lambda: [])():
        if str(key).lower() == lowered:
            return str(candidate)
    return ""


def _diagnostic_id(headers) -> str:
    for name in ("X-Tt-Logid", "X-Api-Request-Id", "X-Request-Id"):
        value = _header(headers, name)
        if value:
            return value.replace("\r", " ").replace("\n", " ")[:128]
    return ""


def _category_for_remote_code(code: object) -> str:
    normalized = str(code or "").strip().lower().replace("_", "").replace("-", "")
    if normalized.startswith("http"):
        digits = "".join(character for character in normalized if character.isdigit())
        status = int(digits[:3]) if len(digits) >= 3 else 0
        if status in {401, 403}:
            return "authentication"
        if status == 429:
            return "quota"
        if status in {408, 425} or 500 <= status <= 599:
            return "transient"
        if status == 400 or status == 422:
            return "parameter"
        return "remote"
    if normalized.isdigit():
        numeric_categories = {
            # 阿里云短语音 REST 状态码。
            "40000001": "authentication",
            "40000002": "parameter",
            "40000003": "parameter",
            "40000004": "transient",
            "40000005": "quota",
            "41010101": "parameter",
            # 科大讯飞语音听写常见错误码。
            "10005": "authentication",
            "10010": "authentication",
            "10110": "authentication",
            "11200": "quota",
            "11201": "quota",
            "11202": "quota",
            "11203": "quota",
            "10014": "transient",
            "10019": "transient",
            "10114": "transient",
            "10200": "transient",
            "10500": "transient",
            "10600": "transient",
            "10700": "transient",
            "10006": "parameter",
            "10007": "parameter",
            "10009": "parameter",
            "10043": "parameter",
            "10044": "parameter",
            "10047": "parameter",
            "10050": "parameter",
            "10101": "parameter",
            "10109": "parameter",
            "10139": "parameter",
            "10303": "parameter",
            "10313": "parameter",
            "10317": "parameter",
            "10404": "parameter",
        }
        if normalized in numeric_categories:
            return numeric_categories[normalized]
        if len(normalized) >= 8 and normalized.startswith("5"):
            return "transient"
    authentication_markers = (
        "auth", "signature", "credential", "accessdenied", "forbidden",
        "unauthorized", "tokeninvalid", "invalidtoken", "secretidnotfound",
    )
    quota_markers = (
        "quota", "balance", "arrears", "billing", "nofreeamount", "insufficient",
        "limitexceeded", "ratelimit", "requestlimit", "throttl",
    )
    parameter_markers = (
        "invalidparameter", "parametererror", "badrequest", "unsupported",
        "invalidformat", "invalidaudio", "emptyaudio",
    )
    transient_markers = ("timeout", "internalerror", "unavailable", "servicebusy", "servererror")
    if any(marker in normalized for marker in authentication_markers):
        return "authentication"
    if any(marker in normalized for marker in quota_markers):
        return "quota"
    if any(marker in normalized for marker in parameter_markers):
        return "parameter"
    if any(marker in normalized for marker in transient_markers):
        return "transient"
    return "remote"


def _safe_remote_error(
    provider_name: str,
    code: object,
    diagnostic_id: str = "",
    *,
    category: str | None = None,
) -> CloudAsrRequestError:
    safe_code = str(code or "未知").replace("\r", " ").replace("\n", " ")[:80]
    safe_diagnostic_id = str(diagnostic_id or "").replace("\r", " ").replace("\n", " ")[:128]
    suffix = f"，诊断编号：{safe_diagnostic_id}" if safe_diagnostic_id else ""
    return CloudAsrRequestError(
        f"{provider_name}识别失败（错误码：{safe_code}{suffix}）。",
        category=category or _category_for_remote_code(code),
    )


class CloudAsrRecognizer:
    """四家在线语音识别的统一适配器。"""

    def __init__(
        self,
        provider: str,
        *,
        credentials: Mapping[str, object] | None = None,
        credential_store: CredentialStore | None = None,
        timeout: float = 30.0,
        run_logger: logging.Logger | None = None,
        error_logger: logging.Logger | None = None,
        urlopen: Callable | None = None,
        websocket_factory: Callable | None = None,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
        uuid_factory: Callable[[], object] | None = None,
    ) -> None:
        self.provider = get_provider(provider)["id"]
        self._credentials_override = dict(credentials) if credentials is not None else None
        self.credential_store = credential_store or CredentialStore()
        self.timeout = max(1.0, float(timeout))
        self.run_logger = run_logger
        self.error_logger = error_logger
        self._urlopen = urlopen or urllib.request.urlopen
        self._websocket_factory = websocket_factory
        self._sleep = sleep or time.sleep
        self._clock = clock or time.time
        self._uuid_factory = uuid_factory or uuid.uuid4
        self._aliyun_token_cache: tuple[str, int, str] | None = None

    def _credentials(self) -> dict[str, str]:
        source = (
            self._credentials_override
            if self._credentials_override is not None
            else self.credential_store.load(self.provider)
        )
        return validate_credentials(self.provider, source)

    def transcribe_pcm16(self, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> str:
        raw = _validate_pcm(pcm, sample_rate)
        if not raw:
            return ""
        operation_id = str(self._uuid_factory()).replace("-", "")[:12]
        started = self._clock()
        duration_ms = len(raw) * 1000 // (SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS)
        if self.run_logger:
            self.run_logger.info(
                "在线识别开始 | 编号=%s | 服务=%s | 时长毫秒=%s",
                operation_id, self.provider, duration_ms,
            )
        try:
            credentials = self._credentials()
            text = str(
                getattr(self, f"_transcribe_{self.provider}")(raw, credentials) or ""
            ).strip()
            if self.run_logger:
                elapsed_ms = max(0, int((self._clock() - started) * 1000))
                self.run_logger.info(
                    "在线识别完成 | 编号=%s | 服务=%s | 耗时毫秒=%s | 字数=%s",
                    operation_id, self.provider, elapsed_ms, len(text),
                )
            return text
        except CloudAsrError as exc:
            if self.error_logger:
                self.error_logger.warning(
                    "在线识别失败 | 编号=%s | 服务=%s | 原因=%s",
                    operation_id, self.provider, str(exc),
                )
            raise
        except Exception as exc:
            if self.error_logger:
                # 不写异常正文或堆栈，避免第三方库把鉴权 URL 写入日志。
                self.error_logger.error(
                    "在线识别异常 | 编号=%s | 服务=%s | 异常类型=%s",
                    operation_id, self.provider, type(exc).__name__,
                )
            raise CloudAsrRequestError("在线识别发生未预期错误，请查看服务状态后重试。") from None

    def _open_json(self, request: urllib.request.Request, provider_name: str):
        try:
            response = self._urlopen(request, timeout=self.timeout)
            try:
                raw = response.read()
                headers = response.headers
                status = getattr(response, "status", None)
                if status is None and hasattr(response, "getcode"):
                    status = response.getcode()
            finally:
                close = getattr(response, "close", None)
                if close:
                    close()
        except urllib.error.HTTPError as exc:
            raise _safe_remote_error(
                provider_name, f"HTTP {exc.code}", _diagnostic_id(exc.headers)
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise CloudAsrRequestError(
                f"无法连接{provider_name}，请检查网络后重试。",
                category="transient",
            ) from None
        if status is not None and not 200 <= int(status) < 300:
            raise _safe_remote_error(provider_name, f"HTTP {status}", _diagnostic_id(headers))
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CloudAsrRequestError(f"{provider_name}返回了无法解析的数据。") from None
        if not isinstance(payload, dict):
            raise CloudAsrRequestError(f"{provider_name}返回的数据格式无效。")
        return payload, headers

    def _transcribe_volcengine(self, pcm: bytes, credentials: Mapping[str, str]) -> str:
        payload = {
            "user": {"uid": "floating-voice-button"},
            "audio": {"data": base64.b64encode(_pcm_to_wav(pcm)).decode("ascii")},
            "request": {"model_name": "bigmodel", "enable_itn": True, "enable_punc": True},
        }
        headers = {
            "Content-Type": "application/json",
            "X-Api-App-Key": credentials["app_key"],
            "X-Api-Resource-Id": "volc.bigasr.auc_turbo",
            "X-Api-Request-Id": str(self._uuid_factory()),
            "X-Api-Sequence": "-1",
        }
        if credentials.get("access_key"):
            headers["X-Api-Access-Key"] = credentials["access_key"]
        request = urllib.request.Request(
            VOLCENGINE_URL,
            data=_json_bytes(payload),
            headers=headers,
            method="POST",
        )
        result, headers = self._open_json(request, "火山引擎")
        code = _header(headers, "X-Api-Status-Code")
        if code != "20000000":
            raise _safe_remote_error("火山引擎", code, _diagnostic_id(headers))
        return str((result.get("result") or {}).get("text") or "")

    @staticmethod
    def _tencent_authorization(payload: bytes, secret_id: str, secret_key: str, timestamp: int) -> str:
        service = "asr"
        host = "asr.tencentcloudapi.com"
        date = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")
        content_type = "application/json; charset=utf-8"
        canonical_headers = f"content-type:{content_type}\nhost:{host}\n"
        signed_headers = "content-type;host"
        canonical_request = (
            "POST\n/\n\n"
            f"{canonical_headers}\n{signed_headers}\n{hashlib.sha256(payload).hexdigest()}"
        )
        scope = f"{date}/{service}/tc3_request"
        string_to_sign = (
            "TC3-HMAC-SHA256\n"
            f"{timestamp}\n{scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )

        def sign(key: bytes, message: str) -> bytes:
            return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()

        secret_date = sign(("TC3" + secret_key).encode("utf-8"), date)
        secret_service = sign(secret_date, service)
        secret_signing = sign(secret_service, "tc3_request")
        signature = hmac.new(
            secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return (
            "TC3-HMAC-SHA256 "
            f"Credential={secret_id}/{scope}, SignedHeaders={signed_headers}, Signature={signature}"
        )

    def _transcribe_tencent(self, pcm: bytes, credentials: Mapping[str, str]) -> str:
        payload = _json_bytes(
            {
                "EngSerViceType": "16k_zh",
                "SourceType": 1,
                "VoiceFormat": "pcm",
                "Data": base64.b64encode(pcm).decode("ascii"),
                "DataLen": len(pcm),
                "FilterPunc": 0,
                "ConvertNumMode": 1,
            }
        )
        timestamp = int(self._clock())
        request = urllib.request.Request(
            TENCENT_URL,
            data=payload,
            headers={
                "Authorization": self._tencent_authorization(
                    payload, credentials["secret_id"], credentials["secret_key"], timestamp
                ),
                "Content-Type": "application/json; charset=utf-8",
                "Host": "asr.tencentcloudapi.com",
                "X-TC-Action": "SentenceRecognition",
                "X-TC-Version": "2019-06-14",
                "X-TC-Timestamp": str(timestamp),
            },
            method="POST",
        )
        result, _ = self._open_json(request, "腾讯云")
        response = result.get("Response") or {}
        request_id = str(response.get("RequestId") or "")[:128]
        if response.get("Error"):
            raise _safe_remote_error("腾讯云", (response["Error"] or {}).get("Code"), request_id)
        return str(response.get("Result") or "")

    @staticmethod
    def _aliyun_quote(value: object) -> str:
        return urllib.parse.quote(str(value), safe="-_.~")

    def _aliyun_token(self, credentials: Mapping[str, str]) -> str:
        fingerprint = hashlib.sha256(
            (credentials["access_key_id"] + "\0" + credentials["access_key_secret"]).encode("utf-8")
        ).hexdigest()
        now = int(self._clock())
        if self._aliyun_token_cache:
            token, expires_at, cached_fingerprint = self._aliyun_token_cache
            if cached_fingerprint == fingerprint and expires_at > now + 60:
                return token
        parameters = {
            "AccessKeyId": credentials["access_key_id"],
            "Action": "CreateToken",
            "Format": "JSON",
            "RegionId": "cn-shanghai",
            "SignatureMethod": "HMAC-SHA1",
            "SignatureNonce": str(self._uuid_factory()),
            "SignatureVersion": "1.0",
            "Timestamp": datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "Version": "2019-02-28",
        }
        canonicalized = "&".join(
            f"{self._aliyun_quote(key)}={self._aliyun_quote(parameters[key])}"
            for key in sorted(parameters)
        )
        string_to_sign = f"GET&%2F&{self._aliyun_quote(canonicalized)}"
        parameters["Signature"] = base64.b64encode(
            hmac.new(
                (credentials["access_key_secret"] + "&").encode("utf-8"),
                string_to_sign.encode("utf-8"), hashlib.sha1,
            ).digest()
        ).decode("ascii")
        request = urllib.request.Request(
            ALIYUN_TOKEN_URL + "?" + urllib.parse.urlencode(parameters), method="GET"
        )
        result, _ = self._open_json(request, "阿里云")
        token_info = result.get("Token") or {}
        token = str(token_info.get("Id") or "")
        try:
            expires_at = int(token_info.get("ExpireTime") or 0)
        except (TypeError, ValueError):
            expires_at = 0
        if not token or expires_at <= now:
            raise _safe_remote_error(
                "阿里云", result.get("Code") or "TOKEN_INVALID",
                str(result.get("RequestId") or "")[:128],
            )
        self._aliyun_token_cache = (token, expires_at, fingerprint)
        return token

    def _transcribe_aliyun(self, pcm: bytes, credentials: Mapping[str, str]) -> str:
        token = self._aliyun_token(credentials)
        query = urllib.parse.urlencode(
            {
                "appkey": credentials["app_key"],
                "format": "pcm",
                "sample_rate": SAMPLE_RATE,
                "enable_punctuation_prediction": "true",
                "enable_inverse_text_normalization": "true",
                "enable_voice_detection": "true",
            }
        )
        request = urllib.request.Request(
            ALIYUN_ASR_URL + "?" + query,
            data=pcm,
            headers={
                "X-NLS-Token": token,
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(pcm)),
            },
            method="POST",
        )
        result, _ = self._open_json(request, "阿里云")
        if int(result.get("status") or 0) != 20000000:
            raise _safe_remote_error(
                "阿里云", result.get("status"), str(result.get("task_id") or "")[:128]
            )
        return str(result.get("result") or "")

    @staticmethod
    def _iflytek_url(credentials: Mapping[str, str], now: float) -> str:
        date = formatdate(now, usegmt=True)
        origin = f"host: {IFLYTEK_HOST}\ndate: {date}\nGET {IFLYTEK_PATH} HTTP/1.1"
        signature = base64.b64encode(
            hmac.new(
                credentials["api_secret"].encode("utf-8"), origin.encode("utf-8"), hashlib.sha256
            ).digest()
        ).decode("ascii")
        authorization_origin = (
            f'api_key="{credentials["api_key"]}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature}"'
        )
        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("ascii")
        return IFLYTEK_URL + "?" + urllib.parse.urlencode(
            {"authorization": authorization, "date": date, "host": IFLYTEK_HOST}
        )

    def _transcribe_iflytek(self, pcm: bytes, credentials: Mapping[str, str]) -> str:
        factory = self._websocket_factory
        if factory is None:
            try:
                import websocket
            except ImportError as exc:
                raise CloudAsrConfigurationError(
                    "缺少科大讯飞在线识别组件，请重新安装程序依赖。"
                ) from None
            factory = websocket.create_connection
        try:
            connection = factory(self._iflytek_url(credentials, self._clock()), timeout=self.timeout)
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            category = _category_for_remote_code(f"HTTP {status}") if status else "transient"
            raise CloudAsrRequestError(
                "无法连接科大讯飞，请检查网络和凭据后重试。",
                category=category,
            ) from None
        try:
            chunks = [pcm[index:index + 1280] for index in range(0, len(pcm), 1280)]
            for index, chunk in enumerate(chunks):
                data = {
                    "status": 0 if index == 0 else 1,
                    "format": "audio/L16;rate=16000",
                    "encoding": "raw",
                    "audio": base64.b64encode(chunk).decode("ascii"),
                }
                message = {"data": data}
                if index == 0:
                    message["common"] = {"app_id": credentials["app_id"]}
                    message["business"] = {
                        "language": "zh_cn", "domain": "iat", "accent": "mandarin",
                        "ptt": 1, "vad_eos": 10000,
                    }
                connection.send(json.dumps(message, ensure_ascii=False, separators=(",", ":")))
                self._sleep(0.04)
            connection.send('{"data":{"status":2}}')

            pieces: dict[int, str] = {}
            while True:
                try:
                    incoming = json.loads(connection.recv())
                except (json.JSONDecodeError, TypeError, UnicodeDecodeError) as exc:
                    raise CloudAsrRequestError("科大讯飞返回了无法解析的数据。") from None
                if int(incoming.get("code") or 0) != 0:
                    raise _safe_remote_error(
                        "科大讯飞", incoming.get("code"), str(incoming.get("sid") or "")[:128]
                    )
                data = incoming.get("data") or {}
                result = data.get("result") or {}
                words = []
                for segment in result.get("ws") or []:
                    candidates = segment.get("cw") or []
                    if candidates:
                        words.append(str(candidates[0].get("w") or ""))
                if words:
                    pieces[int(result.get("sn") or len(pieces))] = "".join(words)
                if int(data.get("status") or 0) == 2:
                    break
            return "".join(pieces[index] for index in sorted(pieces))
        except CloudAsrError:
            raise
        except Exception as exc:
            raise CloudAsrRequestError(
                "科大讯飞识别连接中断，请稍后重试。",
                category="transient",
            ) from None
        finally:
            try:
                connection.close()
            except Exception:
                pass


def transcribe_pcm16(
    provider: str,
    pcm: bytes,
    sample_rate: int = SAMPLE_RATE,
    **recognizer_options,
) -> str:
    """一次性创建在线识别器并返回文字，便于主程序直接调用。"""
    return CloudAsrRecognizer(provider, **recognizer_options).transcribe_pcm16(pcm, sample_rate)
