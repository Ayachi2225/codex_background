# codex_background

`codex_background` 是一个面向 Codex 桌面应用的非官方本地插件。它通过运行时注入加载自定义背景图片，并让部分界面面板呈现半透明效果；不会修改应用包、`app.asar`、应用资源或代码签名。

> [!IMPORTANT]
> 这不是 OpenAI 官方功能。插件只能让 Codex 网页界面的内部面板透出插件背景图，不能让整个原生窗口透出桌面。

## 目录

- [平台状态](#平台状态)
- [要求](#要求)
- [仓库结构](#仓库结构)
- [安装](#安装)
  - [从 GitHub marketplace 安装](#从-github-marketplace-安装)
  - [从本地 clone 安装](#从本地-clone-安装)
- [设置自己的背景图片](#设置自己的背景图片)
- [使用方法](#使用方法)
  - [可双击启动器](#可双击启动器)
  - [命令行](#命令行)
- [Windows 首次验证](#windows-首次验证)
- [Linux 首次验证](#linux-首次验证)
- [外观配置](#外观配置)
- [工作原理](#工作原理)
- [注意事项与安全](#注意事项与安全)
- [隐私](#隐私)
- [排错](#排错)
- [卸载与恢复](#卸载与恢复)
- [License](#license)

## 平台状态

| 平台 | 状态 | 自动加载方式 |
| --- | --- | --- |
| macOS | 稳定，已实机验证 | 用户级 LaunchAgent |
| Windows 10/11 原生 PowerShell | 实验| 用户启动目录 `.cmd` |
| Linux 桌面版 | 实验| XDG autostart `.desktop` |

- [Windows 桌面应用官方说明](https://learn.chatgpt.com/docs/windows/windows-app)
- [Linux 桌面应用官方说明](https://learn.chatgpt.com/docs/linux/linux-app)

## 要求

- Python 3.9 或更高版本
- 无第三方 Python 依赖
- ChatGPT/Codex 桌面应用
- Windows 必须从原生 PowerShell Agent 运行；WSL 桥接尚未实现
- Linux 当前面向官方支持的 `.deb`/`.rpm` 桌面应用

助手会自动查找应用。若应用位于非标准位置，可以设置 `CODEX_BACKGROUND_APP` 为可执行文件的绝对路径。
启用自动加载时，当前覆盖值会写入本机的用户启动项；路径改变后应先关闭再重新启用自动加载。该启动项不位于 Git 仓库中。

## 仓库结构

```text
codex_background/
├── .agents/plugins/marketplace.json
├── tests/
└── plugins/codex_background/
    ├── .codex-plugin/plugin.json
    ├── assets/background.png
    ├── config.json
    ├── scripts/
    │   ├── codex_background.py
    │   └── codex_background_platforms/
    │       ├── base.py
    │       ├── macos.py
    │       ├── windows.py
    │       └── linux.py
    └── skills/codex-background/
        ├── SKILL.md
        └── references/platforms.md
```

仓库同时是一个 Codex Git marketplace。随附的 Skill 会让 Codex 理解如何检查、启用、关闭和配置背景。

## 安装

### 从 GitHub marketplace 安装

```bash
codex plugin marketplace add Ayachi2225/codex_background --ref main
codex plugin add codex_background@codex_background
```

安装后建议新建一个 Codex 任务，让新版本插件和 Skill 被完整加载。

### 从本地 clone 安装

macOS/Linux：

```bash
git clone https://github.com/Ayachi2225/codex_background.git
cd codex_background
codex plugin marketplace add "$PWD"
codex plugin add codex_background@codex_background
```

Windows PowerShell：

```powershell
git clone https://github.com/Ayachi2225/codex_background.git
Set-Location codex_background
codex plugin marketplace add (Get-Location).Path
codex plugin add codex_background@codex_background
```

## 设置自己的背景图片

支持 PNG、JPEG 和 WebP。推荐使用 16:9、1920×1080 或更高分辨率的图片。

macOS/Linux：

```bash
python3 plugins/codex_background/scripts/codex_background.py \
  set-image /absolute/path/to/your-background.png
```

Windows PowerShell：

```powershell
py -3 plugins/codex_background/scripts/codex_background.py `
  set-image "C:\absolute\path\to\your-background.png"
```

命令会把图片复制到插件的 `assets/` 目录并更新 `config.json`。不要把私人背景图片重新提交到公开仓库。

## 使用方法

### 可双击启动器

| 操作 | macOS | Windows | Linux |
| --- | --- | --- | --- |
| 立即启用 | `Start Background.command` | `Start Background.cmd` | `Start Background.sh` |
| 恢复原貌 | `Restore Original.command` | `Restore Original.cmd` | `Restore Original.sh` |
| 启用自动加载 | `Enable Automatic Loading.command` | `Enable Automatic Loading.cmd` | `Enable Automatic Loading.sh` |
| 关闭自动加载 | `Disable Automatic Loading.command` | `Disable Automatic Loading.cmd` | `Disable Automatic Loading.sh` |

Linux 文件管理器可能要求先允许脚本作为程序执行，也可以直接在终端运行。

### 命令行

macOS/Linux 使用 `python3`，Windows 使用 `py -3` 或 `python`：

```text
<python> plugins/codex_background/scripts/codex_background.py doctor
<python> plugins/codex_background/scripts/codex_background.py status
<python> plugins/codex_background/scripts/codex_background.py enable-autostart
<python> plugins/codex_background/scripts/codex_background.py disable-autostart
<python> plugins/codex_background/scripts/codex_background.py start
<python> plugins/codex_background/scripts/codex_background.py restore
```

- `start` 和 `restore` 会重启桌面应用并中断当前任务连接。
- `enable-autostart` 不会重启当前正在运行的应用；监视器会保护当前进程并接管之后的普通启动。
- Windows/Linux 启用自动加载后，会立即启动本次登录会话的监视器，并安装下次登录时的启动项。

## Windows 首次验证

Windows 适配尚需实机验证。建议先不要启用自动加载，依次执行：

```powershell
py -3 plugins/codex_background/scripts/codex_background.py doctor
py -3 plugins/codex_background/scripts/codex_background.py start
Start-Sleep -Seconds 8
py -3 plugins/codex_background/scripts/codex_background.py status
```

确认背景生效并且 `status` 显示 `active` 后，再测试：

```powershell
py -3 plugins/codex_background/scripts/codex_background.py restore
py -3 plugins/codex_background/scripts/codex_background.py enable-autostart
```

如果 `doctor` 找不到 Microsoft Store 安装的应用，先从 PowerShell 找到 `ChatGPT.exe`，再为当前会话设置：

```powershell
$env:CODEX_BACKGROUND_APP = "C:\path\to\ChatGPT.exe"
```

<!-- Windows 版本最大的待验证点是 Microsoft Store/MSIX 构建是否允许直接执行 `ChatGPT.exe` 并保留 Chromium 调试参数。若应用过滤这些参数，`doctor` 可能成功，但 `start` 后调试端口不会就绪。 -->

## Linux 首次验证

Linux 桌面应用仍处于预览，本插件尚未实机验证：

```bash
command -v chatgpt
python3 plugins/codex_background/scripts/codex_background.py doctor
python3 plugins/codex_background/scripts/codex_background.py start
sleep 8
python3 plugins/codex_background/scripts/codex_background.py status
```

Linux 适配默认通过 `chatgpt` 命令定位应用，通过 `/proc` 检测进程，通过 XDG autostart 安装用户启动项。

## 外观配置

编辑 `plugins/codex_background/config.json`：

| 字段 | 范围 | 作用 |
| --- | --- | --- |
| `image` | 插件内相对路径 | 背景图片文件 |
| `fit` | `cover` / `contain` / `fill` | 图片适配方式 |
| `position` | CSS `background-position` | 图片位置 |
| `backgroundOpacity` | 0–1 | 背景图片本身的不透明度 |
| `overlayOpacity` | 0–1 | 深色遮罩的不透明度；越大越暗 |
| `panelOpacity` | 0–1 | 内部面板的不透明度；越小越容易看到背景 |
| `blurPixels` | 0–40 | 背景模糊半径 |
| `debugPort` | 1024–65535 | 本机 Chromium 调试端口 |

修改后先运行 `doctor`。若背景已经启用，运行 `start` 会直接刷新样式；若尚未启用，则会重启应用。

## 工作原理

1. 通用核心读取配置和本地图片。
2. 当前平台适配器定位并重启未修改的应用可执行文件，同时加入仅监听 `127.0.0.1` 的 Chromium DevTools 参数。
3. 助手通过 Chrome DevTools Protocol 的 `Runtime.evaluate` 注入 CSS 和背景层。
4. 图片在本机转换为 data URL，不会上传到远端。
5. `MutationObserver` 在界面更新时维持样式。
6. 平台适配器分别使用 LaunchAgent、Windows 用户启动目录或 XDG autostart 维护登录监视器。
7. 执行恢复命令会关闭自动加载并以无调试参数的方式重启应用；应用文件始终未被修改。

## 注意事项与安全

- 启用背景时会开放 `127.0.0.1:<debugPort>`。它不监听局域网，但同一台设备上的其他本地进程可能访问该端口。
- 自动加载首次接管普通启动时，应用会短暂重开一次。
- `start` 和 `restore` 会中断当前桌面任务连接；先等待正在生成的回复结束。
- 应用更新可能改变 CSS 类名、renderer 结构、可执行文件路径或调试参数行为。
- 插件不提供原生窗口透明度；`panelOpacity` 只影响内部界面面板。
- Windows 和 Linux 支持未经实机确认前均视为实验性。
- 不要把私人照片、访问令牌、日志或 `.runtime/` 内容提交到公开仓库。
- 该插件依赖未公开保证的运行时行为，未来应用版本可能阻止调试端口或样式注入。

## 隐私

- 插件不包含遥测代码。
- 插件不主动连接互联网。
- 背景图片只在本机读取并注入本地 renderer。
- `.gitignore` 排除运行状态、日志、Python 缓存、环境变量文件和常见密钥文件。

## 排错

```text
<python> plugins/codex_background/scripts/codex_background.py doctor
<python> plugins/codex_background/scripts/codex_background.py status
```

`127.0.0.1:9229` 只有在背景模式已启用时才会响应。运行日志位于插件目录的 `.runtime/background.log`。

常见问题：

- `doctor` 找不到应用：设置 `CODEX_BACKGROUND_APP`。
- Windows 显示 WSL 环境：切换 Codex Agent 到 Windows 原生 PowerShell，并重新打开任务。
- `start` 后端口未就绪：当前平台应用可能过滤 Chromium 参数，请附上 `.runtime/background.log` 和 `doctor` 输出报告问题。
- 背景存在但面板不透明：降低 `panelOpacity`，不是 `backgroundOpacity`。
- 选中文本后无法添加注释：升级到 `0.2.1` 或更高版本；早期版本的背景层级规则可能覆盖 Codex 的选区浮层定位。

## 卸载与恢复

```text
<python> plugins/codex_background/scripts/codex_background.py disable-autostart
<python> plugins/codex_background/scripts/codex_background.py restore
codex plugin remove codex_background@codex_background
codex plugin marketplace remove codex_background
```

## License

[MIT](LICENSE)
