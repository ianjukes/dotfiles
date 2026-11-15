#!/bin/zsh
set -euo pipefail

# Install once per Mac. Unite Pro handles subsequent updates itself.
[[ "$(/usr/bin/uname -s)" == "Darwin" ]] || exit 0

applications="/Applications"
destination="$applications/Unite Pro.app"
bundle_id="com.BZG.unitepro"
# BZG's official latest-version link: https://www.bzgapps.com/unite-changelog
url="https://bzgdownloads.s3.amazonaws.com/Unite/Unite+Pro.zip"
requirement='=anchor apple generic and identifier "com.BZG.unitepro" and certificate leaf[subject.OU] = "J463UA2LCA"'

fail() {
  print -u2 -- "Unite Pro: $*"
  exit 1
}

# Also recognise a manually installed copy in the user's Applications folder.
for existing in "$destination" "$HOME/Applications/Unite Pro.app"; do
  if [[ -e "$existing" || -L "$existing" ]]; then
    if [[ -d "$existing" && "$(/usr/bin/plutil -extract CFBundleIdentifier raw \
        "$existing/Contents/Info.plist" 2>/dev/null)" == "$bundle_id" ]]; then
      print -- "Unite Pro is already installed; skipping."
      exit 0
    fi
    fail "An unexpected or incomplete item exists at $existing; leaving it untouched."
  fi
done

work=""
stage=""
typeset -a install_prefix=()
cleanup() {
  local exit_status=$?
  trap - EXIT
  if [[ -n "$stage" ]]; then
    "${install_prefix[@]}" /bin/rm -rf -- "$stage" || true
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

work=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/chezmoi-unite-pro.XXXXXX")
print -- "Downloading Unite Pro from BZG..."
/usr/bin/curl --fail --location --show-error --silent \
  --proto '=https' --proto-redir '=https' \
  --connect-timeout 30 --max-time 600 --retry 3 \
  --output "$work/unite.zip" "$url"
/usr/bin/ditto -xk "$work/unite.zip" "$work/unpacked"

# Refuse an empty or ambiguous archive; allow an enclosing release folder.
app=$(/usr/bin/find "$work/unpacked" -type d -name "Unite Pro.app" -prune -print)
[[ -n "$app" && -d "$app" ]] || fail "The archive must contain exactly one Unite Pro.app."
[[ "$(/usr/bin/plutil -extract CFBundleIdentifier raw "$app/Contents/Info.plist")" == "$bundle_id" ]] \
  || fail "The downloaded app has an unexpected bundle identifier."

print -- "Checking Unite Pro's signature and macOS Gatekeeper approval..."
/usr/bin/codesign --verify --deep --strict "$app"
# Check the top-level signing identity separately from nested components.
/usr/bin/codesign --verify --strict -R "$requirement" "$app"
/usr/sbin/spctl --assess --type execute --verbose=2 "$app"

# Stage on the destination volume so an interrupted copy cannot leave a
# partially installed app. Elevate only if /Applications requires it.
if [[ ! -w "$applications" ]]; then
  install_prefix=(/usr/bin/sudo)
fi
stage=$("${install_prefix[@]}" /usr/bin/mktemp -d "$applications/.chezmoi-unite-pro.XXXXXX")
"${install_prefix[@]}" /usr/bin/ditto "$app" "$stage/Unite Pro.app"

# -n refuses to overwrite an app installed while the download was running.
# Pass the parent directory so an existing app cannot become a nested target.
"${install_prefix[@]}" /bin/mv -n "$stage/Unite Pro.app" "$applications/"
if "${install_prefix[@]}" /bin/test -e "$stage/Unite Pro.app"; then
  fail "The destination appeared during installation; leaving it untouched."
fi

print -- "Unite Pro installed. Open it to activate your licence."
