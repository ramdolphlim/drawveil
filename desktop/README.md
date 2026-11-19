# 图隐 DrawVeil · 桌面版

桌面版是一个原生窗口程序，图纸只在本机处理。它支持：

- 直接处理 DWG 文件：需要安装免费的 ODA File Converter。
- 拖入图纸就开始扫描，一屏只做一件事：扫描结果 → 脱敏 → 在访达或资源管理器中显示，想看细节再点“逐项核对”。
- 同一个人在每批图纸里都用同一个代号（设置里可以关掉）。
- 监视文件夹：把图纸放进去，程序会自动脱敏，结果写到「已脱敏」子文件夹。

## 一、下载安装

到仓库的 [Releases](https://github.com/peter804762649-ux/drawveil/releases) 页下载：

| 系统 | 文件 |
|---|---|
| macOS（Apple 芯片） | `DrawVeil-版本号-mac-arm64.dmg` |
| macOS（Intel 芯片） | `DrawVeil-版本号-mac-intel.dmg` |
| Windows 10 / 11 | `DrawVeil-版本号-win-x64-setup.exe`（安装版）或 `…-portable.zip`（免安装） |

程序没有开发者签名，第一次打开会被系统拦一下：

- macOS：把「图隐」拖进「应用程序」后，右键 → 打开。如果提示“已损坏”，在终端执行 `xattr -cr /Applications/图隐.app` 再打开。
- Windows：看到“Windows 已保护你的电脑”时，点“更多信息”→“仍要运行”。

### 自己打包

每个系统各做一次，需要联网，并先装好 Python 3.9 或更新版本（https://www.python.org/downloads/ ）：

| 系统 | 操作 | 结果 |
|---|---|---|
| macOS | 双击 `build_mac.command` | `dist/图隐-DrawVeil-1.0.0.dmg` |
| Windows | 双击 `build_win.bat` | `dist\DrawVeil\DrawVeil.exe` 和便携 zip；装了 Inno Setup 6 还会生成安装程序 |

打包脚本会自动建立虚拟环境，并安装 pywebview 和 pyinstaller。仓库里推送 `v*` 标签时，GitHub Actions 会自动打出上面三种安装包（见 `.github/workflows/release.yml`）。

## 二、不打包，直接运行

```
pip install pywebview
python3 drawveil_desktop.py              # 原生窗口
python3 drawveil_desktop.py --browser    # 不装 pywebview：用浏览器打开同样的界面
```

## 三、DWG 支持

到 https://www.opendesign.com/guestfiles/oda_file_converter 免费下载 ODA File Converter 并安装。
程序会自动找到它，左下角显示绿点即为已连接。也可以在「设置 › 转换与输出」里指定路径。

## 四、数据存放位置

| 内容 | 位置 |
|---|---|
| 设置、批次、代号库 | macOS：`~/Library/Application Support/DrawVeil`；Windows：`%APPDATA%\DrawVeil` |
| 脱敏图纸 | 默认在原文件旁的「脱敏输出」文件夹，可在设置里改成统一的文件夹 |
| 报告与映射表 | 默认在 `文稿/图隐报告（内部留存）/<批次>/<时间>/` |

报告与映射表含有原文，只能内部留存，不要和图纸一起外发。

## 五、快捷操作

- `⌘/Ctrl + O`：选择图纸
- `⌘/Ctrl + ,`：打开设置
- `Esc`：返回上一步
