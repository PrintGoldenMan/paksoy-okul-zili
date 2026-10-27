; Okul Zili – Windows kurulum programı (Inno Setup 6)
; Derleme: iscc /DAppVersion=1.0.0 installer\OkulZili.iss
; PyInstaller çıktısının dist\OkulZili\ klasöründe hazır olması gerekir.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "Okul Zili"
#define AppExe "OkulZili.exe"

[Setup]
AppId={{6B0F3C1E-5A7D-4C1B-9E2A-0A11D5A7B001}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Abdulkadir Paksoy Anadolu Lisesi
DefaultDirName={autopf}\OkulZili
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Yönetici izni gerekmeden kullanıcıya kurulabilir; istenirse tüm kullanıcılar için de kurulabilir.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=OkulZili-Kurulum-{#AppVersion}
SetupIconFile=..\assets\okul_zili.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Program açıksa kurulum/kaldırma öncesi kapatılması istenir (programın tek kopya kilidi).
AppMutex=Local\OkulZili.TekKopya
CloseApplications=yes

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "Masaüstüne kısayol oluştur"; GroupDescription: "Kısayollar:"
Name: "autostart"; Description: "Bilgisayar açılınca Okul Zili otomatik başlasın (önerilir)"; GroupDescription: "Başlangıç:"

[Files]
Source: "..\dist\OkulZili\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} programını kaldır"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Programın kendi «otomatik başlat» ayarıyla aynı kayıt (okul_zili/autostart.py).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "OkulZili"; ValueData: """{app}\{#AppExe}"""; Tasks: autostart; Flags: uninsdeletevalue

[UninstallDelete]
Type: dirifempty; Name: "{app}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Okul Zili programını şimdi başlat"; Flags: nowait postinstall skipifsilent
; Program kendini güncellediğinde (sessiz kurulum, /RELAUNCH=1) kurulumdan sonra yeniden açılır.
Filename: "{app}\{#AppExe}"; Parameters: "--oz-restart"; Flags: nowait; Check: ShouldRelaunch

[UninstallRun]
; «Kapanırsa yeniden başlat» zamanlanmış görevi kaldırılır.
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""OkulZili Bekci"" /F"; Flags: runhidden; RunOnceId: "BekciSil"

[Code]
function ShouldRelaunch: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;

// Otomatik başlatma program içinden de açılmış olabilir; kaldırırken her durumda silinir.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'OkulZili');
end;
