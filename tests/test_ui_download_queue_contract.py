from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from history_store import HistoryEntry
from settings_panel import WebSettingsApi


PROJECT_DIR = Path(__file__).resolve().parents[1]


def _top_level_function(source: str, signature: str) -> str:
    """返回以顶格右花括号结束的 JavaScript 函数，避免依赖 JS 运行环境。"""
    start = source.index(signature)
    lines = source[start:].splitlines()
    collected: list[str] = []
    for line in lines:
        collected.append(line)
        if line == "}":
            return "\n".join(collected)
    raise AssertionError(f"没有找到函数结尾：{signature}")


def _quoted_values(source: str) -> set[str]:
    return set(re.findall(r'["\']([^"\']+)["\']', source))


class DownloadUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.javascript = (PROJECT_DIR / "web" / "app.js").read_text(encoding="utf-8")
        cls.css = (PROJECT_DIR / "web" / "styles.css").read_text(encoding="utf-8")

    def test_both_model_card_renderers_use_independent_cancel_action(self) -> None:
        cancel_calls = re.findall(
            r'manageLocalModelResource\((input\.value|engine\.modelId),\s*"cancel"\)',
            self.javascript,
        )
        self.assertCountEqual(cancel_calls, ["input.value", "engine.modelId"])
        self.assertIn('action: () => manageLocalModelResource(model.model_id, "delete")', self.javascript)

    def test_verifying_state_keeps_cancel_visible_for_realtime_and_local_models(self) -> None:
        cancel_guards = re.findall(
            r"if\s*\(\[(?P<states>[^\]]+)\]\.includes\(resourceState\)\)\s*\{\s*"
            r'const cancelButton = createTextElement\("button", "model-card-cancel"',
            self.javascript,
            re.DOTALL,
        )
        self.assertEqual(len(cancel_guards), 2)
        for states in cancel_guards:
            values = _quoted_values(states)
            self.assertTrue(
                {"queued", "downloading", "verifying", "paused", "pausing", "cancelling"}
                <= values
            )

    def test_cancel_polling_reaches_terminal_state_and_rerenders_enabled_controls(self) -> None:
        polling = _top_level_function(self.javascript, "function scheduleModelResourcePoll()")
        active_sets = re.findall(
            r"\[(?P<states>[^\]]+)\]\.includes\(resourceState\)", polling, re.DOTALL
        )
        self.assertGreaterEqual(len(active_sets), 2)
        for states in active_sets:
            values = _quoted_values(states)
            self.assertIn("cancelling", values)
            self.assertTrue({"not_started", "completed", "failed"}.isdisjoint(values))

        operation = _top_level_function(
            self.javascript, "async function manageLocalModelResource(modelId, action)"
        )
        finally_match = re.search(r"finally\s*\{(?P<body>.*?)\n  \}", operation, re.DOTALL)
        self.assertIsNotNone(finally_match)
        finally_body = finally_match.group("body")
        self.assertRegex(finally_body, r"state\.modelBusy\s*=\s*false\s*;")
        self.assertRegex(
            finally_body,
            r"syncModelControls\(\s*(?:state\.model)?\s*\)",
            "终态响应是在 modelBusy=true 时首次渲染；解除 busy 后必须重绘实时和本地模型控件。",
        )

    def test_realtime_card_is_tall_enough_for_download_and_cancel_buttons(self) -> None:
        card = re.search(
            r"#localModelView\.local-mode-v3 \.realtime-model-row \.mode-option\s*\{"
            r"(?P<body>.*?)\}",
            self.css,
            re.DOTALL,
        )
        buttons = re.search(
            r"#localModelView\.local-mode-v3 \.model-card-download,\s*"
            r"#localModelView\.local-mode-v3 \.model-card-cancel\s*\{(?P<body>.*?)\}",
            self.css,
            re.DOTALL,
        )
        actions = re.search(
            r"#localModelView\.local-mode-v3 \.model-card-actions\s*\{(?P<body>.*?)\}",
            self.css,
            re.DOTALL,
        )
        self.assertIsNotNone(card)
        self.assertIsNotNone(buttons)
        self.assertIsNotNone(actions)
        card_height = int(re.search(r"min-height:\s*(\d+)px", card.group("body")).group(1))
        button_height = int(re.search(r"min-height:\s*(\d+)px", buttons.group("body")).group(1))
        gap = int(re.search(r"gap:\s*(\d+)px", actions.group("body")).group(1))
        self.assertGreaterEqual(card_height, button_height * 2 + gap)


class SettingsApiContractTests(unittest.TestCase):
    @staticmethod
    def _api() -> WebSettingsApi:
        api = WebSettingsApi.__new__(WebSettingsApi)
        api._run_log = MagicMock()
        api._error_log = MagicMock()
        return api

    def test_cancel_does_not_use_current_or_fallback_model_delete_gate(self) -> None:
        api = self._api()
        resource_id = "streaming-paraformer-bilingual-zh-en"
        manager = MagicMock()
        manager.resource_ids = (resource_id,)
        manager.cancel.return_value = {
            "resource_id": resource_id,
            "state": "cancelling",
            "verified": False,
        }
        api._model_downloads = manager
        payload = {
            "realtime_models": [
                {
                    "model_id": resource_id,
                    "resource_status": dict(manager.cancel.return_value),
                }
            ],
            "local_models": [],
        }

        with (
            patch.object(api, "_resource_is_in_use", return_value=True) as in_use,
            patch.object(api, "_recognition_payload", return_value=payload),
        ):
            response = api.manage_local_model_resource(resource_id, "cancel")

        self.assertTrue(response["ok"])
        manager.cancel.assert_called_once_with(resource_id)
        manager.delete.assert_not_called()
        in_use.assert_not_called()

    def test_history_pending_count_is_global_even_when_entries_are_filtered(self) -> None:
        api = self._api()
        store = MagicMock()
        store.snapshot.return_value = (
            [HistoryEntry("done", "2026-08-24T12:00:00+08:00", "仅匹配这条")],
            (7, 19),
        )
        store.pending_count.return_value = 4
        api._store = store

        payload = api._history_payload("仅匹配")

        self.assertEqual(len(payload["entries"]), 1)
        self.assertEqual(payload["pending_count"], 4)
        store.snapshot.assert_called_once_with("仅匹配")
        store.pending_count.assert_called_once_with()

    def test_history_ui_uses_payload_pending_count_not_filtered_entries(self) -> None:
        javascript = (PROJECT_DIR / "web" / "app.js").read_text(encoding="utf-8")
        normalize = _top_level_function(javascript, "function normalizeHistoryPayload(payload)")
        render = _top_level_function(javascript, "function renderHistory()")
        self.assertIn("payload?.pending_count", normalize)
        self.assertIn("const activeCount = state.pendingCount", render)
        self.assertNotRegex(
            render,
            r"activeCount\s*=\s*state\.entries\.(?:filter|reduce)",
        )


if __name__ == "__main__":
    unittest.main()
