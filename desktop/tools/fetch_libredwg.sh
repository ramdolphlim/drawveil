#!/bin/bash
# 下载并编译 LibreDWG（GPL-3.0）的 dwg2dxf / dxf2dwg，放到 桌面版/libredwg/，打包时一起带进 App。
# 只在“没装 ODA File Converter”的电脑上兜底使用。需要：联网、Xcode 命令行工具（xcode-select --install）。
# 用法：bash tools/fetch_libredwg.sh [版本，默认 0.14]
set -e
VER="${1:-0.14}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$HERE/libredwg"
if [ -x "$OUT/dwg2dxf" ] && [ -x "$OUT/dxf2dwg" ]; then echo "LibreDWG 已存在：$OUT"; exit 0; fi
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"
echo "下载 LibreDWG $VER 源码…"
curl -fsSL -o src.tar.xz "https://ftp.gnu.org/gnu/libredwg/libredwg-$VER.tar.xz" \
  || curl -fsSL -o src.tar.xz "https://github.com/LibreDWG/libredwg/releases/download/$VER/libredwg-$VER.tar.xz"
tar xf src.tar.xz
cd libredwg-*/
echo "编译（静态链接，约 3–8 分钟）…"
./configure --disable-shared --enable-static --disable-bindings --disable-werror --disable-docs >/dev/null 2>&1 \
  || ./configure --disable-shared --enable-static --disable-bindings --disable-werror >/dev/null
make -j"$(sysctl -n hw.ncpu 2>/dev/null || nproc)" -C src >/dev/null
make -j"$(sysctl -n hw.ncpu 2>/dev/null || nproc)" -C programs dwg2dxf dxf2dwg >/dev/null
mkdir -p "$OUT"
cp programs/dwg2dxf programs/dxf2dwg "$OUT/"
strip "$OUT/dwg2dxf" "$OUT/dxf2dwg" 2>/dev/null || true
cp COPYING "$OUT/COPYING"
cat > "$OUT/README.txt" <<TXT
这里是 GNU LibreDWG $VER 的 dwg2dxf / dxf2dwg 程序，按 GNU GPL v3 授权（见 COPYING）。
图隐 DrawVeil 以独立程序的方式调用它们，只在没有安装 ODA File Converter 时兜底读写 DWG。
源代码：https://ftp.gnu.org/gnu/libredwg/libredwg-$VER.tar.xz
项目主页：https://www.gnu.org/software/libredwg/
TXT
"$OUT/dwg2dxf" --version | head -1
echo "完成：$OUT"
