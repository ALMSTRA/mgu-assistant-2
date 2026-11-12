; Inno Setup 6 — MGU Assistant 2. Compile tras build.ps1:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\windows\installer.iss
#define AppName "MGU Assistant 2"
#define AppVersion "2.0.0"
#define ExeName "MGU-Assistant-2.exe"

[Setup]
AppId={{7D2F0C1A-5B6E-4E0A-9C3D-2A1B8E7F6D21}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\MGU Assistant 2
DisableProgramGroupPage=yes
OutputDir=dist\installer
OutputBaseFilename=MGU-Assistant-2-Setup-{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "..\..\dist\MGU-Assistant-2\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\MGU Assistant 2"; Filename: "{app}\{#ExeName}"
Name: "{group}\MGU Assistant 2 (demo)"; Filename: "{app}\{#ExeName}"; Parameters: "--demo"
Name: "{commondesktop}\MGU Assistant 2"; Filename: "{app}\{#ExeName}"

[Run]
Filename: "{app}\{#ExeName}"; Description: "Abrir MGU Assistant 2"; Flags: nowait postinstall skipifsilent
