#!/usr/bin/env bash
# Install one pinned command-line tool for the checks (linux x86_64 runners).
#
# Every tool has a fixed version and the sha256 of its release asset. The
# asset is downloaded, verified with `sha256sum -c`, and only then unpacked;
# any mismatch fails the step (fail-closed). Where a digest comes from:
#   gitleaks, vale, oasdiff, actionlint: the project's checksums file
#   lychee:                              the project's per-asset .sha256 file
#   typos, zizmor:                       no checksums file is published; the
#                                        digest is the one GitHub's release
#                                        attestation lists for the asset
#                                        (gh release verify-asset)
#   ShellCheck:                          GitHub's digest for the release asset
#                                        (the same pin as DeePloy's CI)
#
# Usage: install-tool.sh NAME [DEST_DIR]   (default DEST_DIR: /usr/local/bin)
set -euo pipefail

name="${1:?usage: install-tool.sh NAME [DEST_DIR]}"
dest="${2:-/usr/local/bin}"

case "$name" in
  gitleaks)
    ver=8.30.1
    url="https://github.com/gitleaks/gitleaks/releases/download/v${ver}/gitleaks_${ver}_linux_x64.tar.gz"
    sha256=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
    member=gitleaks ;;
  vale)
    ver=3.22.0
    url="https://github.com/errata-ai/vale/releases/download/v${ver}/vale_${ver}_Linux_64-bit.tar.gz"
    sha256=52f5cd0314a1b7384cac6aa102a68193977312f6ba9c9f3ae001b5deec8e3a10
    member=vale ;;
  lychee)
    ver=0.24.2
    url="https://github.com/lycheeverse/lychee/releases/download/lychee-v${ver}/lychee-x86_64-unknown-linux-gnu.tar.gz"
    sha256=1f4e0ef7f6554a6ed33dd7ac144fb2e1bbed98598e7af973042fc5cd43951c9a
    member=lychee-x86_64-unknown-linux-gnu/lychee ;;
  typos)
    ver=1.50.2
    url="https://github.com/crate-ci/typos/releases/download/v${ver}/typos-v${ver}-x86_64-unknown-linux-musl.tar.gz"
    sha256=abcb3e257c7c2abeff4d903f7fe68071357637605bdb283ce2251f44bc70dc09
    member=./typos ;;
  zizmor)
    ver=1.30.1
    url="https://github.com/zizmorcore/zizmor/releases/download/v${ver}/zizmor-x86_64-unknown-linux-gnu.tar.gz"
    sha256=e65324f4430c2717591937edcec90ccbefaf14c174f8ec9415e03ca875b46e1a
    member=zizmor ;;
  oasdiff)
    ver=1.32.1
    url="https://github.com/oasdiff/oasdiff/releases/download/v${ver}/oasdiff_${ver}_linux_amd64.tar.gz"
    sha256=7c8939fc49b75ee11fec66a5b83b37a2fca6aee109fed85013b1ba2ac2a1ee7f
    member=oasdiff ;;
  actionlint)
    ver=1.7.12
    url="https://github.com/rhysd/actionlint/releases/download/v${ver}/actionlint_${ver}_linux_amd64.tar.gz"
    sha256=8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8
    member=actionlint ;;
  shellcheck)
    ver=0.11.0
    url="https://github.com/koalaman/shellcheck/releases/download/v${ver}/shellcheck-v${ver}.linux.x86_64.tar.xz"
    sha256=8c3be12b05d5c177a04c29e3c78ce89ac86f1595681cab149b65b97c4e227198
    member="shellcheck-v${ver}/shellcheck" ;;
  *)
    echo "install-tool.sh: unknown tool '$name'" >&2
    exit 2 ;;
esac

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
asset="$work/$(basename "$url")"
curl -fsSL --retry 3 --proto '=https' -o "$asset" "$url"
echo "${sha256}  ${asset}" | sha256sum -c -
case "$asset" in
  *.tar.xz) tar -xJf "$asset" -C "$work" "$member" ;;
  *)        tar -xzf "$asset" -C "$work" "$member" ;;
esac
if [ -w "$dest" ]; then
  install -m 0755 "$work/$member" "$dest/$name"
else
  sudo install -m 0755 "$work/$member" "$dest/$name"
fi
echo "installed $name $ver ($sha256)"
