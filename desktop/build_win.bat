@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo == 图隐 DrawVeil · 打包 Windows 版 ==
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% --version >nul 2>nul || (echo 没有找到 Python。请先安装 https://www.python.org/downloads/windows/ ，安装时勾选 Add Python to PATH & pause & exit /b 1)
set ENGDIR=
if exist "cad_desensitize.py" set ENGDIR=%CD%
if not defined ENGDIR if exist "..\cad_desensitize.py" for %%I in ("..") do set ENGDIR=%%~fI
if not defined ENGDIR (echo 没有找到 cad_desensitize.py（应放在本文件夹或上一级） & pause & exit /b 1)
echo 引擎：%ENGDIR%\cad_desensitize.py
if not exist .venv %PY% -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt || (echo 依赖安装失败，请检查网络 & pause & exit /b 1)
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
pyinstaller --noconfirm --clean --windowed --name "DrawVeil" --icon assets\icon.ico --add-data "ui;ui" --paths "%ENGDIR%" --hidden-import cad_desensitize --version-file version_info.txt drawveil_desktop.py || (echo 打包失败 & pause & exit /b 1)
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\DrawVeil\*' -DestinationPath 'dist\图隐-DrawVeil-1.0.0-Windows.zip'"
where iscc >nul 2>nul && (iscc /Q installer.iss && echo 已生成安装包 dist\图隐-DrawVeil-1.0.0-Setup.exe)
echo.
echo 完成：%CD%\dist\DrawVeil\DrawVeil.exe
echo 便携压缩包：%CD%\dist\图隐-DrawVeil-1.0.0-Windows.zip
echo 首次运行如出现“Windows 已保护你的电脑”，点“更多信息”→“仍要运行”（程序没有代码签名）。
explorer dist
pause
