import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch,Mock
import update_client as u

@unittest.skipUnless(os.name=='nt','Windows restart helper')
class RestartTests(unittest.TestCase):
 def test_helper_starts_child_with_unicode_quoted_paths_and_arguments(self):
  with tempfile.TemporaryDirectory(prefix="xlam-restart-'тест-") as directory:
   root=Path(directory);marker=root/'child with space.json'
   code='from pathlib import Path; Path('+repr(str(marker))+').write_text("child started")'
   with patch.dict(os.environ,{'XLAMBOT_UPDATE_HOME':directory}):
    p=u.start_restart_helper(sys.executable,2147483647,['-c',code])
    p.wait(timeout=15)
    deadline=time.monotonic()+8
    while not marker.exists() and time.monotonic()<deadline:time.sleep(.1)
    self.assertEqual(p.returncode,0,(root/'restart.log').read_text(errors='replace'))
    self.assertEqual(marker.read_text(),'child started')
    self.assertFalse(list(root.glob('restart-ready-*')))
 def test_failed_helper_cannot_exit_current_bot(self):
  with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'XLAMBOT_UPDATE_HOME':directory}):
   child=Mock();child.poll.return_value=1
   with patch.object(u.subprocess,'Popen',return_value=child),patch.object(u.os,'_exit') as exit:
    with self.assertRaises(RuntimeError):u.start_restart_helper(sys.executable,os.getpid())
    exit.assert_not_called()
    kwargs=u.subprocess.Popen.call_args.kwargs
    self.assertEqual(kwargs['stdin'],u.subprocess.DEVNULL)
    self.assertEqual(kwargs['stderr'],u.subprocess.STDOUT)
    self.assertEqual(kwargs['creationflags'],u.subprocess.CREATE_NO_WINDOW)
