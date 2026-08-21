# codex_background

`codex_background` 是一个面向 macOS Codex 桌面应用的非官方本地插件。它通过运行时注入为 Codex 加载自定义背景图片，并让部分界面面板呈现半透明效果；不会修改 `/Applications/ChatGPT.app`、`app.asar`、应用资源或代码签名。

> [!IMPORTANT]
> 这不是 OpenAI 官方功能。插件只能让 Codex 的网页界面面板透出插件背景图，不能让整个原生窗口透出 macOS 桌面。

## 支持范围

- macOS
- Codex/ChatGPT 桌面应用安装在 `/Applications/ChatGPT.app`
- Python 3.9 或更高版本
- 无第三方 Python 依赖

Windows、Linux、Web 版 ChatGPT/Codex 当前不受支持。

## 仓库结构

```text
codex_background/
├── .agents/plugins/marketplace.json
└── plugins/codex_background/
    ├── .codex-plugin/plugin.json
    ├── assets/background.png
    ├── config.json
    ├── scripts/codex_background.py
    └── skills/codex-background/SKILL.md
```

仓库同时是一个 Codex Git marketplace，因此 clone 后可以直接安装。随附的 skill 会让 Codex 理解如何启用、关闭、检查和配置背景。

## 安装

### 从 GitHub marketplace 安装

```bash
codex plugin marketplace add Ayachi2225/codex_background --ref main
codex plugin add codex_background@codex_background
```

安装后建议新建一个 Codex 任务，让新插件和 skill 被完整加载。

### 从本地 clone 安装

```bash
git clone https://github.com/Ayachi2225/codex_background.git
cd codex_background
codex plugin marketplace add "$PWD"
codex plugin add codex_background@codex_background
```

## 设置自己的背景图片

支持 PNG、JPEG 和 WebP。推荐使用 16:9、1920×1080 或更高分辨率的图片。

```bash
python3 plugins/codex_background/scripts/codex_background.py \
  set-image /absolute/path/to/your-background.png
```

该命令会把图片复制到插件的 `assets/` 目录，并更新 `config.json`。如果使用 Git marketplace 的缓存副本，请在 Codex 中对已安装插件运行相同命令，或修改 clone 后重新安装。

## 使用方法

插件目录内提供四个可双击运行的 macOS 命令：

- `Enable Automatic Loading.command`：启用启动监视器。不会重启当前 Codex；以后普通打开 Codex 时会自动加载背景。
- `Disable Automatic Loading.command`：关闭启动监视器，不重启当前 Codex。
- `Start Background.command`：立即重启 Codex 并启用背景，会中断当前任务连接。
- `Restore Original.command`：关闭自动加载并以原始外观重启 Codex，会中断当前任务连接。

也可以在终端中运行：

```bash
PLUGIN_ROOT=/path/to/plugins/codex_background

python3 "$PLUGIN_ROOT/scripts/codex_background.py" doctor
python3 "$PLUGIN_ROOT/scripts/codex_background.py" status
python3 "$PLUGIN_ROOT/scripts/codex_background.py" enable-autostart
python3 "$PLUGIN_ROOT/scripts/codex_background.py" disable-autostart
python3 "$PLUGIN_ROOT/scripts/codex_background.py" start
python3 "$PLUGIN_ROOT/scripts/codex_background.py" restore
```

## 外观配置

编辑 `plugins/codex_background/config.json`：

| 字段 | 范围 | 作用 |
| --- | --- | --- |
| `image` | 插件内相对路径 | 背景图片文件 |
| `fit` | `cover` / `contain` / `fill` | 图片适配方式 |
| `position` | CSS background-position | 图片位置 |
| `backgroundOpacity` | 0–1 | 背景图片本身的不透明度 |
| `overlayOpacity` | 0–1 | 深色遮罩的不透明度；越大越暗 |
| `panelOpacity` | 0–1 | Codex 内部面板的不透明度；越小越容易看到背景 |
| `blurPixels` | 0–40 | 背景模糊半径 |
| `debugPort` | 1024–65535 | 本机 Chromium 调试端口 |

修改后先检查配置：

```bash
python3 plugins/codex_background/scripts/codex_background.py doctor
```

若背景已经启用，运行 `start` 会直接刷新样式；若背景尚未启用，`start` 会重启 Codex。

## 工作原理

1. 助手直接启动未修改的 Codex 可执行文件，并加入仅监听 `127.0.0.1` 的 Chromium DevTools 参数。
2. 助手通过 Chrome DevTools Protocol 的 `Runtime.evaluate` 将 CSS 和背景图注入 Codex renderer。
3. 背景图会在本机转换为 data URL，不会上传到远端。
4. `MutationObserver` 在界面更新时维持样式和背景层。
5. 可选的用户级 macOS LaunchAgent 会监视普通 Codex 启动，并在需要时短暂重开应用以加入调试参数。
6. 执行恢复命令或以普通方式启动应用即可回到原始界面；应用包始终未被修改。

## 注意事项与安全

- 启用背景时会开放 `127.0.0.1:<debugPort>`。它不监听局域网，但同一台 Mac 上的其他本地进程可能访问该端口。
- 自动加载首次接管普通 Codex 启动时，应用会短暂重开一次。
- `start` 和 `restore` 会中断当前桌面任务连接；先等待正在生成的回复结束。
- Codex 更新可能改变 CSS 类名或 renderer 结构，届时透明样式可能需要维护。
- 插件不提供原生窗口透明度；`panelOpacity` 只影响内部界面面板。
- 不要把私人照片、访问令牌、日志或 `.runtime/` 内容提交到公开仓库。
- 该插件使用未公开保证的运行时行为，未来版本的 Codex 可能阻止调试端口或样式注入。

## 隐私

- 插件不包含遥测代码。
- 插件不主动连接互联网。
- 背景图片只在本机读取并注入本地 renderer。
- `.gitignore` 默认排除运行时状态、日志、Python 缓存、环境变量文件和常见密钥文件。

## 排错

```bash
python3 plugins/codex_background/scripts/codex_background.py doctor
python3 plugins/codex_background/scripts/codex_background.py status
curl http://127.0.0.1:9229/json/version
```

`127.0.0.1:9229` 只有在背景模式已启用时才会响应。运行日志位于插件目录的 `.runtime/background.log`，该目录不会被 Git 跟踪。

## 卸载与恢复

先关闭启动监视器并恢复原始外观：

```bash
python3 plugins/codex_background/scripts/codex_background.py disable-autostart
python3 plugins/codex_background/scripts/codex_background.py restore
```

然后从 Codex 中移除插件和 marketplace：

```bash
codex plugin remove codex_background@codex_background
codex plugin marketplace remove codex_background
```

## License

[MIT](LICENSE)
