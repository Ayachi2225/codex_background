#!/bin/zsh
set -u

plugin_dir="$(cd "$(dirname "$0")" && pwd)"
python_bin="$(command -v python3 || true)"

if [[ -z "$python_bin" ]]; then
  echo "未找到 python3，无法启动背景助手。"
  read -r "?按回车键关闭…"
  exit 1
fi

"$python_bin" "$plugin_dir/scripts/codex_background.py" doctor || {
  read -r "?检查失败。按回车键关闭…"
  exit 1
}

"$python_bin" "$plugin_dir/scripts/codex_background.py" start
echo "背景助手已排队启动，ChatGPT/Codex 将重启。"
sleep 2
