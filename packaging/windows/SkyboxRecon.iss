; Skybox Recon - Windows installer (Inno Setup 6)
; Built by CI:  ISCC /DAppVersion=2.0.0 packaging\windows\SkyboxRecon.iss
#ifndef AppVersion
  #define AppVersion "2.0.0"
#endif

[Setup]
AppId={{6C1F7E4A-2B7D-4C1B-9A3E-5B1D0F2A9C11}
AppName=Skybox Recon
AppVersion={#AppVersion}
AppVerName=Skybox Recon {#AppVersion}
AppPublisher=BajanBob
AppPublisherURL=https://github.com/BajanBob/skybox
AppSupportURL=https://github.com/BajanBob/skybox/issues
DefaultDirName={autopf}\Skybox Recon
DefaultGroupName=Skybox Recon
DisableProgramGroupPage=yes
; Lets a user without admin rights install just for themselves.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\package
OutputBaseFilename=SkyboxRecon-{#AppVersion}-Windows-x64-Setup
SetupIconFile=..\..\assets\icon.ico
UninstallDisplayIcon={app}\SkyboxRecon.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\SkyboxRecon.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\dist\skybox-cli.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\dist\tools\*"; DestDir: "{app}\tools"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\Run-SkyboxRecon.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\README-WINDOWS.txt"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\Skybox Recon"; Filename: "{app}\SkyboxRecon.exe"
Name: "{group}\Skybox Recon command menu"; Filename: "{app}\Run-SkyboxRecon.bat"; WorkingDir: "{app}"
Name: "{group}\Uninstall Skybox Recon"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Skybox Recon"; Filename: "{app}\SkyboxRecon.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SkyboxRecon.exe"; Description: "{cm:LaunchProgram,Skybox Recon}"; Flags: nowait postinstall skipifsilent
