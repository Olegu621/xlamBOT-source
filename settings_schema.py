"""Validate settings before saving; preserve structured calibration values."""
import math

SECRET_KEYS = {'key', 'discord_bot_token', 'telegram_token', 'webhook_url'}
RANGES = {
    'scrcpy_max_fps': (0, 120), 'scrcpy_max_width': (0, 3840), 'scrcpy_bitrate': (100000, 50000000),
    'used_threads': (1, 16), 'max_fps': (1, 120), 'emulator_port': (1, 65535),
    'brawler_switch_after_games': (0, 100000), 'run_for_minutes': (0, 525600),
    'preview_interval_ms': (0, 60000), 'debug_view_fps': (1, 60),
    'perceived_tile_size': (1, 1000), 'default_trophy_target': (0, 100000),
}

def masked(settings):
    return {section: {name: ('' if name in SECRET_KEYS else value) for name, value in values.items()}
            for section, values in settings.items()}

def validate(name, value, original, path=''):
    label = path or name
    if name == "thinking_mode" and (not isinstance(value, str) or value not in {"low", "standard", "medium", "high", "maximum"}):
        raise ValueError("Выберите уровень думалки из списка")
    if isinstance(original, bool):
        valid = isinstance(value, bool)
    elif isinstance(original, int):
        valid = type(value) is int or ('[' in label and type(value) is float and math.isfinite(value))
    elif isinstance(original, float):
        valid = type(value) in (float, int) and math.isfinite(value)
    elif isinstance(original, str):
        valid = isinstance(value, str)
    elif isinstance(original, list):
        valid = isinstance(value, list)
        if valid:
            if name not in {'gas_classes', 'wall_model_classes'} and len(value) != len(original):
                raise ValueError('Keep the array size for ' + label)
            for index, (item, old) in enumerate(zip(value, original)):
                validate(name, item, old, f'{label}[{index}]')
    elif isinstance(original, dict):
        valid = isinstance(value, dict)
        if valid:
            for child, item in value.items():
                if child in original:
                    validate(child, item, original[child], label + '.' + child)
                elif not label.startswith('brawler_calibration'):
                    raise ValueError('Unknown setting: ' + label + '.' + child)
    else:
        valid = False
    if not valid:
        raise ValueError('Invalid value type for ' + label)
    if name in RANGES and not isinstance(value, (list, dict)):
        if value == 'auto' and name in {'used_threads', 'max_fps'}:
            return
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            raise ValueError('Enter a number or auto for ' + label) from None
        low, high = RANGES[name]
        if not math.isfinite(numeric) or not low <= numeric <= high:
            raise ValueError(f'{label}: allowed range {low}–{high}')
    if type(value) in (int, float):
        if not math.isfinite(value) or value < 0:
            raise ValueError('Enter a non-negative finite number for ' + label)
        if any(part in name for part in ('confidence', 'gas_area_', 'gas_danger_', 'gas_centre_bias')) and value > 1:
            raise ValueError('Enter a value from 0 to 1 for ' + label)
