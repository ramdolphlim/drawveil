# 下载 LibreDWG（GPL-3.0）Windows 版的 dwg2dxf.exe / dxf2dwg.exe 和所需 DLL，放到 桌面版\libredwg\
# 只在“没装 ODA File Converter”的电脑上兜底使用。用法：powershell -ExecutionPolicy Bypass -File tools\fetch_libredwg.ps1 [-Ver 0.14]
param([string]$Ver = "0.14")
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $PSScriptRoot
$Out = Join-Path $Here "libredwg"
if ((Test-Path "$Out\dwg2dxf.exe") -and (Test-Path "$Out\dxf2dwg.exe")) { Write-Host "LibreDWG 已存在：$Out"; exit 0 }
$Work = Join-Path $env:TEMP ("libredwg_" + [guid]::NewGuid())
New-Item -ItemType Directory -Force $Work | Out-Null
try {
  $rel = Invoke-RestMethod "https://api.github.com/repos/LibreDWG/libredwg/releases/tags/$Ver" -Headers @{ "User-Agent" = "drawveil" }
  $asset = $rel.assets | Where-Object { $_.name -match "win64.*\.zip$" } | Select-Object -First 1
  if (-not $asset) { throw "LibreDWG $Ver 没有 win64 压缩包" }
  Write-Host "下载 $($asset.name)…"
  Invoke-WebRequest $asset.browser_download_url -OutFile "$Work\l.zip"
  Expand-Archive "$Work\l.zip" -DestinationPath "$Work\x" -Force
  $exe = Get-ChildItem "$Work\x" -Recurse -Filter dwg2dxf.exe | Select-Object -First 1
  if (-not $exe) { throw "压缩包里没有 dwg2dxf.exe" }
  New-Item -ItemType Directory -Force $Out | Out-Null
  Copy-Item "$($exe.DirectoryName)\dwg2dxf.exe", "$($exe.DirectoryName)\dxf2dwg.exe" $Out
  Get-ChildItem $exe.DirectoryName -Filter *.dll | Copy-Item -Destination $Out
  $lic = Get-ChildItem "$Work\x" -Recurse -Include COPYING, COPYING.txt | Select-Object -First 1
  if ($lic) { Copy-Item $lic.FullName "$Out\COPYING" }
  @"
这里是 GNU LibreDWG $Ver 的 dwg2dxf / dxf2dwg 程序，按 GNU GPL v3 授权（见 COPYING）。
图隐 DrawVeil 以独立程序的方式调用它们，只在没有安装 ODA File Converter 时兜底读写 DWG。
源代码与二进制：https://github.com/LibreDWG/libredwg/releases/tag/$Ver
项目主页：https://www.gnu.org/software/libredwg/
"@ | Set-Content -Encoding UTF8 "$Out\README.txt"
  & "$Out\dwg2dxf.exe" --version | Select-Object -First 1
  Write-Host "完成：$Out"
} finally { Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue }
