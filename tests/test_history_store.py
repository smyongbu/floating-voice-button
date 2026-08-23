import tempfile
import unittest
from pathlib import Path

from history_store import HistoryRevisionMismatch, HistoryStore


class HistoryStoreTests(unittest.TestCase):
    def test_unicode_and_whitespace_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(Path(temp) / "history.db")
            text = "  你好 👋\n第二行  "
            store.add("op-1", text)
            self.assertEqual(store.list_entries()[0].text, text)

    def test_entries_are_newest_first_and_searchable(self):
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(Path(temp) / "history.db")
            store.add("op-1", "第一条")
            store.add("op-2", "第二条文字")
            self.assertEqual([entry.operation_id for entry in store.list_entries()], ["op-2", "op-1"])
            self.assertEqual([entry.operation_id for entry in store.list_entries("文字")], ["op-2"])

    def test_same_operation_is_saved_only_once(self):
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(Path(temp) / "history.db")
            store.add("same-op", "第一次")
            store.add("same-op", "不应覆盖")
            entries = store.list_entries()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].text, "第一次")

    def test_limit_delete_and_clear(self):
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(Path(temp) / "history.db", limit=3)
            for index in range(5):
                store.add(f"op-{index}", f"文字 {index}")
            self.assertEqual(len(store.list_entries()), 3)
            selected = store.list_entries()[0]
            self.assertTrue(store.delete(selected.operation_id))
            self.assertFalse(store.delete("missing"))
            self.assertEqual(store.clear(), 2)
            self.assertEqual(store.clear(), 0)

    def test_blank_text_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(Path(temp) / "history.db")
            with self.assertRaises(ValueError):
                store.add("op", " \n ")

    def test_get_returns_exact_entry_without_listing_all_history(self):
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(Path(temp) / "history.db")
            expected = store.add("target-op", "测试正文")
            store.add("other-op", "其他正文")

            self.assertEqual(store.get("target-op"), expected)
            self.assertIsNone(store.get("missing-op"))

    def test_revision_is_persistent_and_changes_after_clear_then_new_add(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "history.db"
            store = HistoryStore(database)
            self.assertEqual(store.signature(), (0, 0))

            store.add("before-clear", "清空前")
            count_before_clear, revision_before_clear = store.signature()
            self.assertEqual(count_before_clear, 1)

            self.assertEqual(store.clear(expected_revision=revision_before_clear), 1)
            count_after_clear, revision_after_clear = store.signature()
            self.assertEqual(count_after_clear, 0)
            self.assertGreater(revision_after_clear, revision_before_clear)

            reopened = HistoryStore(database)
            self.assertEqual(reopened.signature(), (0, revision_after_clear))
            reopened.add("after-clear", "清空后")
            count_after_add, revision_after_add = reopened.signature()
            self.assertEqual(count_after_add, 1)
            self.assertGreater(revision_after_add, revision_after_clear)

    def test_clear_rejects_stale_expected_revision_without_deleting_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(Path(temp) / "history.db")
            store.add("first-op", "第一条")
            stale_revision = store.signature()[1]
            store.add("new-op", "确认后新增")

            with self.assertRaises(HistoryRevisionMismatch):
                store.clear(expected_revision=stale_revision)

            count, current_revision = store.signature()
            self.assertEqual(count, 2)
            self.assertGreater(current_revision, stale_revision)

    def test_pending_batch_tracks_queue_positions_and_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(Path(temp) / "history.db")
            store.reserve("first", "batch-1")
            store.reserve("second", "batch-1")

            entries = {entry.operation_id: entry for entry in store.list_entries()}
            self.assertEqual(entries["first"].queue_position, 1)
            self.assertEqual(entries["second"].queue_position, 2)
            self.assertEqual(entries["first"].status, "queued")

            self.assertTrue(store.mark_recognizing("first", "正在出现"))
            recognizing = store.get("first")
            self.assertEqual(recognizing.status, "recognizing")
            self.assertEqual(recognizing.preview_text, "正在出现")

            self.assertTrue(store.complete("first", "识别完成"))
            completed = store.get("first")
            self.assertEqual(completed.status, "completed")
            self.assertEqual(completed.text, "识别完成")
            self.assertEqual(completed.preview_text, "")

    def test_pending_preview_is_searchable_and_failure_is_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(Path(temp) / "history.db")
            store.reserve("pending", "batch-2")
            store.mark_recognizing("pending", "逐字预览")
            self.assertEqual(store.list_entries("预览")[0].operation_id, "pending")
            self.assertTrue(store.fail("pending", "没有声音"))
            failed = store.get("pending")
            self.assertEqual(failed.status, "failed")
            self.assertEqual(failed.error_message, "没有声音")

    def test_pending_entries_obey_limit_and_pending_count_is_global(self):
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(Path(temp) / "history.db", limit=3)
            for index in range(5):
                store.reserve(f"pending-{index}", "batch")

            self.assertEqual(store.signature()[0], 3)
            self.assertEqual(store.pending_count(), 3)
            self.assertEqual(store.list_entries("不会命中"), [])
            self.assertEqual(store.pending_count(), 3)

    def test_fail_pending_recovers_queued_and_recognizing_after_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "history.db"
            store = HistoryStore(database)
            store.reserve("queued", "batch")
            store.reserve("recognizing", "batch")
            store.mark_recognizing("recognizing", "未完成文字")
            store.add("completed", "已经完成")

            reopened = HistoryStore(database)
            self.assertEqual(reopened.fail_pending("上次未完成"), 2)
            self.assertEqual(reopened.pending_count(), 0)
            self.assertEqual(reopened.get("queued").status, "failed")
            self.assertEqual(reopened.get("recognizing").preview_text, "")
            self.assertEqual(reopened.get("recognizing").error_message, "上次未完成")
            self.assertEqual(reopened.get("completed").status, "completed")

    def test_terminal_history_state_cannot_be_overwritten_by_racing_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(Path(temp) / "history.db")
            store.reserve("failed", "batch")
            self.assertTrue(store.fail("failed", "程序退出"))
            self.assertFalse(store.complete("failed", "迟到的模型结果"))
            self.assertFalse(store.mark_recognizing("failed", "迟到的预览"))
            self.assertFalse(store.delete_pending("failed"))
            self.assertEqual(store.get("failed").status, "failed")

            store.reserve("completed", "batch")
            self.assertTrue(store.complete("completed", "正常完成"))
            self.assertFalse(store.fail("completed", "迟到的退出清理"))
            self.assertEqual(store.get("completed").text, "正常完成")


if __name__ == "__main__":
    unittest.main()
