#  ⚙️ dotfiles

A repository of configuration files (dotfiles) created by [@ianjukes](https://github.com/ianjukes) for  personal use, and managed by [chezmoi](https://github.com/twpayne/chezmoi) for replication across multiple machines.

### macOS Prerequisites

1. Make sure the Mac’s hostname begins with `MacBook` for laptop settings. All other hostnames use desktop settings. A new MacBook is usually named something like `Ians-MacBook-Pro`, which does not qualify, so rename it first:

       sudo scutil --set LocalHostName MacBookPro

   The bootstrap script stops if a MacBook’s hostname does not begin with `MacBook`.

2. Use the same macOS account name as on the existing Macs (`id -un` shows it). The passwordless `sudo` rule only applies to that account name; with a different name, installers keep asking for the password.

3. Sign into iCloud.

4. Perform any operating system updates via **General → Software Update**.

5. Log into an Apple account for **Media & Puchases** so that applications can be installed from the **Mac App Store** automatically via [Homebrew](https://github.com/homebrew) (if applicable).

6. Launch Photos and Messages to initiate iCloud syncronisation.

7. Install Dropbox and let synchronisation complete. This could take 24 hours.

8. Make sure Terminal has **App Management** and **Full Disk Access** in **Settings → Privacy & Security**.

### Install

To bootstrap a new machine use the following command:

    bash -c "$(curl -fsSL https://raw.githubusercontent.com/ianjukes/dotfiles/HEAD/bootstrap.sh)"

This will install any prerequisite tools (like Homebrew), initialize chezmoi, and mark any saved application preferences for initial restoration.

Stay near the Mac while it runs. It asks for the macOS password and the GPG passphrase near the start, and for permission to let Terminal control System Events (used to set the wallpaper) at the end. Installing every application, including Xcode, can take a few hours.

If bootstrapping fails, it prints a command to resume from the failed stage after a fix has been applied. Earlier bootstrap stages are skipped, and chezmoi skips unchanged scripts that already succeeded.

### After bootstrapping

The bootstrap ends by listing the applications whose saved settings are still pending. To finish the setup:

1. Open a new terminal window so that the new shell configuration is loaded.

2. Sign in to 1Password and turn on its SSH agent.

3. Launch Bartender, Loopback and SoundSource once, complete their first-run setup, then quit them along with their menu bar helpers. Their settings are restored by running:

       chezmoi apply

4. Open Unite Pro to activate its licence, and HuionTablet to grant the permissions it requests.

HuionTablet stays listed as pending. Its saved settings are for version 15 and are not applied to later versions.

### Update

A previously bootstrapped machine can be updated at anytime with:

    chezmoi update

This will pull the latest updates from this repository and apply them locally.
