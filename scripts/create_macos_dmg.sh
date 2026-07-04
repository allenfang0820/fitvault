#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: $0 /path/to/脉图.app /path/to/output.dmg [volume-name]" >&2
  exit 64
fi

APP_PATH="$1"
OUTPUT_DMG="$2"
VOLUME_NAME="${3:-脉图 FitVault}"

if [[ ! -d "$APP_PATH" ]]; then
  echo "App bundle not found: $APP_PATH" >&2
  exit 66
fi

APP_NAME="$(basename "$APP_PATH")"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/fitvault-dmg.XXXXXX")"
RW_DMG="$WORK_DIR/package-rw.dmg"

cleanup() {
  set +e
  if [[ -d "/Volumes/$VOLUME_NAME" ]]; then
    hdiutil detach "/Volumes/$VOLUME_NAME" -quiet
  fi
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

APP_SIZE_MB="$(du -sm "$APP_PATH" | awk '{print $1}')"
DMG_SIZE_MB="$((APP_SIZE_MB + 220))"
if [[ "$DMG_SIZE_MB" -lt 650 ]]; then
  DMG_SIZE_MB=650
fi

rm -f "$OUTPUT_DMG"

hdiutil create \
  -size "${DMG_SIZE_MB}m" \
  -fs HFS+ \
  -volname "$VOLUME_NAME" \
  -ov \
  "$RW_DMG" >/dev/null

hdiutil attach "$RW_DMG" -readwrite -noverify -noautoopen >/dev/null
VOLUME_PATH="/Volumes/$VOLUME_NAME"

cp -R "$APP_PATH" "$VOLUME_PATH/$APP_NAME"
ln -s /Applications "$VOLUME_PATH/Applications"

# Best-effort Finder layout. The DMG remains valid even if Finder is not available.
osascript >/dev/null 2>&1 <<OSA || true
tell application "Finder"
  tell disk "$VOLUME_NAME"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set the bounds of container window to {120, 120, 680, 430}
    set viewOptions to the icon view options of container window
    set arrangement of viewOptions to not arranged
    set icon size of viewOptions to 96
    set position of item "$APP_NAME" of container window to {155, 165}
    set position of item "Applications" of container window to {405, 165}
    close
    open
    update without registering applications
    delay 1
  end tell
end tell
OSA

sync
hdiutil detach "$VOLUME_PATH" -quiet

hdiutil convert "$RW_DMG" \
  -format UDZO \
  -imagekey zlib-level=9 \
  -o "$OUTPUT_DMG" >/dev/null

hdiutil verify "$OUTPUT_DMG" >/dev/null
echo "Created $OUTPUT_DMG"
