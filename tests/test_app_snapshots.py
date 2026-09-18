"""Synthetic fixtures only. No imports into the user's macOS preference domains."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import plistlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "home/.files/lib/app_snapshots.py"
spec = importlib.util.spec_from_file_location("snapshots", MODULE)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def fixture(app, hostname="MacBook-Test"):
    files = {"preferences.plist": plistlib.dumps({})}
    if app == "Loopback":
        files["Devices.plist"] = plistlib.dumps({"LBModelListVersion": 1, "modelItems": []})
    elif app == "SoundSource":
        files.update({"Models.v2.plist": plistlib.dumps({"models": []}),
                      "Presets.v2.plist": plistlib.dumps([])})
    elif app == "TablePlus":
        files.update({name: plistlib.dumps([]) for name in ("Connections.plist", "ConnectionGroups.plist")})
    elif app == "OpenIn":
        files = {"settings.openin-backup": b"pbze synthetic fixture"}
    return s.pack(app, hostname, s.SPECS[app][2] + ".0", files)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp", prefix="app-snapshot-tests-")
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.backend = s.FileBackend(self.home)
        # Any accidental platform call or crypto invocation is a test failure.
        self.guard = patch.object(s, "run", side_effect=AssertionError("No macOS commands in fixtures"))
        self.guard.start()
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()

    def tearDown(self):
        self.output.__exit__(None, None, None)
        self.guard.stop()
        self.tmp.cleanup()

    def files(self, app, hostname="MacBook-Test"):
        return s.unpack(fixture(app, hostname), app, s.profile(app, hostname))[1]

    def pref(self, app):
        return self.home / "Library/Preferences" / (s.SPECS[app][1] + ".plist")

    def test_profile_selection(self):
        for app in ("Bartender", "Loopback", "SoundSource"):
            self.assertEqual(s.profile(app, "MacBook-Air"), "laptop")
            for name in ("MacStudio", "macbook", "iMac", ""):
                self.assertEqual(s.profile(app, name), "desktop")
        for app in ("OpenIn", "TablePlus"):
            self.assertEqual(s.profile(app, "MacBook"), "shared")
            self.assertEqual(s.profile(app, "MacStudio"), "shared")

    def test_no_cross_machine_fallback_and_late_capture(self):
        source, dest = self.root / "repo", self.root / "provisioned"
        ciphertext = b"-----BEGIN PGP MESSAGE-----\nsynthetic"
        s.atomic(s.snapshot_path(source, "Loopback", "MacBook"), ciphertext)
        self.assertFalse(s.provision("Loopback", "MacStudio", source, dest))
        self.assertFalse(dest.exists())
        s.atomic(s.snapshot_path(source, "Loopback", "MacStudio"), ciphertext)
        self.assertTrue(s.provision("Loopback", "MacStudio", source, dest))
        self.assertTrue(s.provision("Loopback", "MacStudio", source, dest))
        self.assertFalse((self.home / "Library").exists())

    def test_shared_provision_and_invalid_ciphertext(self):
        source, dest = self.root / "repo", self.root / "provisioned"
        path = s.snapshot_path(source, "TablePlus", "MacBook")
        s.atomic(path, b"-----BEGIN PGP MESSAGE-----\nsynthetic")
        s.provision("TablePlus", "MacStudio", source, dest)
        target = s.snapshot_path(dest, "TablePlus", "MacBook")
        original = target.read_bytes()
        s.atomic(path, b"plaintext is forbidden")
        with self.assertRaises(s.SnapshotError):
            s.provision("TablePlus", "MacStudio", source, dest)
        self.assertEqual(target.read_bytes(), original)

    def test_invalid_and_wrong_profile_rejected(self):
        for data in (b"", b"{}", b"not json", fixture("Loopback", "MacStudio")):
            with self.assertRaises(s.SnapshotError):
                s.unpack(data, "Loopback", "laptop")
        package = json.loads(fixture("Loopback"))
        package["files"]["../../outside"] = "YQ=="
        with self.assertRaises(s.SnapshotError):
            s.unpack(json.dumps(package).encode(), "Loopback", "laptop")

    def test_bad_plist_and_license_keys_rejected(self):
        for data in (b"broken", b'<?xml version="1.0"?><plist><dict>', plistlib.dumps({"registrationInfo": "secret"})):
            files = self.files("Loopback")
            files["preferences.plist"] = data
            with self.assertRaises(s.SnapshotError):
                s.pack("Loopback", "MacBook", "2.5.0", files)

    def test_empty_connections_only_without_vendor_export(self):
        files = self.files("TablePlus")
        files["Connections.plist"] = plistlib.dumps([{"Host": "synthetic.invalid"}])
        with self.assertRaises(s.SnapshotError):
            s.pack("TablePlus", "MacBook", "26.0", files)

    def test_clean_restore_then_protect_new_app_changes(self):
        for app in ("Bartender", "Loopback", "SoundSource", "TablePlus"):
            self.assertTrue(s.restore_files(app, self.files(app), self.backend))
            s.atomic(self.pref(app), plistlib.dumps({"user_changed": True}))
            self.assertFalse(s.restore_files(app, self.files(app), self.backend))
            self.assertEqual(plistlib.loads(self.pref(app).read_bytes()), {"user_changed": True})

    def test_replace_preserves_license_and_backs_up_existing(self):
        original = {"registrationInfo": "synthetic-license", "ThemeKitTheme": "old"}
        s.atomic(self.pref("TablePlus"), plistlib.dumps(original))
        files = self.files("TablePlus")
        files["preferences.plist"] = plistlib.dumps({"ThemeKitTheme": "new"})
        self.assertFalse(s.restore_files("TablePlus", files, self.backend))
        self.assertTrue(s.restore_files("TablePlus", files, self.backend, replace=True))
        self.assertEqual(self.backend.preferences(s.SPECS["TablePlus"][1]),
                         {"registrationInfo": "synthetic-license", "ThemeKitTheme": "new"})
        backups = list((self.home / ".local/share/chezmoi/app-snapshot-backups").glob("TablePlus-*"))
        self.assertEqual(plistlib.loads((backups[0] / "preferences.plist").read_bytes()), original)
        self.assertEqual(self.pref("TablePlus").stat().st_mode & 0o777, 0o600)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o700)
        s.restore_files("TablePlus", files, self.backend, replace=True)
        self.assertEqual(len(list(backups[0].parent.iterdir())), 1)

    def test_existing_support_directory_protected(self):
        (self.home / "Library/Application Support/SoundSource").mkdir(parents=True)
        self.assertFalse(s.restore_files("SoundSource", self.files("SoundSource"), self.backend))
        self.assertFalse(self.pref("SoundSource").exists())

    def test_symlink_parent_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.home / "Library").symlink_to(outside)
        with self.assertRaises(s.SnapshotError):
            s.restore_files("Loopback", self.files("Loopback"), self.backend, replace=True)
        self.assertEqual(list(outside.iterdir()), [])

    def test_file_backend_rejects_real_home(self):
        for target in (Path.home(), Path.home() / "Library", Path("/")):
            with self.assertRaises(s.SnapshotError):
                s.FileBackend(target)

    def test_preference_failure_rolls_back_data_files(self):
        original = b"original device bytes"
        target = self.home / s.FILES["Loopback"]["Devices.plist"]
        s.atomic(target, original)
        with patch.object(self.backend, "write_preferences", side_effect=s.SnapshotError("synthetic failure")):
            with self.assertRaises(s.SnapshotError):
                s.restore_files("Loopback", self.files("Loopback"), self.backend, replace=True)
        self.assertEqual(target.read_bytes(), original)
        self.assertFalse(self.pref("Loopback").exists())

    def test_decryption_failure_leaves_existing_untouched(self):
        root = self.root / "repo"
        s.atomic(s.snapshot_path(root, "Loopback", "MacBook"), b"ciphertext")
        s.atomic(self.pref("Loopback"), plistlib.dumps({"keep": True}))
        with patch.object(s, "SNAPSHOTS", root), patch.object(s.socket, "gethostname", return_value="MacBook"), \
                patch.object(s, "crypt", side_effect=s.SnapshotError("decryption failed")), \
                patch.object(s, "MacBackend", side_effect=AssertionError("Must not reach live backend")), \
                patch.object(s.sys, "argv", ["snapshots", "restore", "Loopback", "--replace"]):
            with self.assertRaises(s.SnapshotError):
                s.main()
        self.assertEqual(plistlib.loads(self.pref("Loopback").read_bytes()), {"keep": True})

    def test_encryption_failure_keeps_old_capture(self):
        root = self.root / "repo"
        path = s.snapshot_path(root, "Loopback", "MacBook")
        s.atomic(path, b"old ciphertext")
        with patch.object(s, "SNAPSHOTS", root), patch.object(s.socket, "gethostname", return_value="MacBook"), \
                patch.object(s, "capture", return_value=fixture("Loopback")), \
                patch.object(s, "crypt", side_effect=s.SnapshotError("encryption failed")), \
                patch.object(s.sys, "argv", ["snapshots", "capture", "Loopback"]):
            with self.assertRaises(s.SnapshotError):
                s.main()
        self.assertEqual(path.read_bytes(), b"old ciphertext")

    def test_sqlite_backup_includes_pending_wal(self):
        source = self.root / "live.sqlite"
        writer = sqlite3.connect(source)
        try:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute("CREATE TABLE setting (value TEXT)")
            writer.execute("INSERT INTO setting VALUES ('committed in WAL')")
            writer.commit()
            before = source.read_bytes()
            target = self.root / "snapshot.sqlite"
            s.sqlite_snapshot(source, target)
            with sqlite3.connect(target) as db:
                self.assertEqual(db.execute("SELECT value FROM setting").fetchone()[0], "committed in WAL")
            self.assertEqual(source.read_bytes(), before)
        finally:
            writer.close()

    def test_openin_never_reads_live_database(self):
        with patch.object(s, "version", return_value="4.4.4"):
            with self.assertRaises(s.SnapshotError):
                s.capture("OpenIn", "MacBook", self.home)

    def test_audio_history_rejected(self):
        files = self.files("SoundSource")
        files["Models.v2.plist"] = plistlib.dumps({"models": [{"deviceSelection": {"history": ["old"]}}]})
        with self.assertRaises(s.SnapshotError):
            s.pack("SoundSource", "MacBook", "6.1.4", files)

    def test_process_guards_cover_helpers_and_fail_closed(self):
        for app, process in (("Bartender", "MenuBarAgent"), ("SoundSource", "arkaudiod"),
                             ("Loopback", "loopbackd"), ("TablePlus", "/Applications/TablePlus.app/Contents/MacOS/TablePlus")):
            with patch.object(s, "run", return_value=process.encode()):
                with self.assertRaises(s.SnapshotError):
                    s.assert_closed(app)
        with patch.object(s, "run", side_effect=s.SnapshotError("ps unavailable")):
            with self.assertRaises(s.SnapshotError):
                s.assert_closed("Loopback")

    def test_tableplus_nested_history_and_security_are_not_captured(self):
        prefs = {"ViewSetting": {"SQLFontSize": 14, "RecentMatchedItems": ["private"],
                                "Variables": {"credential": "private"}, "IsEnableOpenAIChat": True},
                 "TPShortcutRunCurrentQuery": "shortcut", "license": "private"}
        self.assertEqual(s.preference_keys("TablePlus", prefs),
                         {"ViewSetting": {"SQLFontSize": 14}, "TPShortcutRunCurrentQuery": "shortcut"})
        s.atomic(self.pref("TablePlus"), plistlib.dumps(prefs))
        files = self.files("TablePlus")
        files["preferences.plist"] = plistlib.dumps({"ViewSetting": {"SQLFontSize": 16}})
        s.restore_files("TablePlus", files, self.backend, replace=True)
        after = self.backend.preferences(s.SPECS["TablePlus"][1])
        self.assertEqual(after["ViewSetting"]["RecentMatchedItems"], ["private"])
        self.assertTrue(after["ViewSetting"]["IsEnableOpenAIChat"])
        self.assertEqual(after["ViewSetting"]["SQLFontSize"], 16)
        self.assertEqual(after["license"], "private")
        # A sparse snapshot must also preserve out-of-scope nested fields.
        s.restore_files("TablePlus", self.files("TablePlus"), self.backend, replace=True)
        after = self.backend.preferences(s.SPECS["TablePlus"][1])
        self.assertEqual(after["ViewSetting"]["RecentMatchedItems"], ["private"])

    def test_capture_sound_source_only_active_files_and_allowed_preferences(self):
        for name, rel in s.FILES["SoundSource"].items():
            s.atomic(self.home / rel, self.files("SoundSource")[name])
        s.atomic(self.home / "Library/Application Support/SoundSource/Models.plist", b"obsolete")
        with patch.object(s, "version", return_value="6.1.4"), \
                patch.object(s, "run", return_value=plistlib.dumps({"hotkeys.v1": {}, "registrationInfo": "private"})):
            data = s.capture("SoundSource", "MacBook", self.home)
        _, files = s.unpack(data, "SoundSource", "laptop")
        self.assertEqual(set(files), {"Models.v2.plist", "Presets.v2.plist", "preferences.plist"})
        self.assertNotIn(b"private", files["preferences.plist"])

    def test_capture_rejects_concurrent_changes(self):
        s.atomic(self.home / s.FILES["Loopback"]["Devices.plist"], self.files("Loopback")["Devices.plist"])
        with patch.object(s, "version", return_value="2.5.0"), \
                patch.object(s, "run", side_effect=[plistlib.dumps({"SUAutomaticallyUpdate": False}),
                                                   plistlib.dumps({"SUAutomaticallyUpdate": True})]):
            with self.assertRaises(s.SnapshotError):
                s.capture("Loopback", "MacBook", self.home)

    def test_tableplus_requires_review_of_new_settings_file_fields(self):
        for name, rel in s.FILES["TablePlus"].items():
            if rel:
                s.atomic(self.home / rel, plistlib.dumps([]))
        settings = self.home / "Library/Application Support/com.tinyapp.TablePlus/Data/Settings.json"
        s.atomic(settings, b'{"closedWorkspaces": [], "newField": true}')
        with patch.object(s, "version", return_value="26.10.20"), \
                patch.object(s, "run", return_value=plistlib.dumps({})):
            with self.assertRaises(s.SnapshotError):
                s.capture("TablePlus", "MacBook", self.home)

    def test_bartender_populated_widget_store_requires_review(self):
        p = self.home / s.BARTENDER_DB
        p.parent.mkdir(parents=True)
        with sqlite3.connect(p) as db:
            db.execute("CREATE TABLE ZWIDGETSETTINGS (Z_PK INTEGER)")
        s.inspect_bartender(self.home)
        with sqlite3.connect(p) as db:
            db.execute("INSERT INTO ZWIDGETSETTINGS VALUES (1)")
        with self.assertRaises(s.SnapshotError):
            s.inspect_bartender(self.home)


if __name__ == "__main__":
    unittest.main()
