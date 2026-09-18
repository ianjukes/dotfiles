#!/usr/bin/env python3
"""Filter a defaults-export plist on stdin; emit only reviewed preference keys.

This does not read apps, capture support files, encrypt, store or restore anything.
"""
import json
from pathlib import Path
import plistlib
import sys


def filter_preferences(app, prefs):
    keys = json.loads(Path(__file__).with_name('app_pref_keys.json').read_text())
    if app not in keys or '.' in app or not isinstance(prefs, dict):
        raise ValueError('Unknown application or invalid preference dictionary')
    result = {k: v for k, v in prefs.items() if k in keys[app]
              or (app == 'TablePlus' and k.startswith('TPShortcut'))}
    if app == 'TablePlus' and 'ViewSetting' in result:
        result['ViewSetting'] = {k: v for k, v in result['ViewSetting'].items()
                                 if k in keys['TablePlus.ViewSetting']}
    return result


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError()
        prefs = filter_preferences(sys.argv[1], plistlib.loads(sys.stdin.buffer.read()))
        sys.stdout.buffer.write(plistlib.dumps(prefs))
    except Exception:
        sys.exit('Could not filter preferences; no output should be captured. Check the app name and plist input.')
