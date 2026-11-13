; Heli Controller – instalátor pro Windows (Inno Setup 6+)
; Sestavení: otevři v Inno Setup Compileru nebo: iscc installer.iss
; Předpoklad: build_exe.bat vytvořil složku dist\HeliController\ a vendor\ViGEmBus_Setup.exe existuje.

#define MyAppName "Heli Controller"
#define MyAppVersion "0.2.0"
#define MyAppExe "HeliController.exe"
#define FwRule "HeliController UDP"
#define Port "47800"

[Setup]
AppId={{B7E1C0A2-5D2F-4C8E-9A7B-3F1E2D4C5B6A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Heli Controller
DefaultDirName={autopf}\HeliController
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=HeliController-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Potřebujeme práva správce: ViGEmBus (ovladač), pravidlo firewallu.
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExe}

[Languages]
Name: "czech"; MessagesFile: "compiler:Languages\Czech.isl"

[Tasks]
Name: "autostart"; Description: "Spouštět po zapnutí Windows (na pozadí v liště)"; GroupDescription: "Nastavení:"
Name: "desktopicon"; Description: "Ikona na ploše"; GroupDescription: "Nastavení:"; Flags: unchecked

[Files]
Source: "dist\HeliController\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Instalátor ovladače ViGEmBus (bundle, licence MIT). Stáhni z https://github.com/nefarius/ViGEmBus/releases
Source: "vendor\ViGEmBus_Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: not VigemInstalled

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\Odinstalovat {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
; Spouštění po přihlášení (jen pro aktuálního uživatele, bez práv správce)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "HeliController"; ValueData: """{app}\{#MyAppExe}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; Firewall: povolit UDP port pro privátní síť (telefon v domácí Wi-Fi)
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""{#FwRule}"" dir=in action=allow protocol=UDP localport={#Port} profile=private"; Flags: runhidden waituntilterminated
; ViGEmBus: tichá instalace (ověř přepínač /qn u konkrétní verze ViGEmBus)
Filename: "{tmp}\ViGEmBus_Setup.exe"; Parameters: "/qn /norestart"; StatusMsg: "Instaluji ovladač ViGEmBus..."; Flags: waituntilterminated; Check: not VigemInstalled
Filename: "{app}\{#MyAppExe}"; Description: "Spustit {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""{#FwRule}"""; Flags: runhidden waituntilterminated; RunOnceId: "DelFwRule"

[Code]
function VigemInstalled: Boolean;
begin
  // ViGEmBus registruje službu; pokud existuje, instalátor ji znovu nedává.
  Result := RegKeyExists(HKLM, 'SYSTEM\CurrentControlSet\Services\ViGEmBus');
end;
