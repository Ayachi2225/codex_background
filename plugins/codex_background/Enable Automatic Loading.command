#!/bin/zsh
set -u

plugin_dir="$(cd "$(dirname "$0")" && pwd)"
python_bin="$(command -v python3 || true)"

if [[ -z "$python_bin" ]]; then
  echo "未找到 python3，无法设置自动加载。"
  read -r "?按回车键关闭…"
  exit 1
fi

"$python_bin" "$plugin_dir/scripts/codex_background.py" enable-autostart
echo "当前 Codex 不会重启；下次普通打开 Codex 时会自动加载背景。"
sleep 3
