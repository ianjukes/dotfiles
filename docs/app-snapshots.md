# Application restoration snapshots

These five apps are already installed by the existing manifest. This feature adds
explicit capture and restoration, not installation or continuous synchronisation.
“Shared” means both Macs start from the same repository snapshot; edits in an app
are not sent back to Git. VS Code continues to use VS Code Sync.

Routine chezmoi runs **only provision encrypted restore material** under
`~/.local/share/chezmoi/app-snapshots`. They never import these app settings.
The ordinary `run_after` script is intentionally not `run_once`: a missing snapshot
prints a capture instruction every time and remains eligible when added later.
There is no laptop/desktop fallback.

## Captured inventory and storage investigation

Inspected on the laptop on 2026-09-18. The implementation starts at repair commit
`4a7fb8a`; that local branch had no subsequent commits and no same-named remote
branch. All snapshots use the repository's existing symmetric GPG encryption.

| App / installed version | Repository snapshot | Actual captured configuration |
| --- | --- | --- |
| Bartender 7.0.1 (700008) | `home/.files/app-snapshots/Bartender/laptop.json.asc` | Allowlisted menu preferences, profiles/layouts, trigger rules, shortcuts, style and embedded image data from a `defaults export` of `com.surteesstudios.Bartender`. One profile and three trigger records were present. |
| OpenIn 4.4.4 (221436), App Store | **Pending**; shared | Nothing captured. The user chose to retain the no-history requirement. The live database has four handlers, twelve app entries, eight rules and 22 history entries. |
| Loopback 2.5.0 | `home/.files/app-snapshots/Loopback/laptop.json.asc` | `~/Library/Application Support/Loopback/Devices.plist` and allowlisted preferences. **Zero virtual devices**; this is an empty device list, not a backup of populated routing. |
| SoundSource 6.1.4 | `home/.files/app-snapshots/SoundSource/laptop.json.asc` | `Models.v2.plist`, `Presets.v2.plist`, and allowlisted appearance, routing-group, exclusion and shortcut preferences. 187 application models plus three system-device models; built-in EQ/overdrive settings are embedded. Zero saved presets. |
| TablePlus 26.10.20 (800) | `home/.files/app-snapshots/TablePlus/shared.json.asc` | Allowlisted general preferences and shortcuts, and the verified **empty** `Connections.plist` and `ConnectionGroups.plist` lists. No connection credentials or populated connections were captured. |

Desktop Bartender, Loopback and SoundSource snapshots are **absent on purpose**.
Capture them on the desktop itself using the commands below. Hostnames starting
with `MacBook` select `laptop`; every other hostname selects `desktop`. OpenIn and
TablePlus always select `shared`. Capture/restore use the actual hostname, without
a profile override; provisioning uses chezmoi's hostname with the same rule.

### What is deliberately excluded

* Bartender's group store is
  `~/Library/Group Containers/24J875RH8J.com.surteesstudios.Bartender/Library/Application Support/default.store`.
  A read-only SQLite online backup (including committed WAL transactions) verified
  zero `ZWIDGETSETTINGS` rows. Its empty widget store and transaction metadata are
  not restoration assets. Capturing stops if widget records later appear, rather
  than silently dropping them or copying unreviewed Top Shelf/other functionality.
  Menu profiles/rules are present in the exported preferences. The feature does
  not copy Apple MenuBar preferences, onboarding/migration flags, window maps,
  purchase records or permission databases. Bartender 7 has no verified complete
  portable export in the inspected build; this is a scoped preference snapshot.
* OpenIn's authoritative store is
  `~/Library/Group Containers/4QE86VV38D.app.loshadki.OpenIn/Library/Application Support/OpenIn/local.sqlite`.
  It has pending WAL data and includes history. Neither it nor the cached Chrome
  profile JSON is copied. The iCloud backup found during inspection was an older
  desktop backup, not a current laptop export, and is not used. No database schema
  is modified to manufacture a history-free export.
* SoundSource's current `.v2` files were updated together on the inspection date;
  `Models.plist` and `Presets.plist` stopped updating in July, and `Sources.plist`,
  `CustomPresets.plist` and `.migratedModelsV6` are older migration data. Only the
  `.v2` pair is captured. The inspected models use embedded built-in EQ/overdrive
  graphs, not external headphone-EQ files. The downloaded `hpeq_profiles` catalogue
  is excluded. Device-selection history was empty; capture rejects nonempty history.
* TablePlus stores data separately under
  `~/Library/Application Support/com.tinyapp.TablePlus/Data/`.
  `Settings.json` currently contains only `closedWorkspaces` (session history), so
  it is excluded. Capture stops if other fields appear, requiring a fresh review.
  Its nested `ViewSetting` preferences also mix configuration with recent queries,
  favorites, paths, security and AI settings: only the explicit general-setting
  allowlist is captured. Existing excluded fields are preserved during restore.
* Caches, logs, recents, container metadata, credentials, licenses, trial data,
  driver/extension settings and macOS permission databases are not captured.

Storage is version-gated (Bartender 7, OpenIn 4 App Store, Loopback 2, SoundSource 6,
TablePlus 26). Re-investigate after upgrades that change storage, particularly
before enabling populated Bartender widgets, third-party audio effects or external
EQ assets. Capturing a file is not proof that its device references are portable.

## Capture or refresh

Run from the repository root with Python 3.9+ and the already-configured chezmoi/GPG
installation. Python, chezmoi and GPG are required; no additional installer is added.
Capture is a deliberate action and atomically replaces that repository snapshot
only after encryption and a successful decryption round-trip. It does not apply
settings, start/stop apps or export the Keychain. Review the resulting Git diff.

```sh
python3 home/.files/lib/app_snapshots.py capture Bartender
python3 home/.files/lib/app_snapshots.py capture Loopback
python3 home/.files/lib/app_snapshots.py capture SoundSource
python3 home/.files/lib/app_snapshots.py capture TablePlus
```

Run the first three commands on **each** source Mac. Run the TablePlus command on
whichever Mac currently holds the intended shared configuration. Do not copy a
laptop file to a desktop filename. Quit the app yourself before capture when
practical: the collector reads the full input set twice and refuses changes during
capture, but cannot collect edits still held only in an app's memory.

All private payloads remain in memory or a private temporary directory under
`/private/tmp`, outside the Dropbox checkout. Temporary inspection files are removed
on exit. Repository files are armored ciphertext with mode 0600. Do not put a
decrypted export in the checkout even temporarily; `.gitignore` is not encryption.

### OpenIn: native backup, manual import

OpenIn provides a [native backup/export/import workflow](https://loshadki.app/blog/2021-12-01-openin-v3/),
retained in the inspected v4 Settings → Backups UI. Its native `.openin-backup`
format is used rather than writing into sandbox/group-container storage.

The present capture is pending because backups include history. Later, use a
source configuration with no history and create/export a backup from Settings →
Backups to a private folder outside Dropbox. Do not clear history automatically;
if preserving source history is necessary, obtain a configuration-only export
procedure from the vendor. Once you have verified the native export has no history:

```sh
python3 home/.files/lib/app_snapshots.py capture OpenIn \
  --export /private/tmp/private-export/settings.openin-backup --history-excluded
```

`--history-excluded` is your attestation about the vendor archive; the helper checks
its container signature but cannot verify the proprietary contents. Do not use it
with an ordinary history-containing backup. Delete the original private export
after encryption. Restore provisions the native file for **manual import** through
Settings → Backups → import backup, then select that backup and Restore. The native
app validates its contents and handles its database writers and WAL files.

First launch OpenIn on the target Mac to initialise its sandbox. Install/relink the
target browsers and their profiles; source browser bookmarks/paths are not portable.
Use [OpenIn's documented setup](https://loshadki.app/openin4/) to select default
browser, mail and file handlers and grant helper/automation permissions yourself.
Those macOS registrations and approvals are not part of the snapshot.

### TablePlus: populated connections use the native export

The simple capture command works for the verified empty connection/group lists.
If either list becomes populated, use TablePlus's
[documented connection export/import](https://docs.tableplus.com/gui-tools/manage-connections):
right-click a group on the welcome screen, choose **Export Connections → Export
all…**, exclude **both database passwords and server passwords**, and export outside
Dropbox. This native format carries connection groups and their images too.

```sh
python3 home/.files/lib/app_snapshots.py capture TablePlus \
  --export /private/tmp/private-export/connections.tableplusconnection --passwords-excluded
```

The flag attests that both password options were off. The archive is opaque to this
helper; TablePlus validates it on import. GPG additionally encrypts the native export
and preferences. Keep any native export password in your credential store and remove
the original export after capture. No populated raw connection plist is accepted.

After restoration, right-click the welcome screen → **Import Connections…**, choose
the provisioned `.tableplusconnection`, enter its export password if set, and Import.
Re-enter database/SSH passwords from your existing credential store and relink SSH
keys/certificates separately. The Keychain and private keys are never exported.

## Deliberate restoration

Run from the checkout on the target Mac, after installation. No command below is
run automatically by chezmoi:

```sh
python3 home/.files/lib/app_snapshots.py restore Bartender
python3 home/.files/lib/app_snapshots.py restore Loopback
python3 home/.files/lib/app_snapshots.py restore SoundSource
python3 home/.files/lib/app_snapshots.py restore TablePlus
python3 home/.files/lib/app_snapshots.py restore OpenIn
```

Missing snapshots print an actionable skip and change nothing. For file-based
restores, any existing preference/support configuration is protected. After first
launch, or to intentionally restore a snapshot again, append `--replace`:

```sh
python3 home/.files/lib/app_snapshots.py restore SoundSource --replace
```

The helper decrypts and validates the entire package before touching the app's
settings. It refuses mismatched app/profile versions, symlinks, populated raw
TablePlus connections, unexpected file names and invalid plists. All replacement
data and private backups are prepared before writes. Preferences are merged with
excluded existing keys and imported through `defaults` so **cfprefsd** sees the
change; raw plist replacement would race its cache. Multi-file restores attempt
rollback on failure and report the backup location if recovery needs attention.
Backups are under `~/.local/share/chezmoi/app-snapshot-backups/<App>-<unique>/`, with
directories 0700 and files 0600. Retain them until you verify the restored app.

This separate multi-file helper preserves the repaired `replace_lib` safety model
without changing its existing callers. `replace_lib` only handles one destination
at a time; it is not used to fake a database or multi-file transaction.

**Quit applications, not just windows.** The restore command checks all process
executable names, including Bartender/MenuBarAgent, Loopback/loopbackd, SoundSource
and TablePlus helpers. For audio apps it conservatively also refuses while ARK/ACE
is running, since a window being closed is not proof all writers stopped. Quit
other audio apps through their normal menus. If a background process persists,
retry after a normal logout/restart before opening audio apps, or get the vendor's
supported shutdown/restoration advice. Do not kill services, unload drivers or
disable extensions to bypass the guard. This limitation can prevent an unattended
audio restore. Nothing in this feature installs or manipulates those components.

Bartender should be launched once to initialise its own store and permissions,
then quit before `restore Bartender --replace`. The empty widget database is left
under the app's control. Approve Accessibility/Screen Recording as requested by
Bartender itself and check layouts on each actual display; OS-owned menu-item
positions and version-specific Bartender 7 migration are not guaranteed by a
preference snapshot. The [vendor's migration guidance](https://www.macbartender.com/Bartender6/support/)
also notes changes in item placement between OS/app versions.

**Audio device validation is mandatory before using restored routing.** SoundSource
stores native binary device references and application file references; these have
been inspected but are not automatically rewritten or asserted to match a different
Mac. After restoring, connect the intended hardware, keep playback/capture stopped,
and inspect each system device, application output, device group, effect and shortcut
in SoundSource. Reselect devices/apps that are missing or point elsewhere. In
Loopback inspect every source, channel map and monitor; reassign hardware and nested
virtual devices, then test with safe levels before use. The current Loopback snapshot
has no references to verify because it has no devices. Matching laptop/desktop
selection alone is insufficient. Install/approve Rogue Amoeba's required components
through the vendor's normal app setup, separately from configuration restoration.
Third-party effects and their licenses must also be installed separately.

OpenIn and native TablePlus connection exports are decrypted only on a deliberate
restore into `~/.local/share/chezmoi/app-snapshot-imports/<App>/`. They are not imported
automatically. Existing differing export files require `--replace`, which backs them
up first. Import in the app, verify results, then delete the decrypted import files
and any old export backups you no longer need. Routine provisioning contains only
ciphertext; it neither creates decrypted exports nor overwrites app preferences.

## Verification and remaining fresh-Mac checks

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Tests use synthetic files under `/private/tmp` and a file-only backend that rejects
the real home directory. Platform commands fail if accidentally invoked by fixture
tests. Coverage includes profile/shared selection, late-added missing snapshots,
invalid packages, decryption/encryption failures, protection of existing settings,
repeat restoration, backups, symlink rejection, rollback, helper process guards and
a read-only SQLite backup with committed data still in a live WAL.

No live `chezmoi apply`/`update`, bootstrap, app restart, setting import or driver
operation was used to build this feature. Fresh-Mac validation remains necessary:
Bartender 7's actual layout/rule rendering, sandbox initialisation and OpenIn's native
import without history, populated TablePlus group import, Rogue Amoeba background
process shutdown, native device/app relinking, and effects/shortcuts on real hardware.
The `.v2` SoundSource file pair is based on the installed build and observed update
times, not a vendor-promised portable interchange format. If a future build changes
this arrangement, stop and re-investigate rather than copying migration files.
