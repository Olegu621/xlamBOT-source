"""Shared presentation preferences, independent of Android device profiles."""
import json
import threading
import utils

_lock = threading.RLock()

def read():
    with _lock:
        try:
            data = json.loads(utils.read_text_auto(utils.resolve_project_path('cfg', 'ui_preferences.json')))
        except (OSError, ValueError):
            data = {}
        return {'language': data.get('language') if data.get('language') in {'ru', 'en'} else 'ru'}

def save(language):
    if language not in {'ru', 'en'}:
        raise ValueError('Choose Russian or English.')
    with _lock:
        data = {'language': language}
        utils.atomic_write_text(utils.resolve_project_path('cfg', 'ui_preferences.json'), json.dumps(data))
        return data
