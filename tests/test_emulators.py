import hashlib
import json
from pathlib import Path
import tempfile
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch
import zipfile
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from flask import Flask
package = ModuleType('webui')
package.__path__ = [str(Path(__file__).resolve().parents[1] / 'webui')]
with patch.dict(sys.modules, {'webui': package}):
    from webui.emulators import EmulatorManager, instance_name, parse_instances, register
    from webui import emulator_distribution as dist
from update_client import canonical


class EmulatorTests(unittest.TestCase):
    def test_setup_blocks_device_training_and_legacy_start_but_not_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Flask(__name__);devices=Mock(resolve_serial=lambda key:key)
            app.config['UI_API_TOKEN']='test'
            for route in ('/api/devices/<key>/start','/api/devices/<key>/training/start','/api/devices/<key>/stop'):
                app.add_url_rule(route,route,lambda key: {'ok':True},methods=['POST'])
            app.add_url_rule('/api/runtime/start','legacy',lambda: {'ok':True},methods=['POST'])
            with patch.dict('os.environ',{'LOCALAPPDATA':folder}),patch.object(EmulatorManager,'discover',return_value=None),patch('threading.Thread.start'):
                register(app,devices)
            manager=app.extensions['emulator_manager'];manager.job=dict(state='running',indices=[1])
            client=app.test_client()
            for route in ('/api/devices/emulator-5556/start','/api/devices/emulator-5556/training/start','/api/runtime/start'):
                self.assertEqual(client.post(route).status_code,409)
            self.assertEqual(client.post('/api/devices/emulator-5554/start').status_code,200)
            self.assertEqual(client.post('/api/devices/emulator-5556/stop').status_code,200)
            self.assertEqual(client.get('/api/emulators',environ_overrides={'xlambot.remote':True}).status_code,403)

    def manager(self, path):
        with patch.object(EmulatorManager, 'discover', return_value=None):
            return EmulatorManager(Mock(all_statuses=lambda: []), path)

    def test_list_mapping_and_transition(self):
        rows = parse_instances('0,LDPlayer - Special for xlamBOT,4,5,1,7,8,1280,720,240\n2,Two,0,0,0,88,0,1280,720,240')
        self.assertEqual(rows[1]['serial'], 'emulator-5558')
        self.assertTrue(rows[1]['running'])
        self.assertFalse(rows[1]['ready'])
        offline = parse_instances('1,Stopped,0,0,0,-1,-1,1280,720,280')[0]
        self.assertFalse(offline['running'])
        booting = parse_instances('1,Booting,15,0,2,10,11,1280,720,240')[0]
        self.assertTrue(booting['running'])
        self.assertFalse(booting['ready'])
        self.assertEqual(parse_instances('1,My, emulator,0,0,0,-1,-1,1280,720,240')[0]['name'],'My, emulator')
        for data in ('0,broken', '0,A,0,0,3,0,0,1,1,240', '0,A,0,0,0,0,0,1,1,240\n0,B,0,0,0,0,0,1,1,240'):
            with self.assertRaises(ValueError):
                parse_instances(data)

    def test_invalid_names_and_actions(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = self.manager(folder)
            for name in ('', '   ', 'A\nB', '--from', 'a";cmd', '../x', 'a' * 61):
                with self.assertRaises(ValueError):
                    instance_name(name)
            for payload in (None, {'action':'shell','command':'whoami'}, {'action':'launch','index':True}, {'action':'add','name':'a','path':'x'}):
                with self.assertRaises(ValueError):
                    manager.submit(payload)

    def test_add_return_code_is_instance_id_but_other_commands_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            manager=self.manager(folder);manager.installation=Path(folder)
            with patch.object(manager,'validate_path'), patch('subprocess.run',return_value=Mock(returncode=2,stdout=b'',stderr=b'')):
                self.assertEqual(manager.console('add','--name','New'),'')
                self.assertEqual(manager.console('copy','--name','Copy','--from',0),'')
                with self.assertRaisesRegex(RuntimeError,'CONSOLE_FAILED'):
                    manager.console('launch','--index',0)

    def test_transient_native_inventory_during_boot_is_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            manager=self.manager(folder)
            item=dict(index=1,running=True,name='Mine')
            manager.instances=Mock(side_effect=[[],[item]])
            with patch('time.sleep'):
                self.assertEqual(manager._instance(1),item)
            self.assertEqual(manager.instances.call_count,2)

    def test_active_bot_alias_blocks_every_destructive_operation(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = self.manager(folder)
            item = dict(index=0, serial='emulator-5554', running=False, name='Mine')
            manager.instances = lambda: [item]
            manager.devices.all_statuses = lambda: [dict(serial='127.0.0.1:5555', is_running=True)]
            for action in ('quit', 'clone', 'configure', 'customize', 'remove'):
                payload = dict(action=action,index=0)
                if action == 'clone': payload['name']='Copy'
                if action == 'remove': payload['confirmation']='Mine'
                with self.assertRaisesRegex(ValueError,'STOP_BOT_FIRST'):
                    manager.submit(payload)

    def test_clone_delete_need_closed_instance_and_exact_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = self.manager(folder)
            item=dict(index=0,serial='emulator-5554',running=True,name='Mine')
            manager.instances=lambda:[item]
            with self.assertRaisesRegex(ValueError,'CLOSE_EMULATOR_FIRST'):
                manager.submit(dict(action='clone',index=0,name='Copy'))
            item['running']=False
            with self.assertRaisesRegex(ValueError,'CONFIRM_NAME'):
                manager.submit(dict(action='remove',index=0,confirmation='Other'))
            manager.job=dict(state='running')
            with self.assertRaisesRegex(ValueError,'EMULATOR_BUSY'):
                manager.submit(dict(action='rename',index=0,name='Changed'))

    def signed(self):
        key=Ed25519PrivateKey.generate()
        public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw).hex()
        prefix=f'https://github.com/{dist.REPO}/releases/download/edition-1/'
        manifest=dict(repository=dist.REPO,revision=1,base_version='9.5.37.0',edition_version='1.2',files={name:hashlib.sha256(name.encode()).hexdigest() for name in dist.FILES},base=dict(url=prefix+'LDPlayer_9.5.37.0.exe',size=1,sha256='a'*64),package=dict(url=prefix+'edition.zip',size=1,sha256='b'*64))
        return key,public,manifest

    def test_signature_paths_limits_and_rollback(self):
        key,public,manifest=self.signed()
        def envelope():return dict(manifest=manifest,signature=key.sign(canonical(manifest)).hex())
        with patch.object(dist,'PUBLIC_KEY',public):
            self.assertEqual(dist.verify_manifest(envelope())['revision'],1)
            bad=envelope();bad['manifest']=dict(manifest,revision=2)
            with self.assertRaises(Exception):dist.verify_manifest(bad)
            manifest['files']['vms/leidian0/data.vmdk']='a'*64
            with self.assertRaises(ValueError):dist.verify_manifest(envelope())
            del manifest['files']['vms/leidian0/data.vmdk']
            manifest['package']['url']='https://evil.invalid/edition.zip'
            with self.assertRaises(ValueError):dist.verify_manifest(envelope())

    def test_archive_cannot_touch_account_or_escape_target(self):
        _,_,manifest=self.signed()
        with tempfile.TemporaryDirectory() as folder:
            archive=Path(folder)/'edition.zip';target=Path(folder)/'staged'
            with zipfile.ZipFile(archive,'w') as z:
                for name in dist.FILES:z.writestr(name,name.encode())
            dist.extract_package(archive,manifest,target)
            self.assertEqual(set(p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()),dist.FILES)
            with zipfile.ZipFile(archive,'a') as z:z.writestr('../account.txt','bad')
            with self.assertRaises(ValueError):dist.extract_package(archive,manifest,target)
            self.assertFalse((Path(folder)/'account.txt').exists())

    def test_host_update_failure_restores_all_replaced_files(self):
        _,_,manifest=self.signed()
        with tempfile.TemporaryDirectory() as folder:
            manager=self.manager(Path(folder)/'private');manager.installation=Path(folder)/'host';manager.installation.mkdir()
            manager.instances=lambda:[]
            stage=Path(folder)/'staged';stage.mkdir()
            for name in dist.HOST_FILES:
                (manager.installation/name).write_bytes(b'old')
                (stage/name).write_bytes(b'new')
            (stage/'guest').mkdir()
            # Missing guest APK is a real transaction failure after host replacement.
            with self.assertRaises(OSError):dist.apply_host(manager,stage,manifest)
            for name in dist.HOST_FILES:self.assertEqual((manager.installation/name).read_bytes(),b'old')
            account=manager.installation/'vms/leidian0/data.vmdk';account.parent.mkdir(parents=True);account.write_bytes(b'private')
            (manager.installation/'xlamBOT-edition.json').write_text(json.dumps({'mod_revision':2}))
            with self.assertRaisesRegex(ValueError,'ROLLBACK'):dist.apply_host(manager,stage,manifest)
            self.assertEqual(account.read_bytes(),b'private')


if __name__ == '__main__':unittest.main()
