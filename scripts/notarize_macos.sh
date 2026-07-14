#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${APPLE_NOTARY_PROFILE:?Set APPLE_NOTARY_PROFILE to a notarytool keychain profile}"

APP="dist/FilmFlip.app"
UPLOAD_ZIP="dist/FilmFlip-v2.0-notary-upload.zip"
FINAL_ZIP="dist/FilmFlip-v2.0-macOS-universal-notarized.zip"

ditto -c -k --sequesterRsrc --keepParent "$APP" "$UPLOAD_ZIP"
xcrun notarytool submit "$UPLOAD_ZIP" --keychain-profile "$APPLE_NOTARY_PROFILE" --wait
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"
spctl --assess --type execute --verbose=4 "$APP"

rm -f "$FINAL_ZIP"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$FINAL_ZIP"
echo "Created $FINAL_ZIP"
