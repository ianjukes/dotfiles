#!/usr/bin/env python3
"""Explicit, encrypted snapshots for five apps. Provisioning never changes app settings."""

import argparse
import base64
import datetime
import json
import os
from pathlib import Path
import plistlib
import socket
import sqlite3
import subprocess
import sys
import tempfile
from xml.parsers.expat import ExpatError


class SnapshotError(Exception):
    pass


SPECS = {
    "Bartender": ("Bartender 7", "com.surteesstudios.Bartender", "7", False),
    "OpenIn": ("OpenIn", "app.loshadki.OpenIn.v4", "4", True),
    "Loopback": ("Loopback", "com.rogueamoeba.Loopback", "2", False),
    "SoundSource": ("SoundSource", "com.rogueamoeba.soundsource", "6", False),
    "TablePlus": ("TablePlus", "com.tinyapp.TablePlus", "26", True),
}
PREF_KEYS = {
    "Bartender": set("""ApplyStyleToNewBars BartenderBarOnlyOnNotchScreens
        BartenderHideMovingItemsNotification ClickingMenuBarTogglesBartender
        DisableAllTriggers HideItemsWhenShowingOthers HideSecondaryMenuBarItems
        HideShownItemsLeaveItemsToRightOfBartender HideShownItemsWhen ImageIndex
        MenuBarColoring-SpaceSettings MenuBarShape MenuBarStyle MouseExitDelay
        ProfileSettings TriggerSettings ReduceMenuItemSpacing ScrollingMenuBarShowsHiddenItems
        SeperatePills ShowAllItemsWhenDragging ShowDivider SimpleLayoutModeEnabled
        UseBartenderBar bartenderBarDoesntAutohide stored_style supressDuringMoves
        com.sureteesstudios.bartender.shortcuts""".split()),
    "Loopback": {"SUAllowsAutomaticUpdates", "SUAutomaticallyUpdate"},
    "SoundSource": set("""SSAudioExclusions applicationTheme followSystemAccent
        selectedAppColor deviceGroups.v1 hotkeys.v1 keyboardVolume menuAdditions
        menuBarIcon virtualVolumes""".split()),
    "TablePlus": {"ThemeKitTheme", "ViewSetting", "NSUseAnimatedFocusRing"},
}
# TablePlus nests UI preferences alongside history, saved queries and security settings.
# Keep an explicit list so new fields cannot silently become public-repo payloads.
TABLEPLUS_VIEW_KEYS = set("""AutoCompleteKey AutoHideTableScollers BackupFileNamePatterns
    DataFontSize DataRowPadding DefaultAvancedFilterColumn DefaultAvancedFilterColumnSort
    DefaultAvancedFilterOperator DefaultAvancedFilterState DefaultDarkTheme DefaultExecuteMode
    DefaultLightTheme DefaultSafeMode DefaultTableOrderBy DisableAlternatingRows
    DisableAutoDecodeSpatialData DisableAutoInsertClosingBraces DisableAutoSaveFavorites
    DisableAutoSuggestion DisableAutoUppercaseKeyword DisableAutocompleteForFunction
    DisableAutocompleteForKeyword DisableAutocompleteForTable DisableDatabaseStackViewDatabaseName
    DisableHighlightCurrentQuery DisableKeepConnectAlive DisableRestoreClosedWorkspace
    DisableSplitQueryResult DisableWrapLinesToEditorWidth EnableAutoAddWhitespace
    EnableAutoPrefixSchema EnableDatabaseStackViewConnectionName EnableQueryParams
    EnableSearchVariableInString EstimatedRowThreshold ExportCSVDecimalDelimiter ExportCSVDelimiter
    ExportCSVLineBreak ExportCSVSwap ExportFileNamePatterns ExportTableCSVDecimal ExportTableCSVLineBreak
    ExportTableCSVNotConvertNullToEmpty ExportTableCSVNotIncludeFieldName
    ExportTableCSVReplaceLineBreakWithSpace ExportTableCSVSwap ExportTableCSVTerminate
    ExportTableSQLCompressGzip ExportTableSQLDropIfExist ExportTableSQLNotIncludeContent
    ExportTableSQLNotIncludeStruct FavoriteSortKey HideOpenContainingFolderAfterExport
    ImportTableCSVSwap ImportTableCSVTerminate IndentType IsCountRowExactly IsDisableLoadingWallpaper
    IsDisableRowNumbersInQueryResults IsEnableConsoleLogSyntaxHighlighting IsEnableRowNumbersInItemViews
    Language LeftSidebarFontName LeftSidebarFontSize LeftSidebarPadding LineHeight NewTabMode
    QueryEditorFontName QueryEditorKeyBindingMode QueryParamsRegex QueryTimeOut ResultFilterMatchCase
    ReturnOnError SQLFontSize SearchMatchingStategy ShowInvisibleCharacters TabWidthSpaces
    TableDataFontName Tags ThemeName Themes""".split())
SUPPORT = "Library/Application Support/"
BARTENDER_DB = ("Library/Group Containers/24J875RH8J.com.surteesstudios.Bartender/"
                "Library/Application Support/default.store")
FILES = {
    "Bartender": {},
    "OpenIn": {"settings.openin-backup": None},
    "Loopback": {"Devices.plist": SUPPORT + "Loopback/Devices.plist"},
    "SoundSource": {name: SUPPORT + "SoundSource/" + name
                    for name in ("Models.v2.plist", "Presets.v2.plist")},
    "TablePlus": {name: SUPPORT + "com.tinyapp.TablePlus/Data/" + name
                  for name in ("Connections.plist", "ConnectionGroups.plist")},
}
FILES["TablePlus"]["connections.tableplusconnection"] = None
SNAPSHOTS = Path(__file__).resolve().parents[1] / "app-snapshots"
MAX_SIZE = 64 * 1024 * 1024


def profile(app, hostname):
    return "shared" if SPECS[app][3] else ("laptop" if hostname.startswith("MacBook") else "desktop")


def snapshot_path(root, app, hostname):
    return root / app / (profile(app, hostname) + ".json.asc")


def run(args, data=None):
    # Never emit subprocess diagnostics: they may contain private values or GPG arguments.
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise SnapshotError("Command failed: " + Path(args[0]).name + " (private diagnostics suppressed)")
    return result.stdout


def crypt(action, data):
    return run(["chezmoi", action], data)


def regular(path):
    for part in (path, *path.parents):
        if part.is_symlink():
            raise SnapshotError("Refusing a symlink in a configuration path")
    if path.exists() and not path.is_file():
        raise SnapshotError("Refusing a non-regular configuration file")


def read(path):
    regular(path)
    if not path.is_file() or path.stat().st_size > MAX_SIZE:
        raise SnapshotError("Required configuration is missing or too large")
    return path.read_bytes()


def atomic(path, data):
    regular(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".snapshot-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def preference_keys(app, prefs):
    result = {k: v for k, v in prefs.items() if k in PREF_KEYS[app]
              or (app == "TablePlus" and k.startswith("TPShortcut"))}
    if app == "TablePlus" and "ViewSetting" in result:
        result["ViewSetting"] = {k: v for k, v in result["ViewSetting"].items() if k in TABLEPLUS_VIEW_KEYS}
    return result


def unpack(data, app, selected_profile):
    try:
        if len(data) > MAX_SIZE:
            raise ValueError()
        package = json.loads(data)
        if (package["format"] != 1 or package["app"] != app
                or package["profile"] != selected_profile
                or package["version"].split(".")[0] != SPECS[app][2]):
            raise ValueError()
        files = {name: base64.b64decode(value, validate=True)
                 for name, value in package["files"].items()}
        allowed = set(FILES[app]) | ({"preferences.plist"} if app in PREF_KEYS else set())
        if not files or not set(files) <= allowed or any(not b for b in files.values()):
            raise ValueError()
        if app in PREF_KEYS:
            prefs = plistlib.loads(files["preferences.plist"])
            if not isinstance(prefs, dict) or preference_keys(app, prefs) != prefs:
                raise ValueError()
        if app == "Loopback":
            devices = plistlib.loads(files["Devices.plist"])
            if not isinstance(devices["modelItems"], list) or "LBModelListVersion" not in devices:
                raise ValueError()
        if app == "SoundSource":
            models = plistlib.loads(files["Models.v2.plist"])
            if not isinstance(models["models"], list) or not isinstance(plistlib.loads(files["Presets.v2.plist"]), list):
                raise ValueError()
            if any(m.get("deviceSelection", {}).get("history") for m in models["models"]):
                raise SnapshotError("SoundSource contains device-selection history; review before capture rather than copying history")
        if app == "TablePlus":
            # Populated lists travel through the vendor's export, never a home-made format.
            native = "connections.tableplusconnection" in files
            raw = {"Connections.plist", "ConnectionGroups.plist"} & set(files)
            if native and raw or not native and len(raw) != 2:
                raise ValueError()
            for name in raw:
                if plistlib.loads(files[name]) != []:
                    raise ValueError()
        if app == "OpenIn" and not files["settings.openin-backup"].startswith(b"pbze"):
            raise ValueError()
        return package, files
    except (ValueError, KeyError, TypeError, AttributeError, plistlib.InvalidFileException, OverflowError, ExpatError):
        raise SnapshotError("Invalid or incompatible snapshot; no settings changed") from None


def pack(app, hostname, version, files):
    data = json.dumps({"format": 1, "app": app, "profile": profile(app, hostname),
                       "version": version, "captured": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       "files": {k: base64.b64encode(v).decode("ascii") for k, v in files.items()}},
                      sort_keys=True).encode()
    unpack(data, app, profile(app, hostname))
    return data


def version(app):
    bundle, domain, major, _ = SPECS[app]
    info = plistlib.loads(read(Path("/Applications") / (bundle + ".app") / "Contents/Info.plist"))
    value = info["CFBundleShortVersionString"]
    if info["CFBundleIdentifier"] != domain or value.split(".")[0] != major:
        raise SnapshotError("App version/distribution changed; review storage before capture/restore")
    return value


def assert_closed(app):
    # comm (not argv) avoids reading credentials passed to unrelated processes.
    processes = run(["/bin/ps", "-axo", "comm="]).decode().lower().splitlines()
    names = {"Bartender": ("bartender", "menubaragent", "notchbar"),
             "Loopback": ("loopback", "arkaudiod", "aceagent"),
             "SoundSource": ("soundsource", "arkaudiod", "aceagent"),
             "TablePlus": ("tableplus",)}[app]
    if any(any(name in proc for name in names) for proc in processes):
        raise SnapshotError("Quit " + app + " and its background helpers first; see docs/app-snapshots.md. Nothing was terminated.")


def sqlite_snapshot(source, destination):
    """Read-only online backup includes committed WAL data. Never use immutable=1 here."""
    regular(source)
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src:
        with sqlite3.connect(destination) as dst:
            src.backup(dst)
            if dst.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise SnapshotError("Invalid SQLite configuration")


def inspect_bartender(home):
    # The inspected v7 database stores widgets, not menu profiles. Do not archive its
    # empty widget store/transaction log, or silently omit later user-created widgets.
    source = home / BARTENDER_DB
    if not source.exists():
        raise SnapshotError("Bartender group store missing; first launch and review storage")
    with tempfile.TemporaryDirectory(prefix="dotfiles-app-", dir="/private/tmp") as tmp:
        target = Path(tmp) / "inspection.sqlite"
        sqlite_snapshot(source, target)
        with sqlite3.connect(target) as db:
            if db.execute("SELECT count(*) FROM ZWIDGETSETTINGS").fetchone()[0]:
                raise SnapshotError("Bartender has widget data: obtain vendor backup guidance before extending this menu-preference snapshot")


def capture(app, hostname, home, native_export=None, history_excluded=False, passwords_excluded=False):
    app_version = version(app)
    if app == "OpenIn":
        if not native_export or not history_excluded:
            raise SnapshotError("OpenIn capture pending: supply a native .openin-backup export with no history and --history-excluded; do not copy local.sqlite")
        files = {"settings.openin-backup": read(native_export)}
    else:
        # Reading stable files does not require stopping an unrelated audio engine.
        # Capture verifies the entire input set twice; restore has stricter guards.
        if app == "Bartender":
            inspect_bartender(home)
        domain = SPECS[app][1]
        def collect():
            prefs = plistlib.loads(run(["/usr/bin/defaults", "export", domain, "-"]))
            result = {"preferences.plist": plistlib.dumps(preference_keys(app, prefs))}
            for name, relative in FILES[app].items():
                if relative and not (app == "TablePlus" and native_export):
                    result[name] = read(home / relative)
            return result
        files = collect()
        if files != collect():
            raise SnapshotError("Configuration changed during capture; quit the app and retry")
        if app == "TablePlus":
            # Settings.json currently contains only closed-workspace history.
            settings = home / (SUPPORT + "com.tinyapp.TablePlus/Data/Settings.json")
            if set(json.loads(read(settings))) - {"closedWorkspaces"}:
                raise SnapshotError("TablePlus Settings.json gained unknown settings; review its safe fields")
            if native_export:
                if not passwords_excluded or native_export.suffix != ".tableplusconnection":
                    raise SnapshotError("Use a native .tableplusconnection export with both password options off and --passwords-excluded")
                files["connections.tableplusconnection"] = read(native_export)
    return pack(app, hostname, app_version, files)


def provision(app, hostname, root, destination):
    source = snapshot_path(root, app, hostname)
    if not source.is_file():
        print(app + ": missing " + profile(app, hostname) + " snapshot; run capture on that Mac (see docs/app-snapshots.md). Existing settings untouched.")
        return False
    target = snapshot_path(destination, app, hostname)
    data = read(source)
    if not data.startswith(b"-----BEGIN PGP MESSAGE-----"):
        raise SnapshotError("Snapshot is not an armored encrypted file")
    if not target.exists() or read(target) != data:
        atomic(target, data)
    print(app + ": encrypted snapshot provisioned; restore is an explicit action")
    return True


class FileBackend:
    """File-only test backend: never invokes defaults or other macOS tools."""
    def __init__(self, home):
        self.home = home.resolve()
        real = Path.home().resolve()
        if self.home == real or self.home in real.parents or real in self.home.parents:
            raise SnapshotError("File backend must use an isolated destination outside the real home")

    def preferences(self, domain):
        p = self.home / "Library/Preferences" / (domain + ".plist")
        return plistlib.loads(read(p)) if p.exists() else {}

    def write_preferences(self, domain, data):
        atomic(self.home / "Library/Preferences" / (domain + ".plist"), data)

    def remove_preferences(self, domain):
        (self.home / "Library/Preferences" / (domain + ".plist")).unlink(missing_ok=True)


class MacBackend:
    def __init__(self):
        self.home = Path.home()

    def preferences(self, domain):
        p = self.home / "Library/Preferences" / (domain + ".plist")
        return plistlib.loads(run(["/usr/bin/defaults", "export", domain, "-"])) if p.exists() else {}

    def write_preferences(self, domain, data):
        # cfprefsd must see the write; do not replace a live preference file behind it.
        run(["/usr/bin/defaults", "import", domain, "-"], data)
        p = self.home / "Library/Preferences" / (domain + ".plist")
        os.chmod(p, 0o600)

    def remove_preferences(self, domain):
        run(["/usr/bin/defaults", "delete", domain])


def restore_files(app, files, backend, replace=False):
    """Prepare all files and an original backup before the first destination change."""
    domain = SPECS[app][1]
    destinations = {backend.home / rel: files[name] for name, rel in FILES[app].items()
                    if rel and name in files}
    pref_path = backend.home / "Library/Preferences" / (domain + ".plist")
    for p in [pref_path, *destinations]:
        regular(p)
    existing = any(p.exists() for p in [pref_path, *destinations])
    # Treat any existing app state as occupied, even if a snapshot omits that file.
    support = {"Bartender": backend.home / BARTENDER_DB,
               "Loopback": backend.home / (SUPPORT + "Loopback"),
               "SoundSource": backend.home / (SUPPORT + "SoundSource"),
               "TablePlus": backend.home / (SUPPORT + "com.tinyapp.TablePlus/Data")}[app]
    if (existing or support.exists()) and not replace:
        print(app + ": existing configuration protected; use restore --replace deliberately")
        return False
    current = backend.preferences(domain)
    had_preferences = pref_path.exists()
    incoming = plistlib.loads(files["preferences.plist"])
    # Preserve license/onboarding keys, replace only settings within this feature's scope.
    merged = {k: v for k, v in current.items() if k not in preference_keys(app, current)}
    merged.update(incoming)
    if app == "TablePlus" and ("ViewSetting" in current or "ViewSetting" in incoming):
        view = {k: v for k, v in current.get("ViewSetting", {}).items() if k not in TABLEPLUS_VIEW_KEYS}
        view.update(incoming.get("ViewSetting", {}))
        merged["ViewSetting"] = view
    new_prefs = plistlib.dumps(merged)
    old_prefs = plistlib.dumps(current)
    originals = {p: read(p) if p.exists() else None for p in destinations}
    if new_prefs == old_prefs and all(originals[p] == value for p, value in destinations.items()):
        print(app + ": snapshot already matches; nothing changed")
        return True
    # Private staging/backups are outside the Dropbox checkout.
    backup_root = backend.home / ".local/share/chezmoi/app-snapshot-backups"
    regular(backup_root / "placeholder")
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = Path(tempfile.mkdtemp(prefix=app + "-", dir=backup_root))
    atomic(backup / "preferences.plist", old_prefs)
    atomic(backup / "restore-info.json", json.dumps({"preferences_existed": had_preferences,
           "files_existed": {p.name: data is not None for p, data in originals.items()}}).encode())
    for p, data in originals.items():
        if data is not None:
            atomic(backup / p.name, data)
    with tempfile.TemporaryDirectory(prefix="dotfiles-app-", dir="/private/tmp") as tmp:
        prepared = {}
        for i, (p, data) in enumerate(destinations.items()):
            stage = Path(tmp) / str(i)
            atomic(stage, data)
            prepared[p] = stage
        changed = []
        prefs_attempted = False
        try:
            for p, stage in prepared.items():
                atomic(p, read(stage))
                changed.append(p)
            prefs_attempted = True
            backend.write_preferences(domain, new_prefs)
        except Exception:
            failed = False
            for p in reversed(changed):
                try:
                    if originals[p] is None:
                        p.unlink()
                    else:
                        atomic(p, originals[p])
                except OSError:
                    failed = True
            if prefs_attempted:
                try:
                    if had_preferences:
                        backend.write_preferences(domain, old_prefs)
                    else:
                        backend.remove_preferences(domain)
                except Exception:
                    failed = True
            raise SnapshotError("Restore failed; " + ("rollback incomplete" if failed else "originals restored") + "; backup: " + str(backup)) from None
    print(app + ": restored; previous settings retained at " + str(backup))
    return True


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("capture", "provision", "restore"))
    parser.add_argument("app", choices=tuple(SPECS) + ("all",))
    parser.add_argument("--export", type=Path, dest="native_export")
    parser.add_argument("--history-excluded", action="store_true")
    parser.add_argument("--passwords-excluded", action="store_true")
    parser.add_argument("--replace", action="store_true", help="explicitly replace existing settings, keeping private backups")
    parser.add_argument("--hostname", help="provision only: hostname supplied by chezmoi")
    args = parser.parse_args()
    if args.hostname and args.action != "provision":
        parser.error("--hostname is only for provisioning; capture/restore use this Mac's hostname")
    if args.app == "all" and args.action != "provision":
        parser.error("capture/restore one app at a time")
    hostname = args.hostname or socket.gethostname()
    for app in SPECS if args.app == "all" else (args.app,):
        path = snapshot_path(SNAPSHOTS, app, hostname)
        if args.action == "capture":
            data = capture(app, hostname, Path.home(), args.native_export,
                           args.history_excluded, args.passwords_excluded)
            encrypted = crypt("encrypt", data)
            if not encrypted.startswith(b"-----BEGIN PGP MESSAGE-----"):
                raise SnapshotError("Expected the repository's armored GPG encryption")
            # Round-trip before replacing any previously captured snapshot.
            if crypt("decrypt", encrypted) != data:
                raise SnapshotError("Encryption verification failed; previous snapshot untouched")
            atomic(path, encrypted)
            print(app + ": captured encrypted " + profile(app, hostname) + " snapshot")
        elif args.action == "provision":
            provision(app, hostname, SNAPSHOTS, Path.home() / ".local/share/chezmoi/app-snapshots")
        elif not path.is_file():
            print(app + ": snapshot missing; capture on the matching Mac first. Existing settings untouched.")
        else:
            package, files = unpack(crypt("decrypt", read(path)), app, profile(app, hostname))
            installed = version(app)
            if tuple(map(int, installed.split("."))) < tuple(map(int, package["version"].split("."))):
                raise SnapshotError("Install the captured app version or newer before restoring")
            if app != "OpenIn":
                assert_closed(app)
                restored = restore_files(app, files, MacBackend(), args.replace)
                if restored and app in ("SoundSource", "Loopback"):
                    print(app + ": before playback/capture, verify and reselect every audio device, application source and monitor in the app. Native identifiers are not assumed portable.")
            for name, rel in FILES[app].items():
                if rel is None and name in files:
                    target = Path.home() / ".local/share/chezmoi/app-snapshot-imports" / app / name
                    regular(target)
                    if target.exists() and read(target) != files[name]:
                        if not args.replace:
                            raise SnapshotError("Existing import file protected; use --replace to save a backup and replace it")
                        fd, old = tempfile.mkstemp(prefix=name + ".backup-", dir=target.parent)
                        os.close(fd)
                        atomic(Path(old), read(target))
                    atomic(target, files[name])
                    print(app + ": native export ready at " + str(target) + "; import in the app (docs/app-snapshots.md), then delete this decrypted file")


if __name__ == "__main__":
    try:
        main()
    except (SnapshotError, OSError, ValueError, sqlite3.Error, plistlib.InvalidFileException, ExpatError) as error:
        # Detailed parser errors can quote private input. Only our own messages are safe.
        print(str(error) if isinstance(error, SnapshotError) else "Snapshot operation failed; configuration was not captured/restored successfully", file=sys.stderr)
        sys.exit(1)
