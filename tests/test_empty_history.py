import ast
import csv
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch


class EmptyHistoryTests(unittest.TestCase):
    def method(self, folder):
        source = Path(__file__).resolve().parents[1] / 'webui/services.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        method = next(node for node in ast.walk(tree)
                      if isinstance(node, ast.FunctionDef) and node.name == 'get_match_history_payload')
        method.args.args[1].annotation = method.args.args[2].annotation = None
        method.returns = None
        builder = next(node for node in ast.walk(tree)
                       if isinstance(node, ast.FunctionDef) and node.name == '_build_match_history_response')
        builder.decorator_list = []
        namespace = {'csv': csv, 'io': io, 'Any': Any, 'get_config_root': lambda: folder}
        exec(compile(ast.Module(body=[method, builder], type_ignores=[]), str(source), 'exec'), namespace)
        runtime = SimpleNamespace(get_status=lambda: {'is_running': False})
        service = SimpleNamespace(runtime_manager=runtime,
                                  _build_match_history_response=namespace['_build_match_history_response'])
        return lambda: namespace['get_match_history_payload'](service)

    def test_new_device_without_history_has_an_empty_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            result = self.method(folder)()
            self.assertEqual(result['items'], [])
            self.assertEqual(result['summary']['total_matches'], 0)
            self.assertFalse((folder / 'match_history.csv').exists())

    def test_unreadable_history_is_not_silently_treated_as_empty(self):
        with tempfile.TemporaryDirectory() as temporary:
            method = self.method(Path(temporary))
            with patch.object(Path, 'open', side_effect=PermissionError('denied')):
                with self.assertRaises(PermissionError):
                    method()
