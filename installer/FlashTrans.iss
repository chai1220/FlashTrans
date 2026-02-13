#define Flavor GetEnv("FLASHTRANS_FLAVOR")
#if Flavor == "nllb"
  #define MyAppName "FlashTrans-NLLB"
  #define MyAppExeName "FlashTrans-NLLB.exe"
  #define MyAppId "{{5B7D3196-2A0C-4D75-9E87-1D6FD0A92EAA}"
#elif Flavor == "qwen"
  #define MyAppName "FlashTrans-Qwen"
  #define MyAppExeName "FlashTrans-Qwen.exe"
  #define MyAppId "{{A55B614E-4E62-4F95-9F15-0F8FEE5CF94F}"
#else
  #define MyAppName "FlashTrans"
  #define MyAppExeName "FlashTrans.exe"
  #define MyAppId "{{C9A5B4ED-3A79-4D31-8F3D-0E1A5C5C1B8D}"
#endif
#define MyAppVersion GetEnv("APP_VERSION")
#if MyAppVersion == ""
  #define MyAppVersion "1.0.0"
#endif

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=..\Output
OutputBaseFilename={#MyAppName}-Setup-{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardStyle=modern

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
