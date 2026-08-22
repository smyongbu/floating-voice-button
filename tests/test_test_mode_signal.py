import unittest
import uuid
from unittest.mock import patch

import test_mode_signal


class TestModeSignalTests(unittest.TestCase):
    def test_lease_sets_and_clears_named_request(self):
        suffix = uuid.uuid4().hex
        with (
            patch.object(test_mode_signal, "TEST_MODE_EVENT_NAME", f"Local\\TestRequest_{suffix}"),
            patch.object(test_mode_signal, "TEST_MODE_READY_NAME", f"Local\\TestReady_{suffix}"),
            patch.object(test_mode_signal, "TEST_MODE_BLOCKED_NAME", f"Local\\TestBlocked_{suffix}"),
        ):
            lease = test_mode_signal.TestModeLease()
            self.assertFalse(test_mode_signal.test_mode_is_active())
            lease.acquire()
            self.assertTrue(test_mode_signal.test_mode_is_active())
            lease.release()
            self.assertFalse(test_mode_signal.test_mode_is_active())


if __name__ == "__main__":
    unittest.main()
