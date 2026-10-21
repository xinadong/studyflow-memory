import unittest
from datetime import datetime, timedelta, timezone

from app.api.routes.feedback import _correct_memory_type_from_explicit_cue, _infer_block_type_from_content
from app.domain.value_objects.memory_type import BlockType, MemoryType
from app.memory.review_schedule import is_review_due, parse_review_interval_days


class ReviewScheduleAndFeedbackBoundaryTests(unittest.TestCase):
    def test_parse_supported_interval_phrases(self):
        self.assertEqual(parse_review_interval_days("每2天复习一次 BFS"), 2)
        self.assertEqual(parse_review_interval_days("每 7 天复习"), 7)
        self.assertEqual(parse_review_interval_days("间隔14天"), 14)
        self.assertEqual(parse_review_interval_days("隔3天复习"), 3)
        self.assertEqual(parse_review_interval_days("每天复习"), 1)

    def test_invalid_interval_is_ignored(self):
        self.assertIsNone(parse_review_interval_days("每0天复习"))
        self.assertIsNone(parse_review_interval_days("每400天复习"))
        self.assertIsNone(parse_review_interval_days("下周复习一次"))
        self.assertIsNone(parse_review_interval_days("每2天提交作业"))

    def test_due_uses_created_or_last_used_timestamp(self):
        now = datetime.now(timezone.utc)
        self.assertTrue(is_review_due("每2天复习", now - timedelta(days=2), now=now))
        self.assertFalse(is_review_due("每2天复习", now - timedelta(days=1), now=now))

    def test_recovery_cues_take_priority_over_minutes(self):
        memory_type = _correct_memory_type_from_explicit_cue(
            "学累了5分钟，想先休息一下", MemoryType.TASK_PREFERENCE,
        )
        self.assertEqual(memory_type, MemoryType.RECOVERY_EXPERIENCE)
        self.assertEqual(_infer_block_type_from_content("学累了5分钟，想先休息一下"), BlockType.FATIGUE)

    def test_review_schedule_cue_takes_priority_over_task_words(self):
        memory_type = _correct_memory_type_from_explicit_cue(
            "以后每2天复习一次 BFS", MemoryType.TASK_PREFERENCE,
        )
        self.assertEqual(memory_type, MemoryType.REVIEW_SCHEDULE)

    def test_too_hard_cue_takes_priority_over_explanation_cue(self):
        memory_type = _correct_memory_type_from_explicit_cue(
            "任务太难，先看一个例子", MemoryType.EXPLANATION_PREFERENCE,
        )
        self.assertEqual(memory_type, MemoryType.RECOVERY_EXPERIENCE)
        self.assertEqual(_infer_block_type_from_content("任务太难，先看一个例子"), BlockType.TOO_HARD)

    def test_time_shortage_cue_takes_priority_over_task_action_words(self):
        memory_type = _correct_memory_type_from_explicit_cue(
            "时间不够，只做一道核心题", MemoryType.TASK_PREFERENCE,
        )
        self.assertEqual(memory_type, MemoryType.RECOVERY_EXPERIENCE)
        self.assertEqual(_infer_block_type_from_content("时间不够，只做一道核心题"), BlockType.TIME)


if __name__ == "__main__":
    unittest.main()
