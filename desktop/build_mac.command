#!/bin/bash
# 图隐 DrawVeil · macOS 打包脚本：双击运行，生成 dist/图隐-DrawVeil.dmg
set -e
cd "$(dirname "$0")"
echo "== 图隐 DrawVeil · 打包 macOS 版 =="
PY=$(command -v python3 || true)
if [ -z "$PY" ]; then echo "没有找到 python3。请先安装：https://www.python.org/downloads/macos/"; read -p "按回车退出"; exit 1; fi
ENGINE=""
for p in ./cad_desensitize.py ../cad_desensitize.py ../脱敏工具/cad_desensitize.py; do [ -f "$p" ] && ENGINE="$p" && break; done
if [ -z "$ENGINE" ]; then echo "没有找到 cad_desensitize.py（应放在本文件夹或上一级）"; read -p "按回车退出"; exit 1; fi
ENGDIR="$(cd "$(dirname "$ENGINE")" && pwd)"
echo "引擎：$ENGDIR/cad_desensitize.py"
[ -d .venv ] || "$PY" -m venv .venv
source .venv/bin/activate
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt
rm -rf build dist
pyinstaller --noconfirm --clean --windowed --name "图隐" \
  --icon assets/icon.icns \
  --osx-bundle-identifier cc.limch.drawveil \
  --add-data "ui:ui" --paths "$ENGDIR" --hidden-import cad_desensitize \
  drawveil_desktop.py
# 声明可以打开 DXF / DWG（拖到程序图标上）
PL="dist/图隐.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string 图隐 DrawVeil" "$PL" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string 1.0.0" "$PL" 2>/dev/null || /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString 1.0.0" "$PL"
/usr/libexec/PlistBuddy -c "Add :NSHighResolutionCapable bool true" "$PL" 2>/dev/null || true
# 未签名：本机打包后去掉隔离标记，并做临时签名，避免“已损坏”提示
xattr -cr "dist/图隐.app" || true
codesign --force --deep --sign - "dist/图隐.app" 2>/dev/null || true
# 生成 dmg（带“应用程序”快捷方式，拖进去即可安装）
mkdir -p dist/dmg && cp -R "dist/图隐.app" dist/dmg/ && ln -s /Applications dist/dmg/应用程序
hdiutil create -quiet -volname "图隐 DrawVeil" -srcfolder dist/dmg -ov -format UDZO "dist/图隐-DrawVeil-1.0.0.dmg"
rm -rf dist/dmg
echo
echo "完成：$(pwd)/dist/图隐-DrawVeil-1.0.0.dmg"
echo "首次打开：在“应用程序”里右键「图隐」→ 打开（程序没有 Apple 开发者签名）。"
open dist
read -p "按回车关闭"
