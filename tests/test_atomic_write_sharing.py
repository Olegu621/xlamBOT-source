"""Windows sharing violations must not destroy saved queues or stop workers."""
import ctypes
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import utils


class AtomicWriteSharingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "queue.json"
        self.path.write_text("old", encoding="utf-8")

    def sharing_error(self, code=5):
        error = PermissionError("destination temporarily locked")
        error.winerror = code
        return error

    def test_transient_windows_errors_retry_without_truncating_destination(self):
        replace = os.replace
        for code in (5, 32, 33):
            self.path.write_text("old", encoding="utf-8")
            calls = []

            def busy_once(source, destination):
                calls.append(source)
                if len(calls) == 1:
                    self.assertEqual(self.path.read_text("utf-8"), "old")
                    raise self.sharing_error(code)
                replace(source, destination)

            with patch.object(utils.os, "replace", side_effect=busy_once), patch.object(utils.time, "sleep"):
                utils.atomic_write_text(self.path, "new")
            self.assertEqual(calls[0], calls[1])
            self.assertEqual(self.path.read_text("utf-8"), "new")
            self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_persistent_denial_is_bounded_and_preserves_old_file(self):
        error = self.sharing_error()
        with patch.object(utils.os, "replace", side_effect=error) as replace, patch.object(utils.time, "sleep") as sleep:
            with self.assertRaises(PermissionError) as caught:
                utils.atomic_write_text(self.path, "new")
        self.assertIs(caught.exception, error)
        self.assertEqual(replace.call_count, 8)
        self.assertLess(sum(c.args[0] for c in sleep.call_args_list), 1)
        self.assertEqual(self.path.read_text("utf-8"), "old")
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_other_io_errors_are_not_retried(self):
        with patch.object(utils.os, "replace", side_effect=OSError("disk full")) as replace, patch.object(utils.time, "sleep") as sleep:
            with self.assertRaises(OSError):
                utils.atomic_write_text(self.path, "new")
        replace.assert_called_once()
        sleep.assert_not_called()
        self.assertEqual(self.path.read_text("utf-8"), "old")

    def test_cleanup_denial_does_not_mask_original_error(self):
        error = self.sharing_error()
        with patch.object(utils.os, "replace", side_effect=error), patch.object(utils.time, "sleep"), patch.object(Path, "unlink", side_effect=OSError("cleanup blocked")):
            with self.assertRaises(PermissionError) as caught:
                utils.atomic_write_text(self.path, "new")
        self.assertIs(caught.exception, error)
        self.assertEqual(self.path.read_text("utf-8"), "old")

    @unittest.skipUnless(os.name == "nt", "requires real Windows file sharing")
    def test_real_windows_reader_releases_lock_and_write_succeeds(self):
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle.restype = wintypes.BOOL
        # Allow reads/writes, deliberately deny delete/rename sharing.
        handle = kernel.CreateFileW(str(self.path), 0x80000000, 3, None, 3, 0x80, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        release = threading.Event()

        def close_reader():
            release.wait(0.15)
            kernel.CloseHandle(handle)

        reader = threading.Thread(target=close_reader)
        reader.start()
        replace = os.replace
        errors = []

        def observed_replace(source, destination):
            try:
                return replace(source, destination)
            except OSError as error:
                errors.append(error.winerror)
                raise

        try:
            with patch.object(utils.os, "replace", side_effect=observed_replace):
                utils.atomic_write_text(self.path, "new")
        finally:
            release.set()
            reader.join(2)
        self.assertTrue(errors, "must reproduce a real sharing violation")
        self.assertTrue(set(errors) <= {5, 32, 33})
        self.assertEqual(self.path.read_text("utf-8"), "new")
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
