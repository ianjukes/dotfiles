#!/bin/zsh
# Convert every PNG in the current directory into a matching .icns file.

set -u
setopt NULL_GLOB NO_CASE_GLOB PIPE_FAIL

[[ -x /usr/bin/sips ]] || { echo "Missing required tool: /usr/bin/sips"; exit 1; }
[[ -x /usr/bin/iconutil ]] || { echo "Missing required tool: /usr/bin/iconutil"; exit 1; }

ICON_FILES=(
  "icon_16x16.png"
  "icon_16x16@2x.png"
  "icon_32x32.png"
  "icon_32x32@2x.png"
  "icon_128x128.png"
  "icon_128x128@2x.png"
  "icon_256x256.png"
  "icon_256x256@2x.png"
  "icon_512x512.png"
  "icon_512x512@2x.png"
)

ICON_SIZES=(16 32 32 64 128 256 256 512 512 1024)

png_files=( *.png )
if (( ${#png_files} == 0 )); then
  echo "No .png files found in $(pwd)"
  exit 0
fi

failed=0

for src_image in "${png_files[@]}"; do
  base_name="${src_image:r}"   # filename without extension
  iconset_path="./${base_name}.iconset"
  icns_file="./${base_name}.icns"

  echo "Processing: $src_image"

  /bin/rm -rf -- "$iconset_path"
  /bin/mkdir -p -- "$iconset_path" || { echo "Failed to create $iconset_path"; failed=1; continue; }

  for ((i=1; i<=${#ICON_FILES}; i++)); do
    out_icon="${iconset_path}/${ICON_FILES[i]}"
    size="${ICON_SIZES[i]}"

    # Direct resize from source into destination (faster than cp + resize)
    /usr/bin/sips -z "$size" "$size" "$src_image" --out "$out_icon" >/dev/null || {
      echo "Failed to create $out_icon"
      failed=1
      continue 2
    }
  done

  # Write/overwrite output .icns explicitly
  if /usr/bin/iconutil -c icns "$iconset_path" -o "$icns_file"; then
    echo "Created: ${base_name}.icns"
  else
    echo "Failed to create: ${base_name}.icns"
    failed=1
  fi

  /bin/rm -rf -- "$iconset_path"
done

exit $failed
