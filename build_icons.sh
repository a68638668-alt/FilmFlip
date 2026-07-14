#!/bin/bash

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

SOURCE="assets/app_icon.svg"
ICON="assets/icon.png"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"

echo "🧹 Cleaning..."
rm -rf assets/icon.iconset

echo "🎨 Rendering app icon..."

magick -background none "$SOURCE" -resize 1024x1024 -depth 8 "$ICON"

echo "🍎🪟 Creating ICNS and ICO..."
"$PYTHON_BIN" scripts/create_icons.py "$ICON" assets/icon.icns assets/icon.ico

echo "✅ Done!"
