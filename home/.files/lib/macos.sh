#!/usr/bin/env zsh
set -eufo pipefail
IFS=$'\n\t'

# Locate user-installed apps and macOS system utilities.
function app_path() {
  local app=$1 root
  for root in /Applications /System/Applications /System/Applications/Utilities; do
    if [[ -d "${root}/${app}.app" ]]; then
      print -r -- "${root}/${app}.app"
      return 0
    fi
  done
  return 1
}

function launched() {
  local app_name=$1
  local app_path
  app_path=$(app_path "${app_name}") || return 1
  # Check for a support directory
  local supp_dir="$HOME/Library/Application Support/${app_name}"
  [[ -d "${supp_dir}" ]] && return 0
  # Dynamically get the bundle identifier
  local app_bundle
  app_bundle=$(defaults read "$app_path/Contents/Info.plist" CFBundleIdentifier 2>/dev/null) || return 1
  # Check for a preference file
  local pref_file="$HOME/Library/Preferences/${app_bundle}.plist"
  [[ -n "${app_bundle}" && -f "${pref_file}" ]] && return 0
  # Check for a state file
  local state_file="$HOME/Library/Saved Application State/${app_bundle}.savedState"
  [[ -n "${app_bundle}" && -d "${state_file}" ]] && return 0
  # Check /private/var/folders for bundle directory
  local pvf_dir
  pvf_dir=$(find /private/var/folders -type d -name "${app_bundle}" -print -quit 2>/dev/null) || true
  [[ -n "${app_bundle}" && -d "${pvf_dir}" ]] && return 0
  # If all other checks fail, assume not launched
  return 1
}

function replace() {
  local src=$1 dst=$2 own grp pem
  [[ -f "${src}" && ! -L "${dst}" ]] || return 1
  if [[ -f "${dst}" ]] && cmp -s "${src}" "${dst}"; then
    return 1
  fi
  # An absent icon has no metadata to preserve. Use its source metadata.
  if [[ -e "${dst}" ]]; then
    [[ -f "${dst}" ]] || return 1
    own=$(sudo stat -f '%u' "${dst}") || return 1
    grp=$(sudo stat -f '%g' "${dst}") || return 1
    pem=$(sudo stat -f '%A' "${dst}") || return 1
    sudo cp -p "${dst}" "${dst}.chezmoi.$(date +%Y%m%d%H%M%S)" || return 1
  else
    own=$(stat -f '%u' "${src}") || return 1
    grp=$(stat -f '%g' "${src}") || return 1
    pem=$(stat -f '%A' "${src}") || return 1
  fi
  sudo mkdir -p "${dst:h}" || return 1
  sudo cp -f "${src}" "${dst}" || return 1
  sudo chown "${own}:${grp}" "${dst}" || return 1
  sudo chmod "${pem}" "${dst}" || return 1
  return 0
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

# Optional is only for intentional omissions; required failures must reach chezmoi.
function replace_lib() (
  local src=$1 dst=$2 app=$3 lib=$4 dec=${5:-false} requirement=${6:-required}
  local bundle tmp='' backup='' running
  if [[ "${requirement}" != required && "${requirement}" != optional ]]; then
    print -u2 -- "Invalid restoration requirement: ${requirement}"
    return 1
  fi
  if [[ ! -f "${src}" ]] || ! bundle=$(app_path "${app}"); then
    if [[ "${requirement}" == optional ]]; then
      print -u2 -- "Skipping optional ${lib}: source or application is absent"
      return 0
    fi
    print -u2 -- "Cannot restore ${lib}: required source (${src}) or application (${app}) is absent"
    return 1
  fi
  # Escape the bundle path for pgrep's regular expression; do not quit apps for the user.
  local pattern
  pattern=$(print -r -- "${bundle}/Contents/MacOS/" | sed 's/[][\\.^$*+?(){}|]/\\&/g') || return 1
  if pgrep -u "$(id -u)" -f "${pattern}" >/dev/null; then
    print -u2 -- "Quit ${app} before restoring ${lib}, then run chezmoi apply again."
    return 1
  else
    running=$?
    [[ ${running} -eq 1 ]] || return "${running}"
  fi
  if [[ -L "${dst}" || ( -e "${dst}" && ! -f "${dst}" ) ]]; then
    print -u2 -- "Refusing to replace non-regular destination: ${dst}"
    return 1
  fi

  umask 077
  mkdir -p "${dst:h}" || return 1
  tmp=$(mktemp "${dst:h}/.chezmoi-restore.XXXXXX") || return 1
  trap 'rm -f -- "${tmp}"' EXIT
  trap 'exit 1' HUP INT TERM
  if [[ "${dec}" == true ]]; then
    if ! chezmoi decrypt "${src}" > "${tmp}"; then
      print -u2 -- "Decryption failed for ${lib}; existing settings were left untouched"
      return 1
    fi
  elif [[ "${dec}" == false ]]; then
    cp "${src}" "${tmp}" || return 1
  else
    print -u2 -- "Invalid encryption flag for ${lib}: ${dec}"
    return 1
  fi
  [[ -s "${tmp}" ]] || { print -u2 -- "Empty replacement for ${lib}"; return 1; }
  if [[ "${dst}" == *.plist ]]; then
    # Suppress diagnostics that could include decrypted preference values.
    plutil -lint "${tmp}" >/dev/null 2>&1 || {
      print -u2 -- "Invalid preference plist for ${lib}; existing settings were left untouched"
      return 1
    }
  fi
  chmod 600 "${tmp}" || return 1
  if [[ -f "${dst}" ]]; then
    chown "$(stat -f '%u:%g' "${dst}")" "${tmp}" || return 1
    # Retain the existing backup convention, but only after preparation succeeds.
    backup=$(mktemp "${dst}.chezmoi.$(date +%Y%m%d%H%M%S).XXXXXX") || return 1
    cp -p "${dst}" "${backup}" || return 1
  fi
  echo "Updating ${lib}..."
  if [[ "${dst}" == "$HOME/Library/Preferences/"*.plist ]]; then
    # Go through cfprefsd instead of copying a plist behind its cache.
    if ! defaults import "${lib%.plist}" "${tmp}" >/dev/null 2>&1; then
      print -u2 -- "Preference import failed for ${lib}; retry after checking the app is closed"
      if [[ -n "${backup}" ]]; then
        defaults import "${lib%.plist}" "${backup}" >/dev/null 2>&1 || {
          print -u2 -- "Could not roll back ${lib}; original retained at ${backup}"
        }
      fi
      return 1
    fi
    chmod 600 "${dst}" || return 1
  else
    # Staging beside the destination makes replacement an atomic rename.
    mv -f "${tmp}" "${dst}" || return 1
  fi
)

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
