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


if __name__ == "__main__":
    unittest.main()
