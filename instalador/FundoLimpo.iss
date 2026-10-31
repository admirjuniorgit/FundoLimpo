; Instalador do FundoLimpo (Inno Setup 6) — gerado pelo gerar-instalador.bat
; Instala o app, cria atalhos, registra a câmera virtual "FundoLimpo Camera" e a remove ao desinstalar.

#ifndef AppVersion
  #define AppVersion "1.2.0"
#endif
#ifndef DistDir
  #define DistDir "..\dist\FundoLimpo"
#endif

[Setup]
AppId={{6F1E2D0A-8C1B-4B7E-9C51-2F0D5A7B9E31}
AppName=FundoLimpo
AppVersion={#AppVersion}
AppVerName=FundoLimpo {#AppVersion}
AppPublisher=1hs
DefaultDirName={autopf}\FundoLimpo
DefaultGroupName=FundoLimpo
DisableProgramGroupPage=yes
; registrar a câmera exige administrador
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\instalador
OutputBaseFilename=FundoLimpo-Setup-{#AppVersion}
SetupIconFile=icone.ico
UninstallDisplayIcon={app}\FundoLimpo.exe
UninstallDisplayName=FundoLimpo
VersionInfoVersion={#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"

[Files]
; o app inteiro (saída do PyInstaller), menos as DLLs da câmera, que entram abaixo com registro
Source: "{#DistDir}\*"; DestDir: "{app}"; Excludes: "fundolimpo_cam.dll"; Flags: ignoreversion recursesubdirs createallsubdirs
; câmera virtual: o Inno registra (regsvr32) ao instalar e desregistra ao desinstalar
Source: "{#DistDir}\_internal\camera\x64\fundolimpo_cam.dll"; DestDir: "{app}\_internal\camera\x64"; Flags: ignoreversion regserver 64bit
Source: "{#DistDir}\_internal\camera\x86\fundolimpo_cam.dll"; DestDir: "{app}\_internal\camera\x86"; Flags: ignoreversion regserver 32bit

[Icons]
Name: "{group}\FundoLimpo"; Filename: "{app}\FundoLimpo.exe"
Name: "{group}\Desinstalar FundoLimpo"; Filename: "{uninstallexe}"
Name: "{autodesktop}\FundoLimpo"; Filename: "{app}\FundoLimpo.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FundoLimpo.exe"; Description: "Abrir o FundoLimpo agora"; Flags: nowait postinstall skipifsilent runasoriginaluser
; atualização automática (Setup rodado pelo próprio app em modo /SILENT): reabre o app no final
Filename: "{app}\FundoLimpo.exe"; Flags: nowait postinstall skipifnotsilent runasoriginaluser

[Messages]
ptbr.FinishedLabel=O FundoLimpo foi instalado.%n%nNo OBS/Streamlabs, adicione uma fonte "Dispositivo de captura de vídeo" e escolha "FundoLimpo Camera". No Discord/Teams/Meet/Zoom, escolha essa câmera nas configurações de vídeo. Deixe o FundoLimpo aberto enquanto usa.
