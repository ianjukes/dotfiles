#  ⚙️ dotfiles

A repository of configuration files (dotfiles) created by [@ianjukes](https://github.com/ianjukes) for  personal use, and managed by [chezmoi](https://github.com/twpayne/chezmoi) for replication across multiple machines.

### macOS Prerequisites

1. Make sure your terminal application (Terminal, Ghostty, iTerm, etc.) has **App Management** and **Full Disk Access** in **Settings → Privacy & Security**.

2. Log into an Apple account for **Media & Puchases** so that applications can be installed from the **Mac App Store** automatically via [Homebrew](https://github.com/homebrew) (if applicable).

3. Perform any operating system updates via **General → Software Update**.

4. Sign into iCloud and let synchronisation complete.

5. Install Dropbox and let synchronisation complete.

6. Make sure the Mac’s hostname begins with `MacBook` for laptop settings. All other hostnames use desktop settings.

7. Quit any applications whose preferences are managed by chezmoi before running it.

### Install

To bootstrap a new machine use the following command:

    bash -c "$(curl -fsSL https://raw.githubusercontent.com/ianjukes/dotfiles/HEAD/bootstrap.sh)"

This will install any prerequisite tools (like Homebrew) and then initialize chezmoi.

### Update

A previously bootstrapped machine can be updated at anytime with:

    chezmoi update

This will pull the latest updates from this repository and apply them locally.

### Application snapshots

Bartender, Loopback and SoundSource have separate laptop/desktop restoration
snapshots; OpenIn and TablePlus use shared snapshots. Routine chezmoi runs provision
encrypted backups without overwriting these apps' live settings. Capture and restore
are explicit actions. See [capture, restore and first-launch instructions](docs/app-snapshots.md),
including pending desktop/OpenIn captures, manual native imports and audio-device checks.
