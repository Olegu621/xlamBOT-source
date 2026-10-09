"""Shared presentation preferences, independent of Android device profiles."""
import json
import threading
import unicodedata
import utils

_lock = threading.RLock()

def read():
    with _lock:
        try:
            data = json.loads(utils.read_text_auto(utils.resolve_project_path('cfg', 'ui_preferences.json')))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        try:
            pc_name = validate_pc_name(data.get('pc_name', ''))
        except ValueError:
            pc_name = ''
        return {'language': data.get('language') if data.get('language') in {'ru', 'en'} else 'ru',
                'pc_name': pc_name}

def validate_pc_name(value):
    if not isinstance(value, str) or len(value) > 64 or any(unicodedata.category(c).startswith('C') for c in value):
        raise ValueError('PC name must contain up to 64 printable characters.')
    return value.strip()


def save(language=None, pc_name=None):
    if language is not None and language not in {'ru', 'en'}:
        raise ValueError('Choose Russian or English.')
    with _lock:
        data = read()
        if language is not None:
            data['language'] = language
        if pc_name is not None:
            data['pc_name'] = validate_pc_name(pc_name)
        utils.atomic_write_text(utils.resolve_project_path('cfg', 'ui_preferences.json'), json.dumps(data))
        return data
