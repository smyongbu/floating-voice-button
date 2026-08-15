import base64
import io
import json
import logging
import unittest
import urllib.error
import urllib.parse
import wave

import cloud_asr


class FakeResponse:
    def __init__(self, payload, *, headers=None, status=200):
        self._raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.headers = headers or {}
        self.status = status
        self.closed = False

    def read(self):
        return self._raw

    def close(self):
        self.closed = True


class FakeUrlOpen:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, *, timeout):
        self.requests.append((request, timeout))
        return self.responses.pop(0)


class FakeWebSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []
        self.closed = False

    def send(self, message):
        self.sent.append(message)

    def recv(self):
        return self.messages.pop(0)

    def close(self):
        self.closed = True


def request_headers(request):
    return {key.lower(): value for key, value in request.header_items()}


class CloudAsrCatalogTests(unittest.TestCase):
    def test_catalog_has_four_supported_services_and_field_metadata(self):
        catalog = cloud_asr.get_provider_catalog()
        self.assertEqual(
            {item["id"] for item in catalog},
            {"volcengine", "iflytek", "tencent", "aliyun"},
        )
        self.assertTrue(all(item["name"] and item["max_seconds"] == 55 for item in catalog))
        self.assertTrue(
            all(field["label"] and field["secret"] for item in catalog for field in item["credential_fields"])
        )

    def test_catalog_is_a_copy(self):
        catalog = cloud_asr.get_provider_catalog()
        catalog[0]["name"] = "被修改"
        self.assertNotEqual(cloud_asr.get_provider_catalog()[0]["name"], "被修改")

    def test_credential_validation_rejects_missing_and_unknown_fields(self):
        with self.assertRaisesRegex(cloud_asr.CloudAsrConfigurationError, "缺少必要凭据"):
            cloud_asr.validate_credentials("iflytek", {"app_id": "只有一个字段"})
        with self.assertRaisesRegex(cloud_asr.CloudAsrConfigurationError, "不支持的字段"):
            cloud_asr.validate_credentials("volcengine", {"api_key": "a", "other": "b"})
        with self.assertRaisesRegex(cloud_asr.CloudAsrConfigurationError, "不支持"):
            cloud_asr.get_provider("unknown")

    def test_pcm_validation_happens_before_credentials_or_network(self):
        recognizer = cloud_asr.CloudAsrRecognizer("volcengine", credentials={"api_key": "x"})
        self.assertEqual(recognizer.transcribe_pcm16(b""), "")
        with self.assertRaisesRegex(cloud_asr.CloudAsrConfigurationError, "16000 Hz"):
            recognizer.transcribe_pcm16(b"\x00\x00", 8000)
        with self.assertRaisesRegex(cloud_asr.CloudAsrConfigurationError, "完整"):
            recognizer.transcribe_pcm16(b"\x00")
        too_long = b"\x00\x00" * (cloud_asr.SAMPLE_RATE * cloud_asr.MAX_AUDIO_SECONDS + 1)
        with self.assertRaisesRegex(cloud_asr.CloudAsrConfigurationError, "55 秒"):
            recognizer.transcribe_pcm16(too_long)

    def test_request_error_categories_are_safe_for_router_fallback(self):
        cases = {
            "HTTP 503": "transient",
            "HTTP 401": "authentication",
            "HTTP 429": "quota",
            "InvalidParameter.Audio": "parameter",
            "40000001": "authentication",
            "40000005": "quota",
            "50000001": "transient",
            "10139": "parameter",
            "11201": "quota",
            "unrecognized-provider-code": "remote",
        }
        for code, expected in cases.items():
            with self.subTest(code=code):
                error = cloud_asr._safe_remote_error("测试服务", code)
                self.assertEqual(error.category, expected)

    def test_network_failure_is_transient(self):
        def unavailable(request, *, timeout):
            raise urllib.error.URLError("offline")

        recognizer = cloud_asr.CloudAsrRecognizer(
            "volcengine",
            credentials={"app_key": "fake-key"},
            urlopen=unavailable,
            uuid_factory=lambda: "operation-id",
        )
        with self.assertRaises(cloud_asr.CloudAsrRequestError) as raised:
            recognizer.transcribe_pcm16(b"\x00\x00")
        self.assertEqual(raised.exception.category, "transient")


class CloudAsrAdapterTests(unittest.TestCase):
    PCM = b"\x01\x00" * 640

    def test_volcengine_uploads_wav_and_parses_text(self):
        opener = FakeUrlOpen(
            FakeResponse(
                {"result": {"text": "火山识别结果"}},
                headers={"X-Api-Status-Code": "20000000", "X-Tt-Logid": "log-1"},
            )
        )
        recognizer = cloud_asr.CloudAsrRecognizer(
            "volcengine",
            credentials={"app_key": "fake-volc-key", "access_key": "fake-old-access-key"},
            urlopen=opener,
            uuid_factory=lambda: "fixed-request-id",
            clock=lambda: 1_700_000_000.0,
        )

        self.assertEqual(recognizer.transcribe_pcm16(self.PCM), "火山识别结果")
        request, timeout = opener.requests[0]
        self.assertEqual(request.full_url, cloud_asr.VOLCENGINE_URL)
        self.assertEqual(timeout, 30.0)
        self.assertEqual(request_headers(request)["x-api-app-key"], "fake-volc-key")
        self.assertEqual(request_headers(request)["x-api-access-key"], "fake-old-access-key")
        body = json.loads(request.data.decode("utf-8"))
        wav_bytes = base64.b64decode(body["audio"]["data"])
        with wave.open(io.BytesIO(wav_bytes), "rb") as audio:
            self.assertEqual((audio.getnchannels(), audio.getsampwidth(), audio.getframerate()), (1, 2, 16000))
            self.assertEqual(audio.readframes(audio.getnframes()), self.PCM)

    def test_tencent_signs_raw_pcm_request_and_parses_result(self):
        opener = FakeUrlOpen(FakeResponse({"Response": {"Result": "腾讯识别结果", "RequestId": "r-1"}}))
        recognizer = cloud_asr.CloudAsrRecognizer(
            "tencent",
            credentials={"secret_id": "fake-secret-id", "secret_key": "fake-secret-key"},
            urlopen=opener,
            clock=lambda: 1_700_000_000.0,
            uuid_factory=lambda: "operation-id",
        )

        self.assertEqual(recognizer.transcribe_pcm16(self.PCM), "腾讯识别结果")
        request, _ = opener.requests[0]
        headers = request_headers(request)
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, cloud_asr.TENCENT_URL)
        self.assertEqual(headers["x-tc-action"], "SentenceRecognition")
        self.assertIn("Credential=fake-secret-id/", headers["authorization"])
        self.assertEqual(body["DataLen"], len(self.PCM))
        self.assertEqual(base64.b64decode(body["Data"]), self.PCM)

    def test_aliyun_creates_and_reuses_token_then_uploads_raw_pcm(self):
        now = 1_700_000_000
        opener = FakeUrlOpen(
            FakeResponse({"Token": {"Id": "fake-temporary-token", "ExpireTime": now + 3600}}),
            FakeResponse({"status": 20000000, "result": "阿里第一次结果"}),
            FakeResponse({"status": 20000000, "result": "阿里第二次结果"}),
        )
        recognizer = cloud_asr.CloudAsrRecognizer(
            "aliyun",
            credentials={
                "app_key": "fake-app-key",
                "access_key_id": "fake-access-key-id",
                "access_key_secret": "fake-access-key-secret",
            },
            urlopen=opener,
            clock=lambda: float(now),
            uuid_factory=lambda: "fixed-nonce",
        )

        self.assertEqual(recognizer.transcribe_pcm16(self.PCM), "阿里第一次结果")
        self.assertEqual(recognizer.transcribe_pcm16(self.PCM), "阿里第二次结果")
        requests = [item[0] for item in opener.requests]
        token_requests = [item for item in requests if item.full_url.startswith(cloud_asr.ALIYUN_TOKEN_URL)]
        asr_requests = [item for item in requests if item.full_url.startswith(cloud_asr.ALIYUN_ASR_URL)]
        self.assertEqual(len(token_requests), 1)
        self.assertEqual(len(asr_requests), 2)
        self.assertIn("Signature=", token_requests[0].full_url)
        self.assertEqual(asr_requests[0].data, self.PCM)
        self.assertEqual(request_headers(asr_requests[0])["x-nls-token"], "fake-temporary-token")
        query = urllib.parse.parse_qs(urllib.parse.urlparse(asr_requests[0].full_url).query)
        self.assertEqual(query["appkey"], ["fake-app-key"])

    def test_iflytek_streams_40ms_frames_and_parses_ordered_words(self):
        socket = FakeWebSocket(
            [
                json.dumps({
                    "code": 0,
                    "data": {"status": 1, "result": {"sn": 0, "ws": [{"cw": [{"w": "讯飞"}]}]}},
                }),
                json.dumps({
                    "code": 0,
                    "data": {"status": 2, "result": {"sn": 1, "ws": [{"cw": [{"w": "结果"}]}]}},
                }),
            ]
        )
        factory_calls = []
        sleeps = []

        def factory(url, *, timeout):
            factory_calls.append((url, timeout))
            return socket

        pcm = b"\x02\x00" * 1280
        recognizer = cloud_asr.CloudAsrRecognizer(
            "iflytek",
            credentials={"app_id": "fake-app-id", "api_key": "fake-api-key", "api_secret": "fake-api-secret"},
            websocket_factory=factory,
            sleep=sleeps.append,
            clock=lambda: 1_700_000_000.0,
            uuid_factory=lambda: "operation-id",
        )

        self.assertEqual(recognizer.transcribe_pcm16(pcm), "讯飞结果")
        self.assertTrue(factory_calls[0][0].startswith(cloud_asr.IFLYTEK_URL + "?"))
        self.assertEqual(sleeps, [0.04, 0.04])
        self.assertEqual(len(socket.sent), 3)
        first, second, final = [json.loads(item) for item in socket.sent]
        self.assertEqual(first["data"]["status"], 0)
        self.assertEqual(second["data"]["status"], 1)
        self.assertEqual(final["data"], {"status": 2})
        self.assertEqual(base64.b64decode(first["data"]["audio"]) + base64.b64decode(second["data"]["audio"]), pcm)
        self.assertTrue(socket.closed)

    def test_logs_only_safe_metadata_not_secret_audio_or_text(self):
        stream = io.StringIO()
        logger = logging.getLogger("cloud-asr-security-test")
        logger.handlers.clear()
        logger.propagate = False
        logger.setLevel(logging.INFO)
        logger.addHandler(logging.StreamHandler(stream))
        sensitive_text = "正文绝不写进日志"
        sensitive_secret = "密钥绝不写进日志"
        opener = FakeUrlOpen(
            FakeResponse(
                {"Response": {"Result": sensitive_text, "RequestId": "safe-request-id"}}
            )
        )
        recognizer = cloud_asr.CloudAsrRecognizer(
            "tencent",
            credentials={"secret_id": "fake-id", "secret_key": sensitive_secret},
            urlopen=opener,
            run_logger=logger,
            error_logger=logger,
            clock=lambda: 1_700_000_000.0,
            uuid_factory=lambda: "operation-id",
        )

        self.assertEqual(recognizer.transcribe_pcm16(self.PCM), sensitive_text)
        log_text = stream.getvalue()
        self.assertNotIn(sensitive_text, log_text)
        self.assertNotIn(sensitive_secret, log_text)
        self.assertNotIn(base64.b64encode(self.PCM).decode("ascii"), log_text)
        self.assertIn("字数=8", log_text)


if __name__ == "__main__":
    unittest.main()
