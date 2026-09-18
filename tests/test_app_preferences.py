"""Exercise the real shell helpers using synthetic files and mocked macOS commands."""
import json
import os
from pathlib import Path
import plistlib
import shlex
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
LIB = REPO / 'home/.files/lib/macos.sh'
SCRIPTS = REPO / 'home/.chezmoiscripts/darwin/app_libs'

MOCK_DEFAULTS = '''import os, pathlib, plistlib, shutil, sys
root = pathlib.Path(os.environ['APP_TEST_HOME']).resolve()
assert root.is_relative_to(pathlib.Path('/private/tmp'))
assert root != pathlib.Path.home().resolve()
action, domain = sys.argv[1:3]
if action == 'read':
    print(os.environ.get('APP_TEST_VERSION', '2.5.0'))
    sys.exit(0)
assert '/' not in domain
target = root / 'Library/Preferences' / (domain + '.plist')
if action == 'import':
    marker = root / 'failed-once'
    if os.environ.get('APP_TEST_IMPORT_FAIL') and not marker.exists():
        marker.touch()
        sys.exit(1)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(sys.argv[3], target)
else:
    raise AssertionError('Unexpected defaults operation')
'''

HARNESS = '''source "$APP_TEST_LIB"
# All preference operations are shell functions; /usr/bin/defaults is never used.
function defaults() { python3 "$APP_TEST_DEFAULTS" "$@"; }
function app_path() { [[ ${APP_TEST_INSTALLED:-1} == 1 ]] && print -r -- "$APP_TEST_HOME/Fake.app"; }
function ps() { print -r -- "${APP_TEST_PROCESSES:-}"; }
function pgrep() { return ${APP_TEST_PGREP:-1}; }
function chezmoi() {
  [[ $1 == decrypt && $2 != *fail.asc ]] || return 1
  cat -- "$2"
}
function sudo() { print -u2 -- 'Forbidden system operation in test'; return 99; }
'''


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='/private/tmp', prefix='app-prefs-test-')
        self.root = Path(self.tmp.name)
        self.home = self.root / 'destination'
        self.home.mkdir()
        self.lib = self.root / 'macos.sh'
        source = LIB.read_text()
        self.assertNotIn('/usr/bin/defaults', source)
        # Do not change HOME: substitute only the destination reference in this test copy.
        self.lib.write_text(source.replace('$HOME', '$APP_TEST_HOME'))
        self.defaults = self.root / 'defaults.py'
        self.defaults.write_text(MOCK_DEFAULTS)
        self.env = dict(os.environ, APP_TEST_HOME=str(self.home), APP_TEST_LIB=str(self.lib),
                        APP_TEST_DEFAULTS=str(self.defaults), PYTHONDONTWRITEBYTECODE='1')
        self.env.pop('DOTFILES_RESTORE_APP', None)
        self.src = self.root / 'prefs.plist.asc'
        self.src.write_bytes(plistlib.dumps({'setting': 'snapshot'}))
        self.dst = self.home / 'Library/Preferences/example.plist'

    def tearDown(self):
        self.tmp.cleanup()

    def shell(self, script, app=None, **env):
        execution = dict(self.env, **env)
        if app:
            execution['DOTFILES_RESTORE_APP'] = app
        return subprocess.run(['/bin/zsh', '-f', '-c', HARNESS + script],
                              env=execution, capture_output=True, text=True)

    def restore(self, app='Loopback', major='2', sources=None, **env):
        pairs = sources or [self.src, self.dst]
        return self.shell('restore_app_libs ' + ' '.join(shlex.quote(str(v)) for v in [app, major, *pairs]),
                          app=env.pop('opt_in', None), **env)

    def seed(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(plistlib.dumps(value))

    def test_no_opt_in_preserves_existing_and_absent_configuration(self):
        self.assertEqual(self.restore().returncode, 0)
        self.assertFalse(self.dst.exists())
        self.seed(self.dst, {'setting': 'newer'})
        self.assertEqual(self.restore().returncode, 0)
        self.assertEqual(plistlib.loads(self.dst.read_bytes()), {'setting': 'newer'})

    def test_wrong_opt_in_cannot_restore_another_app(self):
        self.assertEqual(self.restore(opt_in='SoundSource').returncode, 0)
        self.assertFalse(self.dst.exists())

    def test_clean_restore_and_explicit_repeat(self):
        self.assertEqual(self.restore(opt_in='Loopback').returncode, 0)
        self.assertEqual(plistlib.loads(self.dst.read_bytes()), {'setting': 'snapshot'})
        self.assertEqual(self.restore(opt_in='Loopback').returncode, 0)
        self.assertEqual(self.dst.stat().st_mode & 0o777, 0o600)
        self.assertFalse(list(self.dst.parent.glob('.chezmoi-restore*')))

    def test_replacement_restores_entire_plist_and_backs_up_original(self):
        original = {'registrationInfo': 'synthetic-only', 'setting': 'old'}
        self.seed(self.dst, original)
        result = self.restore(opt_in='Loopback')
        self.assertEqual(result.returncode, 0, result.stderr)
        after = plistlib.loads(self.dst.read_bytes())
        self.assertEqual(after, {'setting': 'snapshot'})
        backups = list(self.dst.parent.glob('example.plist.chezmoi.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(plistlib.loads(backups[0].read_bytes()), original)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)

    def test_tableplus_restores_all_snapshot_fields_without_merging(self):
        self.dst = self.dst.with_name('com.tinyapp.TablePlus.plist')
        self.seed(self.dst, {'ViewSetting': {'SQLFontSize': 10, 'Variables': {'key': 'synthetic'}}})
        captured = {'ViewSetting': {'SQLFontSize': 14, 'RecentMatchedItems': ['synthetic'],
                    'Variables': {'key': 'synthetic-snapshot'}}, 'UnrecognisedPreference': True}
        self.src.write_bytes(plistlib.dumps(captured))
        result = self.restore(app='TablePlus', major='26', opt_in='TablePlus', APP_TEST_VERSION='26.10.20')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(plistlib.loads(self.dst.read_bytes()), captured)

    def test_missing_snapshot_later_becomes_eligible(self):
        missing = self.root / 'later.asc'
        result = self.restore(sources=[missing, self.dst], opt_in='Loopback')
        self.assertEqual(result.returncode, 0)
        self.assertIn('missing', result.stderr)
        self.assertFalse(self.dst.exists())
        missing.write_bytes(self.src.read_bytes())
        self.assertEqual(self.restore(sources=[missing, self.dst], opt_in='Loopback').returncode, 0)
        self.assertTrue(self.dst.exists())

    def test_prepare_all_before_changing_any_destination(self):
        second = self.root / 'second.asc'
        second.write_bytes(b'not a plist')
        target = self.home / 'Library/Application Support/Loopback/Devices.plist'
        self.seed(self.dst, {'keep': True})
        result = self.restore(sources=[self.src, self.dst, second, target], opt_in='Loopback')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(plistlib.loads(self.dst.read_bytes()), {'keep': True})
        self.assertFalse(target.exists())
        second = self.root / 'fail.asc'
        second.write_bytes(self.src.read_bytes())
        result = self.restore(sources=[self.src, self.dst, second, target], opt_in='Loopback')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(plistlib.loads(self.dst.read_bytes()), {'keep': True})

    def test_support_plist_uses_existing_replacement_and_backup(self):
        self.dst = self.home / 'Library/Application Support/Loopback/Devices.plist'
        self.seed(self.dst, {'modelItems': []})
        self.assertEqual(self.restore(opt_in='Loopback').returncode, 0)
        self.assertEqual(plistlib.loads(self.dst.read_bytes()), {'setting': 'snapshot'})
        self.assertEqual(len(list(self.dst.parent.glob('Devices.plist.chezmoi.*'))), 1)

    def test_helper_and_version_guards(self):
        for env in ({'APP_TEST_PROCESSES': 'arkaudiod'}, {'APP_TEST_VERSION': '3.0'},
                    {'APP_TEST_INSTALLED': '0'}, {'APP_TEST_PGREP': '2'}):
            self.assertNotEqual(self.restore(opt_in='Loopback', **env).returncode, 0)
            self.assertFalse(self.dst.exists())
        self.assertNotEqual(self.restore(major='2.5.0', opt_in='Loopback', APP_TEST_VERSION='2.4.0').returncode, 0)
        self.assertFalse(self.dst.exists())

    def test_parent_symlink_rejected(self):
        (self.home / 'Library').symlink_to(self.root)
        self.assertNotEqual(self.restore(opt_in='Loopback').returncode, 0)
        self.assertFalse((self.root / 'Preferences').exists())

    def test_import_failure_rolls_back(self):
        self.seed(self.dst, {'setting': 'original'})
        result = self.restore(opt_in='Loopback', APP_TEST_IMPORT_FAIL='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(plistlib.loads(self.dst.read_bytes()), {'setting': 'original'})

    def test_legacy_replace_lib_arguments_still_work(self):
        self.seed(self.dst, {'old': True})
        command = 'replace_lib ' + ' '.join(shlex.quote(str(v)) for v in
                  [self.src, self.dst, 'Loopback', 'example.plist', 'true'])
        result = self.shell(command)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(plistlib.loads(self.dst.read_bytes()), {'setting': 'snapshot'})

    def test_rendered_selection_and_missing_desktop_without_fallback(self):
        config = self.root / 'chezmoi.toml'
        config.write_text('encryption = "gpg"\n')
        for hostname in ('MacBook-Test', 'MacStudio-Test'):
            expected = 'laptop.' if hostname.startswith('MacBook') else 'desktop.'
            for app in ('bartender', 'loopback', 'soundsource', 'tableplus', 'openin'):
                template = (SCRIPTS / ('run_' + app + '.sh.tmpl')).read_text()
                data = '{{ with dict "chezmoi" (dict "hostname" ' + json.dumps(hostname) + ') "include" ' + json.dumps(str(self.lib)) + ' "filesDir" ' + json.dumps(str(self.root / 'files')) + ' }}'
                result = subprocess.run(['chezmoi', '--config', str(config), '--cache', str(self.root / 'cache'),
                                         '--persistent-state', str(self.root / 'state'), 'execute-template'],
                                        input=data + template + '{{ end }}', capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                rendered = result.stdout.replace('$HOME', '$APP_TEST_HOME')
                if app in ('bartender', 'loopback', 'soundsource'):
                    self.assertIn(expected, rendered)
                    self.assertNotIn('laptop.' if expected == 'desktop.' else 'desktop.', rendered)
                else:
                    self.assertNotIn('laptop.', rendered)
                    self.assertNotIn('desktop.', rendered)
                script = self.root / 'rendered.zsh'
                script.write_text(rendered)
                self.assertEqual(subprocess.run(['/bin/zsh', '-n', str(script)]).returncode, 0)
                # Missing fixtures remain harmless even during ordinary script execution.
                result = self.shell(rendered)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((self.home / 'Library').exists())


if __name__ == '__main__':
    unittest.main()
