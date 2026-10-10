"""English defaults for the emulator UI and newly prepared Android guests."""
import json
import os
import time


def host_english(manager):
    if any(item['running'] for item in manager.instances()):
        return False
    manager.native_manager(close=True)
    path=manager.installation/'vms/config/leidians.config'
    if path.is_symlink() or not path.resolve().is_relative_to(manager.installation):
        raise ValueError('INVALID_INSTALLATION')
    values=json.loads(path.read_text(encoding='utf8'))
    if values.get('languageId')=='en_US' and values.get('productLanguageId')=='en_US':return True
    backup=manager.home/'backups'/f'host-language-{time.time_ns()}.json'
    backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(path.read_bytes())
    values.update(languageId='en_US',productLanguageId='en_US')
    temporary=path.with_suffix('.xlambot-language-tmp')
    temporary.write_text(json.dumps(values,ensure_ascii=False,indent=2),encoding='utf8')
    if any(item['running'] for item in manager.instances()):
        temporary.unlink(missing_ok=True);raise ValueError('CLOSE_EMULATOR_FIRST')
    os.replace(temporary,path)
    return True


def guest_english(manager,index):
    manager._idle_bot(manager._instance(index))
    for key,value in [('persist.sys.locale','en-US'),('persist.sys.language','en'),('persist.sys.country','US')]:
        manager.console('setprop','--index',index,'--key',key,'--value',value)
    actual=manager.console('adb','--index',index,'--command','shell getprop persist.sys.locale').strip()
    if actual!='en-US':raise RuntimeError('GUEST_LANGUAGE_FAILED')


def prepare_english(manager,index):
    item=manager._instance(index);manager._idle_bot(item)
    if item['running']:raise ValueError('CLOSE_EMULATOR_FIRST')
    host_english(manager)
    manager.console('launch','--index',index)
    try:
        manager._wait(lambda rows:any(i['index']==index and i['ready'] for i in rows))
        manager._wait(lambda rows:manager.console('adb','--index',index,'--command','shell getprop sys.boot_completed').strip()=='1')
        guest_english(manager,index)
    finally:
        manager._idle_bot(manager._instance(index))
        manager.console('quit','--index',index)
        manager._wait(lambda rows:any(i['index']==index and not i['running'] for i in rows))
