#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# 0) Verify macOS
if [[ "$(uname)" != "Darwin" ]]; then
  echo "This script must be run on macOS. Exiting."
  exit 1
fi

# 1) Install Apple Developer Command Line Tools
if ! xcode-select -p &>/dev/null; then
  echo "Installing Xcode Command Line Tools..."
  echo "You may be asked to confirm installation via a dialog box"
  xcode-select --install
  # Wait until the tools are finished installing
  until xcode-select -p &>/dev/null; do
    sleep 5
  done
fi

# 2) Install Homebrew
if ! command -v brew &>/dev/null; then
  echo "Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
eval "$(/opt/homebrew/bin/brew shellenv)"

# 3) Install gnupg
if ! command -v gpg &>/dev/null; then
  echo "Installing gnupg via Homebrew..."
  brew install gnupg
fi

# 4) Install chezmoi
if ! command -v chezmoi &>/dev/null; then
  echo "Installing chezmoi via Homebrew..."
  brew install chezmoi
fi

# 5) Initialize chezmoi and apply your dotfiles
echo "Initializing configuration with chezmoi..."
echo "You may be prompted for a password"
chezmoi init ianjukes --apply
