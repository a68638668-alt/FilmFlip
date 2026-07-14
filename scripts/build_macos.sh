#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"

bash build_icons.sh
"$PYTHON_BIN" -m PyInstaller --clean --noconfirm FilmFlip.spec

rm -f dist/FilmFlip-v2.0-macOS-universal.zip
ditto -c -k --sequesterRsrc --keepParent \
  dist/FilmFlip.app dist/FilmFlip-v2.0-macOS-universal.zip

# BUNDLE가 완성된 뒤 남는 내부 COLLECT 폴더는 최종 배포물에 필요하지 않다.
rm -rf dist/FilmFlip

codesign --verify --deep --strict --verbose=2 dist/FilmFlip.app
echo "Created dist/FilmFlip.app"
echo "Created dist/FilmFlip-v2.0-macOS-universal.zip"
