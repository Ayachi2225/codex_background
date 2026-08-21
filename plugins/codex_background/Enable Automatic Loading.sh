#!/usr/bin/env sh
set -eu

plugin_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 "$plugin_dir/scripts/codex_background.py" enable-autostart
echo "Automatic loading is enabled."
