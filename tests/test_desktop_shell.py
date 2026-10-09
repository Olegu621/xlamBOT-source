import unittest
from concurrent.futures import ThreadPoolExecutor
from desktop_shell import LogBuffer


class DesktopLogTests(unittest.TestCase):
    def test_window_logs_are_bounded_and_thread_safe(self):
        buffer = LogBuffer(limit=1000)
        with ThreadPoolExecutor(4) as pool:
            list(pool.map(lambda n: buffer.write(str(n)+'\n'), range(200)))
        version, text = buffer.snapshot()
        self.assertEqual(version, 200)
        self.assertLessEqual(len(text), 1000)
        buffer.write('\x1b[31mred\x1b[0m')
        self.assertTrue(buffer.snapshot()[1].endswith('red'))
        buffer.write('x'*4000)
        self.assertEqual(buffer.snapshot()[1], 'x'*1000)

    def test_closed_legacy_console_does_not_stop_logging(self):
        import io
        legacy = io.StringIO()
        legacy.close()
        buffer = LogBuffer(legacy)
        self.assertEqual(buffer.write('still running'), 13)
        buffer.flush()
        self.assertEqual(buffer.snapshot()[1], 'still running')
