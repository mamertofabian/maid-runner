#!/bin/sh
set -eu

usage() {
    printf 'Usage: install.sh [--version VERSION]\n' >&2
}

version=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --version)
            if [ "$#" -lt 2 ]; then
                usage
                exit 2
            fi
            version=$2
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            usage
            exit 2
            ;;
    esac
done

if [ -n "$version" ]; then
    case "$version" in
        [0-9A-Za-z]*) ;;
        *)
            usage
            exit 2
            ;;
    esac
    case "$version" in
        *[!0-9A-Za-z.!+_-]*)
            usage
            exit 2
            ;;
    esac
fi

case "$(uname -s)" in
    Darwin|Linux) ;;
    *)
        printf 'MAID Runner supports this installer on macOS and Linux.\n' >&2
        exit 1
        ;;
esac

if ! command -v uv >/dev/null 2>&1; then
    if ! command -v curl >/dev/null 2>&1; then
        printf 'curl is required to install uv.\n' >&2
        exit 1
    fi

    printf 'Installing uv...\n'
    uv_installer=$(curl -LsSf https://astral.sh/uv/install.sh)
    printf '%s\n' "$uv_installer" | sh

    for candidate in "${UV_INSTALL_DIR:-}" "$HOME/.local/bin" "$HOME/.cargo/bin"; do
        if [ -n "$candidate" ]; then
            PATH="$candidate:$PATH"
        fi
    done
    export PATH
fi

if ! command -v uv >/dev/null 2>&1; then
    printf 'uv was installed but could not be found on PATH.\n' >&2
    exit 1
fi

package_requirement="maid-runner"
if [ -n "$version" ]; then
    package_requirement="maid-runner==$version"
fi

printf 'Installing %s...\n' "$package_requirement"
uv tool install --python 3.12 "$package_requirement"
uv tool update-shell

tool_bin=$(uv tool dir --bin)
if [ -z "$tool_bin" ]; then
    printf 'uv did not report its tool executable directory.\n' >&2
    exit 1
fi
PATH="$tool_bin:$PATH"
export PATH

if ! command -v maid >/dev/null 2>&1; then
    printf 'MAID Runner was installed but maid could not be found on PATH.\n' >&2
    exit 1
fi

maid --version
printf 'MAID Runner is ready. Run: maid init\n'
