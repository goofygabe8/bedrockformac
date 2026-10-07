"""Documented launcher settings, applied once before the next game start."""

import hashlib
import json
import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / '.launcher-settings.json'


def field(key, title, section, kind, default, hint, **extra):
    return dict(key=key, title=title, section=section, kind=kind, default=default, hint=hint, **extra)


SCHEMA = [
    field('high_resolution', 'High Resolution / Retina', 'Display', 'bool', True,
          'Use the full pixel resolution of Retina displays. Sharper text and edges; more GPU work. Applies after restarting Minecraft.'),
    field('gfx_fullscreen', 'Fullscreen', 'Display', 'bool', False, 'Start Minecraft in fullscreen instead of a window.'),
    field('gfx_vsync', 'Vertical sync', 'Display', 'bool', True, 'Keep frames in step with your display to reduce tearing. Can add some input delay.'),
    field('gfx_max_framerate', 'Frame rate limit', 'Display', 'choice', 120,
          'A lower cap reduces heat and battery use. Vertical sync may cap the rate further.',
          options=[[0, 'Unlimited'], [30, '30 FPS'], [60, '60 FPS'], [90, '90 FPS'], [120, '120 FPS'], [144, '144 FPS'], [165, '165 FPS'], [240, '240 FPS']]),
    field('gfx_field_of_view', 'Field of view', 'Display', 'slider', 70, 'Show more of the world at higher values, with stronger perspective distortion.', minimum=30, maximum=110, step=1, unit='°'),
    field('gfx_guiscale_offset', 'Interface scale', 'Display', 'choice', 0, 'Change the size of inventory and menu elements. Available sizes depend on the game window.', options=[[-2, 'Smallest'], [-1, 'Smaller'], [0, 'Automatic'], [1, 'Larger'], [2, 'Large'], [3, 'Extra large'], [4, 'Maximum']]),
    field('gfx_interface_opacity', 'HUD opacity', 'Display', 'slider', 1, 'Make the hotbar and HUD more opaque. 100% is recommended for clear menus.', minimum=0.25, maximum=1, step=0.05, scale=100, unit='%'),
    field('renderer', 'Graphics renderer', 'Graphics', 'choice', 'metal3', 'Metal 3 fixes the server UI tint with anti-aliasing. Experimental Metal 4 reproduced that bug on the original Mac.', options=[['metal3', 'Metal 3 (Recommended)'], ['metal4', 'Metal 4 (Experimental)']]),
    field('graphics_mode', 'Graphics mode', 'Graphics', 'choice', 1, 'Fancy is the balanced default. Vibrant Visuals adds lighting effects and costs more GPU time; some server packs disable it.', options=[[0, 'Simple'], [1, 'Fancy'], [2, 'Vibrant Visuals']]),
    field('gfx_msaa', 'Anti-aliasing', 'Graphics', 'choice', 4, 'Smooth jagged edges in Simple or Fancy graphics. Higher values cost more GPU time. The slider can be hidden in Vibrant Visuals.', options=[[1, 'Off (1×)'], [2, '2×'], [4, '4× (Recommended)'], [8, '8×'], [16, '16×']]),
    field('gfx_viewdistance', 'Classic render distance', 'Graphics', 'choice', 256, 'How far the game draws in Simple or Fancy mode. Larger distances use more CPU, GPU, and memory.', options=[[128, '8 chunks'], [192, '12 chunks'], [256, '16 chunks'], [384, '24 chunks'], [512, '32 chunks'], [768, '48 chunks'], [1024, '64 chunks']]),
    field('deferred_viewdistance', 'Vibrant render distance', 'Graphics', 'choice', 16, 'Draw distance used by Vibrant Visuals. Keep this lower than the classic distance for smoother play.', options=[[8, '8 chunks'], [12, '12 chunks'], [16, '16 chunks'], [24, '24 chunks'], [32, '32 chunks'], [48, '48 chunks']]),
    field('gfx_gamma', 'Display brightness', 'Graphics', 'slider', 0.5, 'Adjust Minecraft display brightness. This does not change the Mac display brightness.', minimum=0, maximum=1, step=0.05, scale=100, unit='%'),
    field('gfx_texture_streaming', 'Texture streaming', 'Graphics', 'bool', True, 'Allow textures to load as needed instead of keeping everything resident. Recommended on Macs with limited memory.'),
    field('gfx_multithreaded_renderer', 'Multi-threaded renderer', 'Graphics', 'bool', True, 'Let Minecraft use multiple CPU threads for rendering work. Leave enabled unless diagnosing a game-specific problem.'),
    field('metal_hud', 'Performance overlay', 'Graphics', 'bool', False, 'Show Apple’s Metal performance overlay, including frame rate and GPU timing. Useful when comparing settings.'),
    field('ctrl_sensitivity2_mouse', 'Mouse sensitivity', 'Controls', 'slider', 0.5, 'Camera movement speed for your mouse or trackpad.', minimum=0, maximum=1, step=0.01, scale=100, unit='%'),
    field('mac_command_shortcuts', 'Mac copy / paste shortcuts', 'Controls', 'bool', True,
          'Map Command to Windows Control for Command+C, Command+V and Command+A. Option sends Windows Alt. Applies after restarting Minecraft; Control shortcuts also work.'),
    field('ctrl_sensitivity2_gamepad', 'Controller sensitivity', 'Controls', 'slider', 0.5, 'Camera movement speed for the controller’s right stick.', minimum=0, maximum=1, step=0.01, scale=100, unit='%'),
    field('ctrl_invertmouse_mouse', 'Invert mouse look', 'Controls', 'bool', False, 'Reverse vertical camera movement for mouse and trackpad input.'),
    field('ctrl_invertmouse_gamepad', 'Invert controller look', 'Controls', 'bool', False, 'Reverse vertical camera movement for the controller’s right stick.'),
    field('ctrl_autojump_mouse', 'Auto-jump with keyboard', 'Controls', 'bool', False, 'Automatically jump over blocks while walking with keyboard controls.'),
    field('ctrl_autojump_gamepad', 'Auto-jump with controller', 'Controls', 'bool', False, 'Automatically jump over blocks while walking with a controller.'),
    field('ctrl_togglecrouch_mouse', 'Toggle crouch with keyboard', 'Controls', 'bool', False, 'Press crouch once to stay crouched; press again to stand. Otherwise hold the key.'),
    field('ctrl_togglecrouch_gamepad', 'Toggle crouch with controller', 'Controls', 'bool', False, 'Press crouch once to stay crouched; press again to stand. Otherwise hold the button.'),
    field('ctrl_swap_gamepad_ab_buttons', 'Swap controller A / B', 'Controls', 'bool', False, 'Swap the game’s A and B actions for controllers with a different button layout.'),
    field('ctrl_swap_gamepad_xy_buttons', 'Swap controller X / Y', 'Controls', 'bool', False, 'Swap the game’s X and Y actions for controllers with a different button layout.'),
    field('gfx_viewbobbing', 'Walking camera bob', 'Controls', 'bool', True, 'Move the camera slightly as you walk. Disable for a steadier view.'),
    field('gfx_damagebobbing', 'Damage camera shake', 'Controls', 'bool', True, 'Shake the camera when taking damage. Disable for a steadier view.'),
]
for key, title, default in [('audio_main', 'Master volume', 0.7), ('audio_music', 'Music', 0.3), ('audio_sound', 'Sound effects', 1), ('audio_ambient', 'Ambient sounds', 1), ('audio_block', 'Blocks', 1), ('audio_hostile', 'Hostile creatures', 1), ('audio_neutral', 'Friendly creatures', 1), ('audio_player', 'Player sounds', 1), ('audio_weather', 'Weather', 1), ('audio_record', 'Jukebox and note blocks', 1)]:
    SCHEMA.append(field(key, title, 'Sound', 'slider', default, 'Volume for ' + title.lower() + '. Audio output device is selected with Audio Output in the main launcher.', minimum=0, maximum=1, step=0.05, scale=100, unit='%'))

BY_KEY = {entry['key']: entry for entry in SCHEMA}
LAUNCHER_KEYS = {'high_resolution', 'renderer', 'metal_hud', 'mac_command_shortcuts'}
DEFAULTS = {entry['key']: entry['default'] for entry in SCHEMA}
PRESETS = {
    'Balanced': {'high_resolution': True, 'renderer': 'metal3', 'graphics_mode': 1, 'gfx_msaa': 4, 'gfx_viewdistance': 256, 'deferred_viewdistance': 16, 'gfx_vsync': True, 'gfx_max_framerate': 120, 'gfx_texture_streaming': True, 'gfx_multithreaded_renderer': True},
    'Performance': {'high_resolution': False, 'renderer': 'metal3', 'graphics_mode': 0, 'gfx_msaa': 2, 'gfx_viewdistance': 128, 'deferred_viewdistance': 8, 'gfx_vsync': True, 'gfx_max_framerate': 60, 'gfx_texture_streaming': True, 'gfx_multithreaded_renderer': True},
    'Quality': {'high_resolution': True, 'renderer': 'metal3', 'graphics_mode': 2, 'gfx_msaa': 4, 'gfx_viewdistance': 384, 'deferred_viewdistance': 24, 'gfx_vsync': True, 'gfx_max_framerate': 120, 'gfx_texture_streaming': True, 'gfx_multithreaded_renderer': True},
}


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name('.settings-write-' + str(time.time_ns()))
    try:
        temporary.write_text(json.dumps(value, indent=2) + '\n')
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def config():
    if not CONFIG.is_file():
        return {}
    return json.loads(CONFIG.read_text())


def option_files(prefix):
    return sorted(Path(prefix).joinpath('drive_c/users').glob('*/AppData/Roaming/Minecraft Bedrock/Users/*/games/com.mojang/minecraftpe/options.txt'))


def settings(prefix):
    values = DEFAULTS.copy()
    files = option_files(prefix)
    active = [p for p in files if '/Shared/' not in str(p)] or files
    if active:
        for line in max(active, key=lambda p: p.stat().st_mtime).read_text(errors='replace').splitlines():
            key, separator, raw = line.partition(':')
            if separator and key in BY_KEY and key not in LAUNCHER_KEYS:
                try:
                    values[key] = raw == '1' if BY_KEY[key]['kind'] == 'bool' else float(raw)
                    if float(values[key]).is_integer() and BY_KEY[key]['kind'] != 'bool':
                        values[key] = int(values[key])
                except ValueError:
                    pass
    saved = config()
    try:
        from runtime_setup import _registry_value_is_set
        if _registry_value_is_set(Path(prefix)/'user.reg', r'Software\Wine\Mac Driver', '"RetinaMode"="n"'):
            values['high_resolution'] = False
    except OSError:
        pass
    values.update(saved.get('launcher', {}))
    values.update(saved.get('pending_game', {}))
    return dict(schema=SCHEMA, values=values, defaults=DEFAULTS, presets=PRESETS,
                pending=bool(saved.get('pending_game') or saved.get('pending_retina')))


def save_settings(values):
    if not isinstance(values, dict) or set(values) - BY_KEY.keys():
        raise ValueError('Unknown launcher setting.')
    normalized = {}
    for key, value in values.items():
        entry = BY_KEY[key]
        if entry['kind'] == 'bool':
            if type(value) is not bool: raise ValueError('Invalid value for ' + entry['title'])
        elif entry['kind'] == 'slider':
            if type(value) not in (int, float) or not entry['minimum'] <= value <= entry['maximum']:
                raise ValueError('Invalid value for ' + entry['title'])
        elif key == 'renderer':
            if value not in ('metal3', 'metal4'): raise ValueError('Invalid renderer.')
        else:
            # Preserve an existing custom numeric value when the UI is opened.
            limits = {'gfx_max_framerate': (0, 1000), 'gfx_field_of_view': (30, 110),
                      'gfx_viewdistance': (64, 2048), 'deferred_viewdistance': (4, 96)}
            if key in limits:
                if type(value) not in (int, float) or not float(value).is_integer() or not limits[key][0] <= value <= limits[key][1]:
                    raise ValueError('Invalid value for ' + entry['title'])
            elif value not in [item[0] for item in entry['options']]:
                raise ValueError('Invalid value for ' + entry['title'])
        normalized[key] = value
    saved = config()
    saved.setdefault('launcher', {}).update({key: value for key, value in normalized.items() if key in LAUNCHER_KEYS})
    saved.setdefault('pending_game', {}).update({key: value for key, value in normalized.items() if key not in LAUNCHER_KEYS})
    if 'high_resolution' in normalized:
        saved['pending_retina'] = True
    atomic_json(CONFIG, saved)


def prepare_launch_settings(prefix, wine):
    """Never called for a running game: its preference saves would overwrite us."""
    prefix = Path(prefix)
    saved = config()
    files = option_files(prefix)
    if not files:
        users = [p for p in (prefix/'drive_c/users').iterdir() if p.is_dir() and p.name.lower() not in ('public', 'default', 'default user')]
        if users:
            target = users[0]/'AppData/Roaming/Minecraft Bedrock/Users/Shared/games/com.mojang/minecraftpe/options.txt'
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch(mode=0o600)
            files = [target]
            saved['pending_game'] = {key: value for key, value in DEFAULTS.items() if key not in LAUNCHER_KEYS} | saved.get('pending_game', {})
    launcher = saved.get('launcher', {})
    from runtime_setup import _registry_value_is_set, _import_registry
    shortcut_key = r'Software\Wine\AppDefaults\Minecraft.Windows.exe\Mac Driver'
    shortcut_mode = 'y' if launcher.get('mac_command_shortcuts', True) else 'n'
    shortcut_values = {'LeftCommandIsCtrl': shortcut_mode, 'RightCommandIsCtrl': shortcut_mode}
    if shortcut_mode == 'y':
        shortcut_values.update(LeftOptionIsAlt='y', RightOptionIsAlt='y')
    if any(not _registry_value_is_set(prefix/'user.reg', shortcut_key, '"' + key + '"="' + value + '"') for key, value in shortcut_values.items()):
        registry = 'Windows Registry Editor Version 5.00\n\n[HKEY_CURRENT_USER\\' + shortcut_key + ']\n'
        registry += ''.join('"' + key + '"="' + value + '"\n' for key, value in shortcut_values.items())
        _import_registry(prefix, wine, registry)
    retina = launcher.get('high_resolution')
    # Fresh installations use Retina. Existing installations keep their choice.
    if retina is None:
        from runtime_setup import _registry_value_is_set
        disabled = _registry_value_is_set(prefix/'user.reg', r'Software\Wine\Mac Driver', '"RetinaMode"="n"')
        retina = not disabled
        launcher['high_resolution'] = retina
        saved['launcher'] = launcher
        saved['pending_retina'] = True
    if saved.get('pending_retina'):
        from runtime_setup import _import_registry
        mode = 'y' if retina else 'n'
        registry = 'Windows Registry Editor Version 5.00\n\n[HKEY_CURRENT_USER\\Software\\Wine\\Mac Driver]\n"RetinaMode"="' + mode + '"\n'
        _import_registry(prefix, wine, registry)
        saved.pop('pending_retina', None)
    changes = saved.get('pending_game', {})
    if changes and files:
        backup = ROOT/'.settings-backups'/str(time.time_ns())
        backup.mkdir(parents=True, mode=0o700)
        os.chmod(backup.parent, 0o700)
        records = []
        for options in files:
            before = options.read_bytes()
            text = before.decode('utf-8', errors='strict')
            for key, value in changes.items():
                if key not in BY_KEY or key in LAUNCHER_KEYS: continue
                raw = ('1' if value else '0') if type(value) is bool else format(value, 'g')
                text, count = re.subn(r'(?m)^' + re.escape(key) + r':[^\r\n]*', key + ':' + raw, text)
                if not count: text += ('\n' if text and not text.endswith('\n') else '') + key + ':' + raw + '\n'
            if text.encode() == before: continue
            name = hashlib.sha256(str(options.relative_to(prefix)).encode()).hexdigest()[:16] + '.options.txt'
            (backup/name).write_bytes(before)
            os.chmod(backup/name, 0o600)
            records.append(dict(path=str(options.relative_to(prefix)), backup=name))
            atomic_json(backup/'manifest.json', records)
            temporary = options.with_name('.launcher-options-' + str(time.time_ns()))
            try:
                temporary.write_text(text)
                os.chmod(temporary, options.stat().st_mode & 0o777)
                os.replace(temporary, options)
            finally:
                temporary.unlink(missing_ok=True)
        saved.pop('pending_game', None)
    atomic_json(CONFIG, saved)
    renderer = launcher.get('renderer', 'metal3')
    os.environ['D3DM_MTL4'] = '1' if renderer == 'metal4' else '0'
    os.environ['MTL_HUD_ENABLED'] = '1' if launcher.get('metal_hud', False) else '0'
