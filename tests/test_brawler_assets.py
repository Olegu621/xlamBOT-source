"""Offline portraits and asset-only additions on an existing installation."""
import ast
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from flask import Flask, send_file
from PIL import Image

import utils
from brawler_catalog import BUILT_IN_BRAWLERS

ROOT = Path(__file__).resolve().parents[1]
package = ModuleType('webui')
package.__path__ = [str(ROOT / 'webui')]
with patch.dict(sys.modules, {'webui': package}):
    from webui.resource_updates import ResourceUpdater
    from webui.services import WebDataService


def icon_client(updater, root=ROOT):
    # Exercise the actual Flask handler without starting device/telemetry workers.
    source = ROOT / 'webui/app.py'
    tree = ast.parse(source.read_text('utf-8'))
    handler = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == 'brawler_icon')
    handler.decorator_list = []
    namespace = dict(get_brawler_icon_path=utils.get_brawler_icon_path,
                     resource_updater=updater, PROJECT_ROOT=root, send_file=send_file)
    exec(compile(ast.Module(body=[handler], type_ignores=[]), str(source), 'exec'), namespace)
    app = Flask(__name__)
    app.add_url_rule('/api/assets/brawlers/<path:brawler_name>',
                     view_func=namespace['brawler_icon'])
    return app.test_client()


class BrawlerAssetsTests(unittest.TestCase):
    def test_every_menu_entry_for_new_brawlers_serves_a_real_png_offline(self):
        with tempfile.TemporaryDirectory() as folder:
            updater = ResourceUpdater(ROOT, Path(folder))
            client = icon_client(updater)
            service = WebDataService.__new__(WebDataService)
            catalog = {row['name']: row for row in service.get_brawler_catalog()}
            with patch('requests.sessions.Session.request', side_effect=AssertionError('Must work offline')):
                for name in ('cosmo', 'vince', 'shelly'):
                    with self.subTest(name=name):
                        with client.get(catalog[name]['icon_url']) as response:
                            self.assertEqual(response.status_code, 200)
                            self.assertEqual(response.mimetype, 'image/png')
                            with Image.open(io.BytesIO(response.data)) as image:
                                image.verify()
                            with Image.open(io.BytesIO(response.data)) as image:
                                self.assertGreaterEqual(min(image.size), 100)

    def test_updated_icons_are_served_when_old_bundle_never_had_them(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            updater = ResourceUpdater(root, root / 'data')
            updater.active = root / 'snapshot'
            client = icon_client(updater, root)
            with patch.object(utils, 'PROJECT_ROOT', root):
                for name in ('cosmo', 'vince'):
                    with self.subTest(name=name):
                        asset = updater.active / f'api/assets/brawler_icons/{name}.png'
                        asset.parent.mkdir(parents=True, exist_ok=True)
                        original = (ROOT / f'api/assets/brawler_icons/{name}.png').read_bytes()
                        asset.write_bytes(original)
                        self.assertFalse((root / f'api/assets/brawler_icons/{name}.png').exists())
                        with client.get(f'/api/assets/brawlers/{name}') as response:
                            self.assertEqual(response.status_code, 200)
                            self.assertEqual(response.data, original)

    def test_new_portrait_takes_precedence_and_missing_update_falls_back(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            updated = root / 'updated.png'
            updated.write_bytes((ROOT / 'api/assets/brawler_icons/cosmo.png').read_bytes())
            with Image.open(updated) as image:
                image.verify()
            self.assertEqual(utils.get_brawler_icon_path('COSMO', lambda name: updated), updated)
            self.assertEqual(utils.get_brawler_icon_path('Cosmo', lambda name: root / 'missing.png'),
                             ROOT / 'api/assets/brawler_icons/cosmo.png')

    def test_legacy_folder_and_names_still_work(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            legacy = root / 'api/assets/brawler_icons2/mr. p.png'
            legacy.parent.mkdir(parents=True)
            legacy.write_bytes((ROOT / 'api/assets/brawler_icons/mrp.png').read_bytes())
            with patch.object(utils, 'PROJECT_ROOT', root):
                self.assertEqual(utils.get_brawler_icon_path('Mr. P'), legacy)

    def test_unsafe_names_never_reach_asset_resolver(self):
        def forbidden(name):
            self.fail(f'Unsafe name reached the asset resolver: {name}')
        for name in ('../cosmo', '..\\vince', '/cosmo', '.', '..', ''):
            with self.subTest(name=name):
                self.assertIsNone(utils.get_brawler_icon_path(name, forbidden))

    def test_unknown_portrait_returns_404(self):
        with tempfile.TemporaryDirectory() as folder:
            client = icon_client(ResourceUpdater(ROOT, Path(folder)))
            self.assertEqual(client.get('/api/assets/brawlers/no-such-brawler').status_code, 404)

    def test_new_default_queue_has_both_without_fabricated_trophies(self):
        queue = json.loads((ROOT / 'latest_brawler_data.json').read_text('utf-8'))
        names = [entry['brawler'] for entry in queue]
        for name in ('cosmo', 'vince'):
            self.assertEqual(names.count(name), 1)
            entry = next(row for row in utils.clean_queue(queue) if row['brawler'] == name)
            self.assertIsNone(entry['trophies'])
            self.assertTrue(entry['automatically_pick'])

    def test_official_game_ids_survive_an_old_partial_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'brawlers_info.json'
            original = b'{"cosmo":{"safe_range":400},"vince":{"safe_range":350}}'
            path.write_bytes(original)
            with patch.object(utils, 'brawlers_info_file_path', path):
                info = utils.load_brawlers_info()
                self.assertEqual(info['cosmo']['id'], 16000109)
                self.assertEqual(info['vince']['id'], 16000110)
                self.assertEqual(info['cosmo']['safe_range'], 400)
                self.assertEqual(info['vince']['safe_range'], 350)
            self.assertEqual(path.read_bytes(), original)
        self.assertNotEqual(BUILT_IN_BRAWLERS['cosmo']['id'], BUILT_IN_BRAWLERS['vince']['id'])


if __name__ == '__main__':
    unittest.main()
