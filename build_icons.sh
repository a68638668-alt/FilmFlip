#!/bin/bash

set -e

ICON="assets/icon.png"
ICONSET="assets/icon.iconset"

echo "🧹 Cleaning..."
rm -rf "$ICONSET"
mkdir -p "$ICONSET"

echo "🎨 Creating iconset..."

magick "$ICON" -resize 16x16   "$ICONSET/icon_16x16.png"
magick "$ICON" -resize 32x32   "$ICONSET/icon_16x16@2x.png"

magick "$ICON" -resize 32x32   "$ICONSET/icon_32x32.png"
magick "$ICON" -resize 64x64   "$ICONSET/icon_32x32@2x.png"

magick "$ICON" -resize 128x128 "$ICONSET/icon_128x128.png"
magick "$ICON" -resize 256x256 "$ICONSET/icon_128x128@2x.png"

magick "$ICON" -resize 256x256 "$ICONSET/icon_256x256.png"
magick "$ICON" -resize 512x512 "$ICONSET/icon_256x256@2x.png"

magick "$ICON" -resize 512x512 "$ICONSET/icon_512x512.png"
cp "$ICON" "$ICONSET/icon_512x512@2x.png"

echo "🍎 Creating ICNS..."
iconutil -c icns "$ICONSET" -o assets/icon.icns

echo "🪟 Creating ICO..."
magick "$ICON" \
-define icon:auto-resize=16,24,32,48,64,128,256 \
assets/icon.ico

echo "✅ Done!"