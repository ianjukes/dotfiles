#!/usr/bin/env zsh
set -eufo pipefail
IFS=$'\n\t'

function launched() {
  local app_name=$1
  local app_path="/Applications/${app_name}.app"
  # Does the application exist?
  [[ -d "${app_path}" ]] || return 1
  # Check for a support directory
  local supp_dir="$HOME/Library/Application Support/${app_name}"
  [[ -d "${supp_dir}" ]] && return 0
  # Dynamically get the bundle identifier
  local app_bundle
  app_bundle=$(defaults read "$app_path/Contents/Info.plist" CFBundleIdentifier 2>/dev/null)
  # Check for a preference file
  local pref_file="$HOME/Library/Preferences/${app_bundle}.plist"
  [[ -n "${app_bundle}" && -f "${pref_file}" ]] && return 0
  # Check for a state file
  local state_file="$HOME/Library/Saved Application State/${app_bundle}.savedState"
  [[ -n "${app_bundle}" && -f "${pref_file}" ]] && return 0
  # Check /private/var/folders for bundle directory
  local pvf_dir=$(find /private/var/folders -type d -name "${app_bundle}" -print -quit 2>/dev/null)
  [[ -n "${app_bundle}" && -d "${pvf_dir}" ]] && return 0
  # If all other checks fail, assume not launched
  return 1
}

function replace() {
  local src=$1 dst=$2
  # Does the destination file exist, and is it different?
  # If so create a backup and then replace it
  if [[ ! -f "${dst}" ]] || ! cmp -s "${src}" "${dst}"; then
    own=$(sudo stat -f '%Su' "${dst}")
    grp=$(sudo stat -f '%Sg' "${dst}")
    pem=$(sudo stat -f '%A' "${dst}")
    sudo mv -f "${dst}" "${dst}.chezmoi.$(date +%Y%m%d%H%M%S)"
    sudo cp -f "${src}" "${dst}"
    sudo chown "${own}:${grp}" "${dst}"
    sudo chmod "${pem}" "${dst}"
    return 0
  fi
  return 1
}

function replace_icons() {
  local src=$1 app=$2 ico=$3
  local -a icons=("${@:4}")
  local res=1
  if launched "${app}"; then
    IFS=':' read -r from to <<< "$ico"
    if replace "${src}/${from}" "${to}"; then
      reset_icons
      res=0
      echo "Updated application '${app}'";
    fi
    for icon in "${icons[@]}"; do
      IFS=':' read -r from to <<< "$icon"
      replace "${src}/${from}" "${to}" && res=0
    done
  else
    echo "Application '${app}' does not exist or has not been launched"
  fi
  return $res
}

function replace_lib() {
  local src=$1 dst=$2 app=$3 lib=$4 dec=${5:-false}
  if [[ -d "/Applications/${app}.app" && -f "${src}" ]]; then
    echo "Updating ${lib}..."
    [[ -f "${dst}" ]] && mv -f "${dst}" "${dst}.chezmoi.$(date +%Y%m%d%H%M%S)"
    [[ "${dec}" == true ]] && chezmoi decrypt "${src}" --output "${dst}" || cp -f "${src}" "${dst}"
    chmod 600 "${dst}"
  fi
}

function reset_icons() {
  echo "Resetting system icon caches..."
  sudo rm -rf /Library/Caches/com.apple.iconservices.store 2>/dev/null || true
  sudo find /private/var/folders/ -name com.apple.iconservices -exec rm -rf {} \; 2>/dev/null || true
  sudo find /private/var/folders/ -name com.apple.dock.iconcache -exec rm -rf {} \; 2>/dev/null || true
  echo "Waiting for Dock to restart..."
  killall Dock
  while ! pgrep Dock >/dev/null; do sleep 0.1; done
  echo "Waiting for Finder to restart..."
  killall Finder
  while ! pgrep Finder >/dev/null; do sleep 0.1; done
}
