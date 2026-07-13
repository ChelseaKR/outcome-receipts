#!/usr/bin/env bash
set -euo pipefail

# Install the two non-Python security scanners used by `make verify`. Downloads
# and cached executables are versioned and checksum-verified so local and CI runs
# execute the same bits. An executable bit or expected filename is never trusted evidence.
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tools_dir="$root/.tools"
if [[ -L "$tools_dir" ]]; then
  echo "security-tool directory must not be a symlink: $tools_dir" >&2
  exit 1
fi
if [[ -e "$tools_dir" && ! -d "$tools_dir" ]]; then
  echo "security-tool path is not a directory: $tools_dir" >&2
  exit 1
fi
mkdir -p "$tools_dir"

gitleaks_version=8.30.1
osv_version=2.4.0

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64)
    gitleaks_platform=darwin_arm64
    gitleaks_archive_sha=b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5
    gitleaks_binary_sha=ba52fb1bfabbcde42f032afad3d6e0b19dff8ed105229a16e7caa338bbc0e84f
    osv_platform=darwin_arm64
    osv_binary_sha=9ca3185ad63e9ab54f7cb90f46a7362be02d80e37f0123d095a54355ea202f5d
    ;;
  Linux-x86_64)
    gitleaks_platform=linux_x64
    gitleaks_archive_sha=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
    gitleaks_binary_sha=88f91962aa2f93ac6ab281d553b9e125f5197bbbce38f9f2437f7299c32e5509
    osv_platform=linux_amd64
    osv_binary_sha=15314940c10d26af9c6649f150b8a47c1262e8fc7e17b1d1029b0e479e8ed8a0
    ;;
  *)
    echo "unsupported security-tool platform: $(uname -s)-$(uname -m)" >&2
    exit 1
    ;;
esac

tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT

sha256_file() {
  shasum -a 256 "$1" | awk '{print $1}'
}

verify_hash() {
  local path=$1
  local expected=$2
  local label=$3
  local actual
  actual=$(sha256_file "$path")
  if [[ "$actual" != "$expected" ]]; then
    echo "$label checksum mismatch: expected $expected, got $actual" >&2
    return 1
  fi
}

cached_binary_valid() {
  local path=$1
  local expected=$2
  [[ -f "$path" && ! -L "$path" && -x "$path" ]] || return 1
  verify_hash "$path" "$expected" "cached $path"
}

prepare_target() {
  local path=$1
  if [[ -d "$path" && ! -L "$path" ]]; then
    echo "security-tool target is an unexpected directory: $path" >&2
    exit 1
  fi
  if [[ -e "$path" || -L "$path" ]]; then
    echo "replacing untrusted cached security tool: $path" >&2
    rm -f -- "$path"
  fi
}

download_https() {
  local url=$1
  local output=$2
  curl --fail --silent --show-error --location \
    --proto '=https' --proto-redir '=https' \
    --output "$output" "$url"
}

gitleaks="$tools_dir/gitleaks"
if ! cached_binary_valid "$gitleaks" "$gitleaks_binary_sha"; then
  prepare_target "$gitleaks"
  archive="$tmp_dir/gitleaks.tar.gz"
  extracted="$tmp_dir/gitleaks"
  download_https \
    "https://github.com/gitleaks/gitleaks/releases/download/v${gitleaks_version}/gitleaks_${gitleaks_version}_${gitleaks_platform}.tar.gz" \
    "$archive"
  verify_hash "$archive" "$gitleaks_archive_sha" "gitleaks archive"
  tar -xzf "$archive" -C "$tmp_dir" gitleaks
  verify_hash "$extracted" "$gitleaks_binary_sha" "gitleaks executable"
  install -m 0755 "$extracted" "$gitleaks"
fi

osv="$tools_dir/osv-scanner"
if ! cached_binary_valid "$osv" "$osv_binary_sha"; then
  prepare_target "$osv"
  downloaded_osv="$tmp_dir/osv-scanner"
  download_https \
    "https://github.com/google/osv-scanner/releases/download/v${osv_version}/osv-scanner_${osv_platform}" \
    "$downloaded_osv"
  verify_hash "$downloaded_osv" "$osv_binary_sha" "osv-scanner executable"
  install -m 0755 "$downloaded_osv" "$osv"
fi

# Recheck file type, mode, and bytes before executing either binary. Version output is
# an independent pin/packaging sanity check, not a substitute for the SHA-256 identity.
if ! cached_binary_valid "$gitleaks" "$gitleaks_binary_sha"; then
  echo "installed gitleaks is not a trusted regular executable" >&2
  exit 1
fi
if ! cached_binary_valid "$osv" "$osv_binary_sha"; then
  echo "installed osv-scanner is not a trusted regular executable" >&2
  exit 1
fi

actual_gitleaks_version=$("$gitleaks" version)
if [[ "$actual_gitleaks_version" != "$gitleaks_version" ]]; then
  echo "gitleaks version mismatch: expected $gitleaks_version, got $actual_gitleaks_version" >&2
  exit 1
fi

osv_version_output=$("$osv" --version)
actual_osv_version=${osv_version_output%%$'\n'*}
expected_osv_version="osv-scanner version: $osv_version"
if [[ "$actual_osv_version" != "$expected_osv_version" ]]; then
  echo "osv-scanner version mismatch: expected '$expected_osv_version', got '$actual_osv_version'" >&2
  exit 1
fi

echo "security tools verified: gitleaks $actual_gitleaks_version; $actual_osv_version"
