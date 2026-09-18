# Five application preference backups

These apps use the existing `.files/prefs/<App>/` storage and `replace_lib` restoration
pattern. Files are ordinary plists encrypted individually with the repository's
existing chezmoi/GPG configuration. There is no custom archive format, snapshot
manager, duplicate staging directory or additional installation logic.

Hostnames beginning with `MacBook` select `laptop.` files; all other hostnames select
`desktop.` files. Bartender, Loopback and SoundSource never cross-fallback. OpenIn
and TablePlus use filenames without a machine prefix. “Shared” means restoring the
same repository configuration on both Macs, not continuous two-way synchronisation.

## What is actually saved

The 2026-09-18 captures were retained byte-for-byte when removing the earlier JSON
wrapper, then re-encrypted as individual plists. Versions and contents:

| Directory below `home/.files/prefs/` | Files and contents |
| --- | --- |
| `Bartender` | `laptop.com.surteesstudios.Bartender.plist.asc`: filtered preferences from Bartender 7.0.1; one profile, three trigger records, layouts, shortcuts, styles and embedded image data. |
| `Loopback` | `laptop.com.rogueamoeba.Loopback.plist.asc`, `laptop.Devices.plist.asc`: Loopback 2.5.0 preferences and **zero virtual devices**. No populated routing was backed up. |
| `SoundSource` | `laptop.com.rogueamoeba.soundsource.plist.asc`, `laptop.Models.v2.plist.asc`, `laptop.Presets.v2.plist.asc`: SoundSource 6.1.4 preferences, 187 application models and three system-device models, embedded built-in EQ/overdrive settings, and **zero saved presets**. |
| `TablePlus` | `com.tinyapp.TablePlus.plist.asc`, `Connections.plist.asc`, `ConnectionGroups.plist.asc`: TablePlus 26.10.20 general preferences/shortcuts and **empty connection and group lists**. |
| `OpenIn` | **Pending**, by request: a history-free native export is needed. No database or older iCloud backup was captured. |

Desktop captures for Bartender, Loopback and SoundSource are still needed. Capture
on the desktop itself; do not rename or duplicate laptop data.

Storage investigation matters:

* Bartender's group-container `24J875RH8J.com.surteesstudios.Bartender/Library/Application Support/default.store`
  had zero `ZWIDGETSETTINGS` rows, verified using a read-only SQLite backup that included
  committed WAL data. Its empty widget store/transaction metadata is excluded. Menu
  profiles and rules are in its preference domain. OS-owned menu positions, migration
  flags, window maps, licences and permission data are excluded. Re-investigate if
  widget records appear; a preference plist is not a complete backup of arbitrary
  Bartender 7 functionality.
* OpenIn 4.4.4's group-container `4QE86VV38D.app.loshadki.OpenIn/Library/Application Support/OpenIn/local.sqlite`
  contained four handlers, twelve app entries, eight rules and 22 history entries,
  with pending WAL data. Do not copy it, its Chrome profile cache or whole containers.
* SoundSource's `Models.v2.plist` and `Presets.v2.plist` were the current pair, updated
  together on the inspection date. Older `Models.plist`, `Presets.plist`, `Sources.plist`,
  `CustomPresets.plist` and `.migratedModelsV6` are excluded migration data. The inspected
  effects are embedded; the downloaded `hpeq_profiles` catalogue is excluded. Review
  storage again after upgrades or adding third-party effects/external EQ assets.
* TablePlus's `Data/Settings.json` contained only `closedWorkspaces`, so it is excluded
  session history. Its preference dictionary also mixes general settings with recents,
  saved queries, security and AI settings. `filter_app_prefs.py` only emits the reviewed
  keys listed in `app_pref_keys.json`; it does not capture, encrypt or restore files.

## Deliberate restoration

Ordinary chezmoi runs do **not** overwrite these apps. The per-app `run_` templates
report availability/missing captures, without a run-once completion marker. A later
capture therefore remains eligible. To restore one app, render and execute only its
template with an opt-in scoped to that command. From the repository root:

```zsh
(
  set -eufo pipefail
  restore_script=$(mktemp /private/tmp/chezmoi-restore.XXXXXX)
  trap 'rm -f "$restore_script"' EXIT
  chezmoi execute-template < home/.chezmoiscripts/darwin/app_libs/run_soundsource.sh.tmpl > "$restore_script"
  DOTFILES_RESTORE_APP=SoundSource zsh "$restore_script"
)
```

Choose the matching filename and opt-in value:

| Template | Opt-in value |
| --- | --- |
| `run_bartender.sh.tmpl` | `'Bartender 7'` |
| `run_loopback.sh.tmpl` | `Loopback` |
| `run_soundsource.sh.tmpl` | `SoundSource` |
| `run_tableplus.sh.tmpl` | `TablePlus` |

Use the same command to deliberately restore again. Do not export the opt-in into
your shell startup files or use a broad `chezmoi apply` for this operation. These
commands use the configured `.include`/`.filesDir`, just like the existing scripts;
ensure chezmoi points at this checkout. No `chezmoi apply` is needed to run one template.

The small `restore_app_libs` guard in `macos.sh` checks the app's reviewed major/minimum version,
background processes and all paths, then decrypts/lints **every** source before calling
`replace_lib` for each destination. Missing files change nothing. Plaintext preparation
is in private `/private/tmp` directories and is removed afterward. `replace_lib` keeps
its atomic file replacement, backup and real-error handling. Its optional `merge` mode
imports selected preference keys through `defaults`/cfprefsd while preserving unrelated
existing keys, including licences; TablePlus's nested `ViewSetting` is also merged.
Existing callers retain the original replacement behaviour.

Existing files are backed up beside their destinations using the established
`.chezmoi.<timestamp>.<unique>` suffix, mode 0600. Source/staging files are validated
before changes. This is **per-file restoration**, not an application-wide transaction:
if a later write fails, earlier successful replacements remain and their backups are
available. Fix the reported problem and rerun, or restore those backups while the app
is closed. Failed preference imports attempt the existing helper's rollback.

Quit apps via their menus, not merely their windows. The guard also checks known
Bartender/MenuBarAgent, Loopback/loopbackd, SoundSource and TablePlus helpers and
conservatively refuses audio restoration while ARK/ACE is running. If helpers persist,
retry after a normal logout/restart before opening audio apps, or obtain the vendor's
supported shutdown advice. Do not kill services, unload drivers or alter extensions
to bypass the guard. The scripts never terminate anything or manipulate drivers.

Launch Bartender once to initialise its own store, then quit before restoring.
Approve its requested permissions yourself and check every display/layout: native
menu positions and Bartender 7 migrations need fresh-Mac validation. See the
[vendor's migration guidance](https://www.macbartender.com/Bartender6/support/).

For audio apps, use the vendor's first-launch setup and approvals separately. Native
device/application references were inspected but cannot be asserted portable between
Macs. **Before playback or capture**, connect the intended hardware and verify every
system device, app output, group, effect, shortcut, Loopback source/channel/monitor;
reselect missing or incorrect references. Matching laptop/desktop filenames does not
prove device IDs match. Third-party effects and their licences must be installed
separately. The current empty Loopback list has no device references to validate.

## Capture and refresh

Capture is explicit; nothing reverse-syncs during chezmoi runs. Quit the source app
yourself and verify its storage still matches the investigated version above. For
Bartender, verify its widget table is still empty with a read-only query (SQLite
reads the WAL; do not copy the live database):

```sh
sqlite3 -readonly "$HOME/Library/Group Containers/24J875RH8J.com.surteesstudios.Bartender/Library/Application Support/default.store" \
  'SELECT count(*) FROM ZWIDGETSETTINGS;'
```

Stop and investigate if that count is nonzero, SoundSource uses newer model files or
external assets, or TablePlus `Settings.json` gains fields other than `closedWorkspaces`.
Use this zsh recipe from the repository root, changing `app` for each capture. Run
Bartender/Loopback/SoundSource on **both source Macs** and TablePlus on the Mac holding
the desired shared configuration:

```zsh
(
  set -eufo pipefail
  umask 077
  app=SoundSource
  pre=desktop.
  [[ $(hostname) != MacBook* ]] || pre=laptop.
  case "$app" in
    Bartender) domain=com.surteesstudios.Bartender; support=() ;;
    Loopback) domain=com.rogueamoeba.Loopback; support=(Devices.plist) ;;
    SoundSource) domain=com.rogueamoeba.soundsource; support=(Models.v2.plist Presets.v2.plist) ;;
    TablePlus) domain=com.tinyapp.TablePlus; pre=''; support=() ;;
    *) exit 1 ;;
  esac
  capture_tmp=$(mktemp -d /private/tmp/chezmoi-capture.XXXXXX)
  trap 'rm -rf "$capture_tmp"' EXIT
  defaults export "$domain" - | python3 home/.files/lib/filter_app_prefs.py "$app" > "$capture_tmp/$domain.plist"
  for name in "${support[@]}"; do
    cp "$HOME/Library/Application Support/$app/$name" "$capture_tmp/$name"
  done
  # For TablePlus this refreshes preferences only; connections use native export below.
  for input in "$capture_tmp"/*.plist; do
    plutil -lint "$input" >/dev/null
    chezmoi encrypt "$input" --output "$input.asc"
    chezmoi decrypt "$input.asc" > "$capture_tmp/verified"
    cmp -s "$input" "$capture_tmp/verified"
  done
  mkdir -p "home/.files/prefs/$app"
  for input in "$capture_tmp"/*.plist; do
    mv "$input.asc" "home/.files/prefs/$app/$pre${input:t}.asc"
  done
)
```

Review the encrypted-file diff, document the captured version/counts, and update the
template's minimum version when capturing from a newer app. Preserve
the no-history requirement: inspect SoundSource device-selection history before
refreshing; if nonempty, obtain a safe export procedure rather than archiving it or
editing proprietary model structures. Do not recapture old migrations or directories.
Passwords, tokens, licences, private keys, history and decrypted exports must not be
committed. Do not export the Keychain. Plaintext stays outside the Dropbox checkout.

### Native exports: OpenIn and populated TablePlus connections

OpenIn's [native backup workflow](https://loshadki.app/blog/2021-12-01-openin-v3/)
exists in the inspected v4 Settings → Backups UI. Capture remains pending because
its ordinary backup includes history. Obtain a verified history-free native export
without automatically clearing the source's history or altering its SQLite schema.
Save its encrypted form as `.files/prefs/OpenIn/settings.openin-backup.asc`.

For TablePlus, use its [documented connection export](https://docs.tableplus.com/gui-tools/manage-connections):
right-click a group → Export Connections → Export all…, disable **both database and
server password inclusion**, and export outside Dropbox. Encrypt the native file as
`.files/prefs/TablePlus/connections.tableplusconnection.asc`. Once present, the template
stops restoring the old empty connection/group plists; remove those obsolete encrypted
empty lists when committing the native export. Native exports preserve groups/images.

Use `chezmoi encrypt <private-export> --output <private-export>.asc`, verify a decrypt
round-trip in that private directory, then move **only the ciphertext** to the filename
above. Never save an unencrypted export inside the checkout. Keep any native export
password in your existing credential store.

To import, explicitly decrypt to a private temporary directory, for example:

```zsh
umask 077
import_tmp=$(mktemp -d /private/tmp/chezmoi-import.XXXXXX)
chezmoi decrypt home/.files/prefs/TablePlus/connections.tableplusconnection.asc \
  --output "$import_tmp/connections.tableplusconnection"
```

In TablePlus, right-click the welcome screen → Import Connections… → choose that file,
enter its export password if set, and Import. In OpenIn, first launch to initialise
its sandbox, then Settings → Backups → import the decrypted `.openin-backup`, select
it and Restore. The app handles its own database writers/caches. Delete the temporary
directory after successful import. No live group-container database is copied.

Relink browser profiles/apps and choose OpenIn's default browser/mail/file handlers
using [its normal setup](https://loshadki.app/openin4/); approve helper/automation
permissions yourself. Restore TablePlus database/SSH credentials from the existing
credential store and relink keys/certificates separately.

## Verification

`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` tests synthetic
files in isolated temporary destinations. Preference operations and process checks
are mocked; the tests cannot import preferences into the real macOS account. They
cover selection, shared files, missing-then-added captures, opt-in protection,
decryption/validation failures before any replacement, backups, repeats, symlinks,
preference rollback/merging and compatibility with the repaired helper's old calls.

No bootstrap, live apply/update, setting import, app restart, push or merge was used
for implementation. Fresh-Mac checks remain: Bartender 7 layouts, native imports,
permissions, audio-helper shutdown, device/application relinking and real effects.
