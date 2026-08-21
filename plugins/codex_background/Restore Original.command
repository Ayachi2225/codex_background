#!/bin/zsh
set -u

plugin_dir="$(cd "$(dirname "$0")" && pwd)"
python_bin="$(command -v python3 || true)"

if [[ -z "$python_bin" ]]; then
  echo "未找到 python3，无法运行恢复助手。"
  read -r "?按回车键关闭…"
  exit 1
fi

"$python_bin" "$plugin_dir/scripts/codex_background.py" restore
echo "已安排恢复原始外观，ChatGPT/Codex 将正常重启。"
sleep 2
