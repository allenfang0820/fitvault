#!/usr/bin/env bash
set -euo pipefail

# Download per-architecture Node.js runtimes used by the macOS DMG builds.
# PyInstaller reads these directories automatically from HikingTrackAnalyzer.spec:
#   runtimes/node-darwin-arm64
#   runtimes/node-darwin-x64

NODE_VERSION="${NODE_VERSION:-v24.18.0}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/runtimes"
TMP_DIR="$RUNTIME_DIR/.tmp"

download_runtime() {
  local arch="$1"
  local target="$RUNTIME_DIR/node-darwin-$arch"
  local tarball="node-$NODE_VERSION-darwin-$arch.tar.gz"
  local url="https://nodejs.org/dist/$NODE_VERSION/$tarball"

  mkdir -p "$TMP_DIR"
  echo "[node] downloading $url"
  curl -fL "$url" -o "$TMP_DIR/$tarball"

  rm -rf "$target" "$TMP_DIR/node-$NODE_VERSION-darwin-$arch"
  tar -xzf "$TMP_DIR/$tarball" -C "$TMP_DIR"
  mv "$TMP_DIR/node-$NODE_VERSION-darwin-$arch" "$target"

  "$target/bin/node" -v
  PATH="$target/bin:$PATH" "$target/bin/npm" -v
  file "$target/bin/node"
  echo "[node] ready: $target"
}

mkdir -p "$RUNTIME_DIR"
download_runtime "arm64"
download_runtime "x64"

echo ""
echo "Node runtimes are ready."
echo "Build arm64 on Apple Silicon with: pyinstaller HikingTrackAnalyzer.spec"
echo "Build x64 under Rosetta or an Intel runner with: arch -x86_64 pyinstaller HikingTrackAnalyzer.spec"
