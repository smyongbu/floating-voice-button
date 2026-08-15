import unittest

from transcript_refinement import refine_transcript


class TranscriptRefinementTests(unittest.TestCase):
    def test_normalizes_chinese_spacing_and_punctuation(self):
        self.assertEqual(refine_transcript("  今天   天气不错  "), "今天 天气不错")
        self.assertEqual(refine_transcript("今天 , 天气不错 ."), "今天，天气不错。")

    def test_preserves_mixed_english(self):
        self.assertEqual(refine_transcript("你好吗? I'm fine."), "你好吗？ I'm fine.")

    def test_preserves_versions_time_urls_email_and_file_names(self):
        original = (
            "版本 v1.2.3，时间 12:30，比例 1:2，"
            "https://example.com/a?x=1，a.b@example.com，demo.py"
        )
        self.assertEqual(refine_transcript(original), original)

    def test_preserves_period_before_ascii_token_characters(self):
        self.assertEqual(
            refine_transcript("文件名是报告.pdf，对象.method()，章节.2，字段._private"),
            "文件名是报告.pdf，对象.method()，章节.2，字段._private",
        )
        self.assertEqual(
            refine_transcript("文件名是报告. pdf，对象. method()"),
            "文件名是报告. pdf，对象. method()",
        )

    def test_preserves_line_breaks_and_intentional_chinese_space(self):
        self.assertEqual(refine_transcript("第一行\n第二行"), "第一行\n第二行")
        self.assertEqual(refine_transcript("甲 乙"), "甲 乙")

    def test_preserves_join_controls_and_repeated_punctuation(self):
        original = "می\u200cروم 👩\u200d💻 等等... 真的吗?? 真的?!"
        self.assertEqual(refine_transcript(original), original)

    def test_removes_only_zero_width_space_and_bom(self):
        self.assertEqual(refine_transcript("甲\u200b乙\ufeff丙"), "甲乙丙")

    def test_preserves_intentional_repetition(self):
        self.assertEqual(
            refine_transcript("我真的非常喜欢这个。我真的非常喜欢这个。"),
            "我真的非常喜欢这个。我真的非常喜欢这个。",
        )

    def test_preserves_short_internal_and_non_adjacent_repetitions(self):
        self.assertEqual(refine_transcript("好。好。"), "好。好。")
        self.assertEqual(refine_transcript("非常非常重要。"), "非常非常重要。")
        self.assertEqual(
            refine_transcript("先保存。然后退出。先保存。"),
            "先保存。然后退出。先保存。",
        )

    def test_is_idempotent(self):
        once = refine_transcript("今天 , 天气不错 .")
        self.assertEqual(refine_transcript(once), once)


if __name__ == "__main__":
    unittest.main()
