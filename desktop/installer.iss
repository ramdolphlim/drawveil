; 图隐 DrawVeil · Inno Setup 安装包脚本（可选：装了 Inno Setup 6 后 build_win.bat 会自动生成安装程序）
[Setup]
AppId={{6C1B3E2A-8D4F-4E57-9A11-D7A3E0C5F201}
AppName=图隐 DrawVeil
AppVersion=1.0.1
DefaultDirName={autopf}\DrawVeil
DefaultGroupName=图隐 DrawVeil
OutputDir=dist
OutputBaseFilename=图隐-DrawVeil-1.0.1-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\DrawVeil.exe
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern

[Languages]
Name: "chs"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\DrawVeil\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\图隐 DrawVeil"; Filename: "{app}\DrawVeil.exe"
Name: "{userdesktop}\图隐 DrawVeil"; Filename: "{app}\DrawVeil.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"

[Run]
Filename: "{app}\DrawVeil.exe"; Description: "运行图隐"; Flags: nowait postinstall skipifsilent
