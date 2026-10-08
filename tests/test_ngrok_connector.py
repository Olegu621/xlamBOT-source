import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from telemetry_service.windows_ngrok import NgrokConnector


class NgrokConnectorTest(unittest.TestCase):
    def test_invalid_token_preserves_existing_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Mock(path=Path(folder)/'secret.json')
            connector=NgrokConnector(folder,store)
            for value in ('','token with spaces',None,{'token':'bad'}):
                with self.assertRaises(ValueError):
                    connector.configure(value)
            store.save.assert_not_called()
            connector.close()

    def test_launch_does_not_write_secret_or_capture_http_payloads(self):
        with tempfile.TemporaryDirectory() as folder:
            token='FAKE_NGROK_CREDENTIAL_FOR_TEST_ONLY'
            store=Mock(path=Path(folder)/'secret.json')
            store.load.return_value=(token,'ngrok')
            connector=NgrokConnector(folder,store)
            process=Mock()
            process.poll.return_value=0
            with patch.object(subprocess,'CREATE_NO_WINDOW',0,create=True),patch('subprocess.Popen',return_value=process) as spawn:
                connector._launch()
            command=spawn.call_args.args[0]
            self.assertNotIn(token,' '.join(command))
            self.assertEqual(spawn.call_args.kwargs['env']['NGROK_AUTHTOKEN'],token)
            self.assertIn('--inspect=false',command)
            configuration=(Path(folder)/'ngrok-agent.yml').read_text()
            self.assertNotIn(token,configuration)
            self.assertIn('127.0.0.1:4041',configuration)
            self.assertIn('remote_management: false',configuration)
            connector._save_status()
            self.assertNotIn(token,(Path(folder)/'ngrok-status.json').read_text())
            connector.close()

    def test_retry_is_explicit_and_clears_stale_public_address(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Mock(path=Path(folder)/'secret.json')
            connector=NgrokConnector(folder,store)
            connector.state='connection_failed'
            connector.url='https://old.ngrok-free.app'
            connector.attempts=3
            result=connector.retry()
            self.assertEqual(result['state'],'connecting')
            self.assertEqual(result['public_url'],'')
            self.assertEqual(connector.attempts,0)
            connector.close()
