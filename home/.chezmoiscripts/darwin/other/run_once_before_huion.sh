#!/bin/zsh
set -euo pipefail

# Install once per Mac, before the application-preference restoration scripts.
# Subsequent driver updates are managed through HuionTablet.
[[ "$(/usr/bin/uname -s)" == "Darwin" ]] || exit 0

applications="/Applications"
destination="$applications/HuionTablet.app"
bundle_id="com.huion.HuionTablet"
# Data endpoint used by Huion's Kamvas 16 (Gen 3), GS1563 download page.
# https://www.huion.com/download/kamvas-16-gen-3
metadata_url="https://www.huion.com/api/driver/driver_temp/126"
requirement='=anchor apple generic and identifier "com.huion.HuionTablet" and certificate leaf[subject.OU] = "5L9RVY3BW9"'

fail() {
  print -u2 -- "HuionTablet: $*"
  exit 1
}

# Recognise a manual installation without replacing or upgrading it.
for existing in "$destination" "$HOME/Applications/HuionTablet.app"; do
  if [[ -e "$existing" || -L "$existing" ]]; then
    if [[ -d "$existing" && "$(/usr/bin/plutil -extract CFBundleIdentifier raw \
        "$existing/Contents/Info.plist" 2>/dev/null)" == "$bundle_id" ]]; then
      print -- "HuionTablet is already installed; skipping."
      exit 0
    fi
    fail "An unexpected or incomplete item exists at $existing; leaving it untouched."
  fi
done

work=""
stage=""
mountpoint=""
mount_attempted=0
typeset -a install_prefix=()
cleanup() {
  local exit_status=$?
  trap - EXIT
  if [[ -n "$stage" ]]; then
    "${install_prefix[@]}" /bin/rm -rf -- "$stage" || true
  fi
  if (( mount_attempted )); then
    if ! /usr/bin/hdiutil detach "$mountpoint" -quiet; then
      # Never recursively remove a directory containing a mounted image.
      print -u2 -- "HuionTablet: could not detach $mountpoint; temporary files retained at $work."
      (( exit_status != 0 )) || exit_status=1
      exit "$exit_status"
    fi
  fi
  if [[ -n "$work" ]]; then
    /bin/rm -rf -- "$work" || true
  fi
  exit "$exit_status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

work=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/chezmoi-huion.XXXXXX")
mountpoint="$work/mount"
/bin/mkdir "$mountpoint"
print -- "Looking up the latest Mac driver for Kamvas 16 (Gen 3)..."
/usr/bin/curl --fail --location --show-error --silent \
  --proto '=https' --proto-redir '=https' \
  --connect-timeout 30 --max-time 60 --retry 3 \
  --output "$work/driver.json" "$metadata_url"
model=$(/usr/bin/plutil -extract down_model raw -expect string "$work/driver.json" 2>/dev/null) \
  || fail "Huion's download information is missing the model; its website may have changed."
[[ "$model" == "GS1563" ]] || fail "Huion's download information is for an unexpected model."
# Huion's page uses the first Mac entry as its current download.
/usr/bin/plutil -extract mac raw -expect array "$work/driver.json" >/dev/null 2>&1 \
  || fail "Huion's download information has no Mac driver list; its website may have changed."
url=$(/usr/bin/plutil -extract mac.0.fileurl raw -expect string "$work/driver.json" 2>/dev/null) \
  || fail "Huion's download information is missing the Mac driver; its website may have changed."
[[ "$url" =~ '^https://driverdl[.]huion[.]com/driver/Mac/HuionTablet_MacDriver_([0-9]+([.][0-9]+)*)[.]dmg$' ]] \
  || fail "Huion returned an unexpected download URL; review its website before installing."
version="${match[1]}"

print -- "Downloading HuionTablet $version from Huion..."
/usr/bin/curl --fail --location --show-error --silent \
  --proto '=https' --proto-redir '=https' \
  --connect-timeout 30 --max-time 600 --retry 3 \
  --output "$work/huion.dmg" "$url"

# Use a private, read-only mount; do not open Finder or launch the driver.
mount_attempted=1
/usr/bin/hdiutil attach -readonly -nobrowse -noautoopen \
  -mountpoint "$mountpoint" "$work/huion.dmg" -quiet
app="$mountpoint/HuionTablet.app"
[[ -d "$app" && ! -L "$app" ]] || fail "The disk image does not contain HuionTablet.app."
[[ "$(/usr/bin/plutil -extract CFBundleIdentifier raw "$app/Contents/Info.plist")" == "$bundle_id" ]] \
  || fail "The downloaded app has an unexpected bundle identifier."
[[ "$(/usr/bin/plutil -extract CFBundleShortVersionString raw "$app/Contents/Info.plist")" == "$version" ]] \
  || fail "The downloaded app has an unexpected version."

print -- "Checking HuionTablet's signature and macOS Gatekeeper approval..."
/usr/bin/codesign --verify --deep --strict "$app"
# The leading '=' tells codesign this is a literal requirement, not a filename.
/usr/bin/codesign --verify --strict -R "$requirement" "$app"
/usr/sbin/spctl --assess --type execute --verbose=2 "$app"

# Stage on the destination volume so a failed copy cannot leave a partial app.
if [[ ! -w "$applications" ]]; then
  install_prefix=(/usr/bin/sudo)
fi
stage=$("${install_prefix[@]}" /usr/bin/mktemp -d "$applications/.chezmoi-huion.XXXXXX")
"${install_prefix[@]}" /usr/bin/ditto "$app" "$stage/HuionTablet.app"

# Refuse to overwrite an installation that appeared during the download.
"${install_prefix[@]}" /bin/mv -n "$stage/HuionTablet.app" "$applications/"
if "${install_prefix[@]}" /bin/test -e "$stage/HuionTablet.app"; then
  fail "The destination appeared during installation; leaving it untouched."
fi

print -- "HuionTablet installed. Open it and grant the macOS permissions it requests."
