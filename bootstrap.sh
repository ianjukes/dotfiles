#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

start_step=1
if [[ $# -gt 0 ]]; then
  if [[ $# -ne 2 || "$1" != --resume ]]; then
    echo "Usage: bootstrap.sh [--resume tools|homebrew|gnupg|chezmoi|dotfiles]" >&2
    exit 2
  fi
  case "$2" in
    tools) start_step=1 ;;
    homebrew) start_step=2 ;;
    gnupg) start_step=3 ;;
    chezmoi) start_step=4 ;;
    dotfiles) start_step=5 ;;
    *) echo "Unknown bootstrap stage: $2" >&2; exit 2 ;;
  esac
fi

# 0) Verify macOS
if [[ "$(uname)" != "Darwin" ]]; then
  echo "This script must be run on macOS. Exiting."
  exit 1
fi

stage=tools
stage_description="installing Apple Developer Command Line Tools"

report_failure() {
  local exit_code=$?
  if [[ "$exit_code" -eq 0 ]]; then
    return
  fi
  trap - EXIT
  printf '\nBootstrapping stopped while %s (exit %s).\n' "$stage_description" "$exit_code" >&2
  printf 'After applying a fix, resume from this stage with:\n\n' >&2
  printf '  bash -c "$(curl -fsSL https://raw.githubusercontent.com/ianjukes/dotfiles/HEAD/bootstrap.sh)" -- --resume %s\n\n' "$stage" >&2
  exit "$exit_code"
}

trap report_failure EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# 1) Install Apple Developer Command Line Tools
if [[ "$start_step" -le 1 ]]; then
  if ! xcode-select -p &>/dev/null; then
    echo "Installing Xcode Command Line Tools..."
    echo "You may be asked to confirm installation via a dialog box"
    xcode-select --install
    # Wait until the tools are finished installing
    until xcode-select -p &>/dev/null; do
      sleep 5
    done
  fi
fi

# 2) Install Homebrew
stage=homebrew
stage_description="installing Homebrew"
if [[ "$start_step" -le 2 ]]; then
  if [[ ! -x /opt/homebrew/bin/brew ]] && ! command -v brew &>/dev/null; then
    echo "Installing Homebrew..."
    homebrew_installer=$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)
    /bin/bash -c "$homebrew_installer"
  fi
fi

# Every resumed stage needs Homebrew available in the current shell.
stage_description="loading the Homebrew environment"
homebrew_environment=$(/opt/homebrew/bin/brew shellenv)
eval "$homebrew_environment"

# 3) Install gnupg
if [[ "$start_step" -le 3 ]]; then
  stage=gnupg
  stage_description="installing gnupg"
  if ! command -v gpg &>/dev/null; then
    echo "Installing gnupg via Homebrew..."
    brew install gnupg
  fi
fi

# 4) Install chezmoi
if [[ "$start_step" -le 4 ]]; then
  stage=chezmoi
  stage_description="installing chezmoi"
  if ! command -v chezmoi &>/dev/null; then
    echo "Installing chezmoi via Homebrew..."
    brew install chezmoi
  fi
fi

# 5) Initialize chezmoi and enrol saved app preferences for this new Mac
stage=dotfiles
stage_description="applying dotfiles and installing applications"
echo "Initializing configuration with chezmoi..."
echo "You may be prompted for a password"
DOTFILES_INITIAL_SETUP=1 chezmoi init ianjukes --apply

echo "Bootstrapping completed."
