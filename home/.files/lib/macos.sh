#!/usr/bin/env zsh
set -eufo pipefail
IFS=$'\n\t'

function app_path() {
  local app=$1 root
  # Locate the application
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
  # Preserve destination metadata, or use source metadata for a new file
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

function app_preference_state() (
  # Read or record restoration state without resetting completed apps
  (( $# >= 1 && $# <= 2 )) || return 1
  local app=$1 next=${2:-} current="unmanaged" item tmp=""

  # Validate the app name and requested state
  [[ -n "${app}" && "${app}" != */* && "${app}" != . && "${app}" != .. ]] || return 1
  [[ -z "${next}" || "${next}" == pending || "${next}" == complete ]] || return 1

  # Check the state directory and file
  local directory="${XDG_STATE_HOME:-$HOME/.local/state}/chezmoi/app-preferences"
  local record="${directory}/${app}"
  [[ "${directory}" == /* ]] || {
    print -u2 -- "Application preference state must use an absolute path"
    return 1
  }
  item="${directory}"
  while [[ "${item}" != / && "${item}" != . ]]; do
    [[ ! -L "${item}" && ( ! -e "${item}" || -d "${item}" ) ]] || {
      print -u2 -- "Unsafe application preference state directory"
      return 1
    }
    item=${item:h}
  done
  [[ ! -L "${record}" && ( ! -e "${record}" || -f "${record}" ) ]] || {
    print -u2 -- "Unsafe application preference state for ${app}"
    return 1
  }

  # Read the current state
  if [[ -f "${record}" ]]; then
    current=$(cat "${record}") || return 1
    [[ "${current}" == pending || "${current}" == complete ]] || {
      print -u2 -- "Invalid application preference state for ${app}; settings untouched"
      return 1
    }
  fi

  # Create a pending record, or record successful restoration
  if [[ -n "${next}" && "${next}" != "${current}" &&
        ( "${next}" == complete || "${current}" == unmanaged ) ]]; then
    umask 077
    mkdir -p "${directory}" || return 1
    chmod 700 "${directory}" || return 1
    tmp=$(mktemp "${directory}/.state.XXXXXX") || return 1
    trap 'rm -f -- "${tmp}"' EXIT
    trap 'exit 1' HUP INT TERM

    print -r -- "${next}" > "${tmp}" || return 1
    chmod 600 "${tmp}" || return 1
    if [[ "${next}" == pending ]]; then
      # Do not overwrite a completion record created by another invocation
      ln "${tmp}" "${record}" || return 1
    else
      mv -f "${tmp}" "${record}" || return 1
    fi
    current="${next}"
  fi
  print -r -- "${current}"
)

function replace_lib() (
  # Arguments: app, minimum version ("-" if unrecorded), process pattern,
  # first-launch path (empty if unnecessary), then source/destination pairs
  (( $# >= 6 && ($# - 4) % 2 == 0 )) || {
    print -u2 -- "Expected app, minimum version, process pattern, first-launch path and source/destination pairs"
    return 1
  }
  local app=$1 minimum=$2 pattern=$3 ready=$4
  shift 4

  # Validate the app and prerequisites
  [[ -n "${app}" && "${app}" != */* && "${app}" != . && "${app}" != .. ]] || {
    print -u2 -- "Invalid application"
    return 1
  }
  [[ "${minimum}" == - || "${minimum}" =~ '^[0-9]+([.][0-9]+)*$' ]] || {
    print -u2 -- "Invalid minimum application version"
    return 1
  }
  [[ -z "${ready}" || "${ready}" == /* ]] || {
    print -u2 -- "Expected an absolute first-launch path"
    return 1
  }
  local pattern_status=0
  /usr/bin/grep -Eq -e "${pattern}" /dev/null 2>/dev/null || pattern_status=$?
  (( pattern_status <= 1 )) || {
    print -u2 -- "Invalid application process pattern"
    return 1
  }

  # Collect the source and destination pairs
  local -a sources destinations staged
  while (( $# )); do
    [[ "$1" == /* && "$2" == /* && "$1" != "$2" ]] || {
      print -u2 -- "Expected distinct absolute source and destination paths"
      return 1
    }
    [[ ${destinations[(Ie)$2]} -eq 0 ]] || {
      print -u2 -- "Duplicate restoration destination"
      return 1
    }
    sources+=("$1")
    destinations+=("$2")
    shift 2
  done

  local src dst item bundle version processes executable index backup
  local staging="" tmp="" restore_state prerequisite_status=0

  # Enrol apps before bootstrap starts installation
  if [[ "${DOTFILES_PREFS_ENROL_ONLY:-}" == 1 ]]; then
    [[ "${DOTFILES_INITIAL_SETUP:-}" == 1 ]] || return 1
    app_preference_state "${app}" pending >/dev/null
    return $?
  fi

  # Restore pending apps, or the app explicitly requested
  restore_state=$(app_preference_state "${app}") || return 1
  if [[ -n "${DOTFILES_RESTORE_APP:-}" ]]; then
    [[ "${DOTFILES_RESTORE_APP}" == "${app}" ]] || return 0
    prerequisite_status=1
  elif [[ "${restore_state}" != pending ]]; then
    # Leave existing Macs without a record untouched
    return 0
  fi

  # Check that every snapshot is available
  for src in "${sources[@]}"; do
    if [[ ! -e "${src}" && ! -L "${src}" ]]; then
      print -u2 -- "Skipping ${app}: missing ${src}. Capture the appropriate snapshot; existing settings untouched."
      return 0
    fi
  done

  # Check the installed application and version
  bundle=$(app_path "${app}") || {
    print -u2 -- "${app}: restoration pending; install the app, then run chezmoi apply again."
    return "${prerequisite_status}"
  }
  if [[ "${minimum}" != - ]]; then
    version=$(defaults read "${bundle}/Contents/Info.plist" CFBundleShortVersionString) || return 1
    [[ "${version%%.*}" == "${minimum%%.*}" ]] || {
      print -u2 -- "${app}: restoration pending; storage needs review for this version."
      return "${prerequisite_status}"
    }
    autoload -Uz is-at-least
    is-at-least "${minimum}" "${version}" || {
      print -u2 -- "${app}: restoration pending; install ${minimum} or newer within the reviewed major version."
      return "${prerequisite_status}"
    }
  fi

  # Check for running writers without reading private command arguments
  processes=$(ps -axo comm=) || return 1
  for executable in "${(@f)processes}"; do
    if [[ "${executable}" == "${bundle}/"* ]] ||
       [[ -n "${pattern}" && "${(L)executable}" =~ ${pattern} ]]; then
      print -u2 -- "${app}: restoration pending; quit the app and its background helpers, then run chezmoi apply again. Nothing was terminated."
      return "${prerequisite_status}"
    fi
  done

  # Validate every path before preparing replacements
  for item in "${sources[@]}" "${destinations[@]}"; do
    [[ ! -e "${item}" || -f "${item}" ]] || {
      print -u2 -- "Non-regular library file"
      return 1
    }
    while [[ "${item}" != / && "${item}" != . ]]; do
      [[ ! -L "${item}" ]] || {
        print -u2 -- "Symlink in library path"
        return 1
      }
      item=${item:h}
    done
  done

  # Check the first-launch indicator
  if [[ -n "${ready}" && ! -e "${ready}" ]]; then
    print -u2 -- "${app}: restoration pending; launch it once, complete its setup, then quit it and run chezmoi apply again. See docs/app-preferences.md."
    return "${prerequisite_status}"
  fi

  # Prepare a private temporary directory
  umask 077
  staging=$(mktemp -d /private/tmp/chezmoi-prefs.XXXXXX) || return 1
  trap 'rm -f -- "${tmp}"; rm -rf -- "${staging}"' EXIT
  trap 'exit 1' HUP INT TERM

  # Prepare and validate all files before replacing any destination
  for (( index=1; index <= ${#sources}; index++ )); do
    src="${sources[index]}"
    dst="${staging}/${index}"
    if [[ "${src}" == *.asc ]]; then
      if ! chezmoi decrypt "${src}" > "${dst}" 2>/dev/null; then
        print -u2 -- "Decryption failed for ${app}; existing settings untouched"
        return 1
      fi
    else
      cp "${src}" "${dst}" || return 1
    fi
    [[ -s "${dst}" ]] || {
      print -u2 -- "Empty replacement for ${app}"
      return 1
    }
    if [[ "${destinations[index]}" == *.plist ]]; then
      plutil -lint "${dst}" >/dev/null 2>&1 || {
        print -u2 -- "Invalid ${app} plist; existing settings untouched"
        return 1
      }
    fi
    staged+=("${dst}")
  done

  # Back up and replace files that differ
  for (( index=1; index <= ${#sources}; index++ )); do
    src="${staged[index]}"
    dst="${destinations[index]}"
    if [[ -f "${dst}" ]] && cmp -s "${src}" "${dst}"; then
      continue
    fi

    mkdir -p "${dst:h}" || return 1
    tmp=$(mktemp "${dst:h}/.chezmoi-restore.XXXXXX") || return 1
    cp "${src}" "${tmp}" || return 1
    chmod 600 "${tmp}" || return 1
    backup=""
    if [[ -f "${dst}" ]]; then
      chown "$(stat -f '%u:%g' "${dst}")" "${tmp}" || return 1
      backup=$(mktemp "${dst}.chezmoi.$(date +%Y%m%d%H%M%S).XXXXXX") || return 1
      cp -p "${dst}" "${backup}" || return 1
      chmod 600 "${backup}" || return 1
    fi

    print -- "Updating ${dst:t}..."
    if [[ "${dst}" == "$HOME/Library/Preferences/"*.plist ]]; then
      # Import preferences through cfprefsd
      if ! defaults import "${${dst:t}%.plist}" "${tmp}" >/dev/null 2>&1; then
        print -u2 -- "Preference import failed for ${app}; retry after checking the app is closed"
        if [[ -n "${backup}" ]]; then
          defaults import "${${dst:t}%.plist}" "${backup}" >/dev/null 2>&1 || {
            print -u2 -- "Could not roll back preferences; original retained at ${backup}"
          }
        fi
        return 1
      fi
      chmod 600 "${dst}" || return 1
    else
      # Replace other files with an atomic rename
      mv -f "${tmp}" "${dst}" || return 1
    fi
    rm -f -- "${tmp}" || return 1
    tmp=""
  done

  # Record completion only after every file has succeeded
  app_preference_state "${app}" complete >/dev/null || return 1
  print -- "Restored ${app}. Check its settings and any device references before use; see docs/app-preferences.md."
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
