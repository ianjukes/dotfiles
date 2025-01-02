#  ⚙️ dotfiles

A repository of configuration files (dotfiles) created by [@ianjukes](https://github.com/ianjukes) for  personal use, and managed by [chezmoi](https://github.com/twpayne/chezmoi) for replication across multiple machines.

### macOS Prerequisites

1. Make sure your terminal application (Terminal, Ghostty, iTerm, etc.) has **App Management** and **Full Disk Access** in **Settings → Privacy & Security**.

2. Log into an Apple account for **Media & Puchases** so that applications can be installed from the **Mac App Store** automatically via [Homebrew](https://github.com/homebrew) (if applicable).

3. Perform any operating system updates via **General → Software Update**.

### Install

To bootstrap a new machine use the following command:

    bash -c "$(curl -fsSL https://raw.githubusercontent.com/ianjukes/dotfiles/HEAD/bootstrap.sh)"

This will install any prerequisite tools (like Homebrew) and then initialize chezmoi.

### Update

A previously bootstrapped machine can be updated at anytime with:

    chezmoi update

This will pull the latest updates from this repository and apply them locally.
