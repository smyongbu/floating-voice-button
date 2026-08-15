import struct
import sys
import types
import unittest
from unittest.mock import patch

from audio_level import AudioLevelMonitor, normalized_level_from_int16


class _FakeInputStream:
    def __init__(self, callback, samplerate=16000, **_kwargs):
        self.callback = callback
        self.samplerate = samplerate
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True

    def push(self, chunk: bytes):
        self.callback(chunk, len(chunk) // 2, None, None)


class _FakeSoundDevice(types.SimpleNamespace):
    def __init__(self):
        super().__init__()
        self.streams = []

    @staticmethod
    def query_hostapis():
        return []

    def RawInputStream(self, **kwargs):
        stream = _FakeInputStream(**kwargs)
        self.streams.append(stream)
        return stream


class AudioLevelTests(unittest.TestCase):
    def test_silence_is_zero(self):
        self.assertEqual(normalized_level_from_int16(bytes(2048)), 0.0)

    def test_louder_audio_has_higher_level(self):
        quiet = struct.pack("<1024h", *([1000] * 1024))
        loud = struct.pack("<1024h", *([9000] * 1024))
        self.assertGreater(normalized_level_from_int16(loud), normalized_level_from_int16(quiet))

    def test_level_is_clamped(self):
        maximum = struct.pack("<1024h", *([32767] * 1024))
        self.assertLessEqual(normalized_level_from_int16(maximum), 1.0)

    def test_continuous_waiting_audio_is_forwarded_but_never_buffered(self):
        fake_sd = _FakeSoundDevice()
        forwarded = []
        levels = []
        monitor = AudioLevelMonitor()
        with patch.dict(sys.modules, {"sounddevice": fake_sd}):
            monitor.open_continuous(levels.append, lambda pcm, rate: forwarded.append((pcm, rate)))
        stream = fake_sd.streams[0]
        chunk = bytes(3200)
        for _ in range(20):
            stream.push(chunk)
        self.assertTrue(monitor.running)
        self.assertFalse(monitor.capturing)
        self.assertEqual(len(forwarded), 20)
        self.assertEqual(monitor.chunks, [])
        monitor.close()

    def test_capture_can_start_and_finish_without_reopening_microphone(self):
        fake_sd = _FakeSoundDevice()
        standby_audio = []
        body_audio = []
        monitor = AudioLevelMonitor()
        with patch.dict(sys.modules, {"sounddevice": fake_sd}):
            monitor.open_continuous(
                lambda _levels: None,
                lambda pcm, _rate: standby_audio.append(pcm),
            )
        stream = fake_sd.streams[0]
        waiting = bytes(800)
        first = bytes([1, 0]) * 400
        second = bytes([2, 0]) * 400
        stream.push(waiting)
        monitor.begin_capture(
            lambda _levels: None,
            lambda pcm, _rate: body_audio.append(pcm),
        )
        stream.push(first)
        stream.push(second)
        pcm, sample_rate = monitor.finish_capture()
        stream.push(waiting)

        self.assertEqual(len(fake_sd.streams), 1)
        self.assertEqual(pcm, first + second)
        self.assertEqual(sample_rate, 16000)
        self.assertEqual(body_audio, [first, second])
        self.assertEqual(standby_audio, [waiting, first, second, waiting])
        self.assertTrue(monitor.running)
        self.assertFalse(stream.stopped)
        self.assertFalse(stream.closed)
        monitor.close()

    def test_legacy_start_and_stop_still_capture_and_close(self):
        fake_sd = _FakeSoundDevice()
        monitor = AudioLevelMonitor()
        with patch.dict(sys.modules, {"sounddevice": fake_sd}):
            monitor.start(lambda _levels: None)
        chunk = bytes([3, 0]) * 400
        stream = fake_sd.streams[0]
        stream.push(chunk)
        pcm, sample_rate = monitor.stop()
        self.assertEqual((pcm, sample_rate), (chunk, 16000))
        self.assertFalse(monitor.running)
        self.assertTrue(stream.stopped)
        self.assertTrue(stream.closed)

    def test_begin_capture_requires_an_open_stream_and_rejects_overlap(self):
        fake_sd = _FakeSoundDevice()
        monitor = AudioLevelMonitor()
        with self.assertRaisesRegex(RuntimeError, "尚未打开"):
            monitor.begin_capture()
        with patch.dict(sys.modules, {"sounddevice": fake_sd}):
            monitor.open_continuous(lambda _levels: None)
        monitor.begin_capture()
        with self.assertRaisesRegex(RuntimeError, "已经在录音"):
            monitor.begin_capture()
        monitor.close()

    def test_activation_is_atomic_and_failure_does_not_start_capture(self):
        fake_sd = _FakeSoundDevice()
        monitor = AudioLevelMonitor()
        with patch.dict(sys.modules, {"sounddevice": fake_sd}):
            monitor.open_continuous(lambda _levels: None)
        states = []

        def activate():
            states.append((monitor.capturing, list(monitor.chunks)))

        monitor.begin_capture(lambda _levels: None, None, activate)
        self.assertEqual(states, [(False, [])])
        self.assertTrue(monitor.capturing)
        monitor.finish_capture()

        def fail_activation():
            raise RuntimeError("会话启动失败")

        with self.assertRaisesRegex(RuntimeError, "会话启动失败"):
            monitor.begin_capture(lambda _levels: None, None, fail_activation)
        self.assertFalse(monitor.capturing)
        self.assertEqual(monitor.chunks, [])
        monitor.close()

    def test_waiting_level_callback_is_restored_after_capture(self):
        fake_sd = _FakeSoundDevice()
        waiting_levels = []
        recording_levels = []
        monitor = AudioLevelMonitor()
        with patch.dict(sys.modules, {"sounddevice": fake_sd}):
            monitor.open_continuous(waiting_levels.append)
        stream = fake_sd.streams[0]
        monitor.last_emit = 0.0
        stream.push(bytes(3200))
        monitor.begin_capture(recording_levels.append)
        monitor.last_emit = 0.0
        stream.push(bytes(3200))
        monitor.finish_capture()
        monitor.last_emit = 0.0
        stream.push(bytes(3200))
        self.assertEqual(len(waiting_levels), 2)
        self.assertEqual(len(recording_levels), 1)
        self.assertTrue(monitor.is_open)
        self.assertTrue(monitor.continuous)
        monitor.close()

    def test_level_drawing_failure_never_stops_the_audio_callback(self):
        fake_sd = _FakeSoundDevice()
        forwarded = []
        monitor = AudioLevelMonitor()

        def broken_level_callback(_levels):
            raise RuntimeError("窗口已经关闭")

        with patch.dict(sys.modules, {"sounddevice": fake_sd}):
            monitor.open_continuous(
                broken_level_callback,
                lambda pcm, _rate: forwarded.append(pcm),
            )
        monitor.last_emit = 0.0
        fake_sd.streams[0].push(bytes(3200))
        self.assertEqual(forwarded, [bytes(3200)])
        self.assertTrue(monitor.is_open)
        monitor.close()


if __name__ == "__main__":
    unittest.main()
