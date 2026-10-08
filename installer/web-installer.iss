#define AppVersion "0.8.19"
#ifndef BootstrapHash
  #error Supply /DBootstrapHash=<SHA256 of verified PC bootstrap EXE>
#endif
#ifndef BootstrapUrl
  #error Supply /DBootstrapUrl=<immutable repository bootstrap URL>
#endif
#ifndef PayloadHash
  #error Supply /DPayloadHash=<SHA256 of runtime ZIP>
#endif
#ifndef PayloadSize
  #error Supply /DPayloadSize=<unpacked bytes>
#endif
#ifndef PayloadBase
  #error Supply /DPayloadBase=<immutable repository runtime URL>
#endif

[Setup]
#ifdef TestInstaller
AppId=xlamBOT-Web-Installer-Isolated-Test
Uninstallable=no
CreateUninstallRegKey=no
#else
AppId={{7C2E1B4A-9F3D-4A61-8B0C-5D6E7F8A9B01}
#endif
AppName=xlamBOT
AppVersion={#AppVersion}
AppPublisher=xlamBOT
DefaultDirName={localappdata}\Programs\xlamBOT
DefaultGroupName=xlamBOT
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=xlamBOT-Web-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern dark polar includetitlebar hidebevels
WizardBackColor=#11151f
WizardImageFile=design\rail.png
WizardSmallImageFile=design\mark.png
SetupIconFile=xlambot.ico
WizardSizePercent=135,135
DisableWelcomePage=no
DisableReadyPage=yes
ArchiveExtraction=full
CloseApplications=force
RestartApplications=no
UninstallDisplayIcon={app}\xlamBOT.exe
ExtraDiskSpaceRequired={#PayloadSize}

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[LangOptions]
DialogFontName=Segoe UI
DialogFontSize=10

[Messages]
SetupWindowTitle=xlamBOT · Установка
WelcomeLabel1=Установим%nxlamBOT.
WelcomeLabel2=Всё необходимое для работы бота — в одной аккуратной установке.
FinishedHeadingLabel=xlamBOT готов.
FinishedLabel=Можно запускать бота и возвращаться к игре.%n%nДальнейшие обновления он получит автоматически.
ButtonNext=Установить
ButtonFinish=Готово

[Files]
Source: "{tmp}\payload\*"; DestDir: "{app}"; Excludes: "_internal\cfg\*,_internal\models\*,_internal\playstyles\*,_internal\latest_brawler_data.json"; Flags: external ignoreversion recursesubdirs createallsubdirs
Source: "{tmp}\payload\_internal\cfg\*"; DestDir: "{app}\_internal\cfg"; Flags: external onlyifdoesntexist recursesubdirs createallsubdirs
Source: "{tmp}\payload\_internal\models\*"; DestDir: "{app}\_internal\models"; Flags: external onlyifdoesntexist recursesubdirs createallsubdirs
Source: "{tmp}\payload\_internal\playstyles\*"; DestDir: "{app}\_internal\playstyles"; Flags: external onlyifdoesntexist recursesubdirs createallsubdirs
Source: "{tmp}\payload\_internal\latest_brawler_data.json"; DestDir: "{app}\_internal"; Flags: external onlyifdoesntexist

[Icons]
#ifndef TestInstaller
Name: "{group}\xlamBOT"; Filename: "{app}\xlamBOT.exe"
Name: "{group}\Удалить xlamBOT"; Filename: "{uninstallexe}"
Name: "{autodesktop}\xlamBOT"; Filename: "{app}\xlamBOT.exe"; Check: DesktopShortcutWanted
#endif

[Run]
#ifndef TestInstaller
Filename: "{app}\xlamBOT.exe"; Description: "Запустить xlamBOT"; Flags: nowait postinstall skipifsilent
#endif

[Code]
var
  DownloadPage: TDownloadWizardPage;
  Prepared: Boolean;
  ReplaceOld: Boolean;
  BackupDir: String;
  OldDeleted: Boolean;
  Finished: Boolean;
  DesktopChoice: TNewCheckBox;
  StagePage: TOutputMarqueeProgressWizardPage;

procedure PageText(Page: TWinControl; const Caption: String; Y, Size: Integer; Bold: Boolean);
var
  Text: TNewStaticText;
begin
  Text := TNewStaticText.Create(WizardForm);
  Text.Parent := Page;
  Text.Left := WizardForm.WelcomeLabel1.Left;
  Text.Top := ScaleY(Y);
  Text.Width := WizardForm.WelcomeLabel1.Width;
  Text.Height := ScaleY(32);
  Text.AutoSize := False;
  Text.WordWrap := True;
  Text.Font.Name := 'Segoe UI';
  Text.Font.Size := Size;
  if Bold then Text.Font.Style := [fsBold];
  Text.Caption := Caption;
end;

procedure InstallationStep(Index: Integer; const Title, Detail: String);
var
  Text: TNewStaticText;
  ColumnWidth, ColumnLeft: Integer;
begin
  ColumnWidth := (WizardForm.ProgressGauge.Width - ScaleX(24)) div 3;
  ColumnLeft := WizardForm.ProgressGauge.Left + Index * (ColumnWidth + ScaleX(12));
  Text := TNewStaticText.Create(WizardForm);
  Text.Parent := WizardForm.InstallingPage;
  Text.Left := ColumnLeft;
  Text.Top := ScaleY(144);
  Text.Width := ColumnWidth;
  Text.Height := ScaleY(30);
  Text.AutoSize := False;
  Text.WordWrap := True;
  Text.Font.Size := 11;
  Text.Font.Style := [fsBold];
  Text.Caption := Title;
  Text := TNewStaticText.Create(WizardForm);
  Text.Parent := WizardForm.InstallingPage;
  Text.Left := ColumnLeft;
  Text.Top := ScaleY(178);
  Text.Width := ColumnWidth;
  Text.Height := ScaleY(42);
  Text.AutoSize := False;
  Text.WordWrap := True;
  Text.Font.Size := 10;
  Text.Caption := Detail;
end;

function DownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  Result := True;
  if ProgressMax > 0 then
    DownloadPage.SetText('Получаем файлы бота', IntToStr(Progress div 1048576) + ' из ' + IntToStr(ProgressMax div 1048576) + ' МБ · Дождитесь завершения загрузки');
end;

procedure CopyTree(const SourceDir, DestDir: String);
var
  Found: TFindRec;
  SourceName, DestName: String;
begin
  if not DirExists(SourceDir) then exit;
  if not ForceDirectories(DestDir) then RaiseException('Не удалось создать резервную папку.');
  if FindFirst(SourceDir + '\*', Found) then begin
    try
      repeat
        if (Found.Name <> '.') and (Found.Name <> '..') then begin
          if (Found.Attributes and $400) <> 0 then
            RaiseException('В папке данных найдена ссылка. Установка остановлена для сохранения данных.');
          SourceName := SourceDir + '\' + Found.Name;
          DestName := DestDir + '\' + Found.Name;
          if (Found.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
            CopyTree(SourceName, DestName)
          else if not FileCopy(SourceName, DestName, False) then
            RaiseException('Не удалось сохранить файл: ' + SourceName);
        end;
      until not FindNext(Found);
    finally
      FindClose(Found);
    end;
  end;
end;

procedure CopyUserData(const SourceRoot, DestRoot: String);
var
  Names: TArrayOfString;
  I: Integer;
begin
  Names := ['cfg', 'devices', 'models', 'playstyles', 'training', 'debug_frames'];
  for I := 0 to GetArrayLength(Names) - 1 do
    CopyTree(SourceRoot + '\_internal\' + Names[I], DestRoot + '\_internal\' + Names[I]);
  if FileExists(SourceRoot + '\_internal\latest_brawler_data.json') then begin
    ForceDirectories(DestRoot + '\_internal');
    if not FileCopy(SourceRoot + '\_internal\latest_brawler_data.json', DestRoot + '\_internal\latest_brawler_data.json', False) then
      RaiseException('Не удалось сохранить очередь бойцов.');
  end;
end;

procedure StopInstalledBot;
var
  Script, AppExe: String;
  Code: Integer;
begin
  AppExe := ExpandConstant('{app}\xlamBOT.exe');
  StringChangeEx(AppExe, '''', '''''', True);
  Script := '$ErrorActionPreference = ''Stop''; Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq ''' + AppExe + ''' } | ForEach-Object { $p = Get-Process -Id $_.ProcessId; Stop-Process -Id $_.ProcessId -Force; $p.WaitForExit() }';
  if not SaveStringToFile(ExpandConstant('{tmp}\stop-installed-bot.ps1'), Script, False) then
    RaiseException('Не удалось подготовить остановку старого бота.');
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{tmp}\stop-installed-bot.ps1') + '"', '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
    RaiseException('Закройте старый xlamBOT и повторите установку.');
end;

procedure InitializeWizard;
var
  Footer: TNewStaticText;
begin
  WizardForm.Caption := 'xlamBOT · Установка';
  WizardForm.WelcomeLabel1.Font.Name := 'Segoe UI Semibold';
  WizardForm.WelcomeLabel1.Font.Size := 27;
  WizardForm.WelcomeLabel1.Top := ScaleY(29);
  WizardForm.WelcomeLabel1.Height := ScaleY(88);
  WizardForm.WelcomeLabel2.Top := ScaleY(126);
  WizardForm.WelcomeLabel2.Height := ScaleY(28);
  WizardForm.WelcomeLabel2.Caption := 'Последняя версия бота — без ручной настройки.';
  PageText(WizardForm.WelcomePage, 'Потребуется интернет · загрузка около 326 МБ', 155, 10, False);
  PageText(WizardForm.WelcomePage, 'Всегда актуальная версия', 197, 12, True);
  PageText(WizardForm.WelcomePage, 'Файлы и обновления загружаются автоматически.', 225, 10, False);
  PageText(WizardForm.WelcomePage, 'Твои настройки остаются с тобой', 272, 12, True);
  PageText(WizardForm.WelcomePage, 'Сохраним модели, разметку и профили устройств.', 300, 10, False);
  DesktopChoice := TNewCheckBox.Create(WizardForm);
  DesktopChoice.Parent := WizardForm.WelcomePage;
  DesktopChoice.Left := WizardForm.WelcomeLabel1.Left;
  DesktopChoice.Top := ScaleY(368);
  DesktopChoice.Width := WizardForm.WelcomeLabel1.Width;
  DesktopChoice.Height := ScaleY(24);
  DesktopChoice.Caption := 'Создать ярлык на рабочем столе';
  DesktopChoice.Checked := True;
  WizardForm.NextButton.Width := ScaleX(160);
  WizardForm.NextButton.Left := WizardForm.CancelButton.Left - WizardForm.NextButton.Width - ScaleX(12);
  WizardForm.NextButton.Height := ScaleY(33);
  WizardForm.CancelButton.Height := ScaleY(33);
  WizardForm.FinishedHeadingLabel.Font.Name := 'Segoe UI Semibold';
  WizardForm.FinishedHeadingLabel.Font.Size := 25;
  WizardForm.FinishedHeadingLabel.Height := ScaleY(64);
  WizardForm.FinishedHeadingLabel.Top := ScaleY(29);
  WizardForm.FinishedLabel.Top := ScaleY(116);
  WizardForm.FinishedLabel.Height := ScaleY(72);
  WizardForm.FinishedLabel.Caption := 'Можно запускать бота и возвращаться к игре.' + #13#10 + #13#10 + 'Дальнейшие обновления он получит автоматически.';
  PageText(WizardForm.FinishedPage, 'Обновления подключены', 215, 12, True);
  PageText(WizardForm.FinishedPage, 'Бот сам проверит новые версии и загрузит их.', 243, 10, False);
  WizardForm.RunList.Top := ScaleY(338);
  WizardForm.RunList.Height := ScaleY(60);
  InstallationStep(0, '01  Файлы бота', 'Загружены и проверены');
  InstallationStep(1, '02  Твои настройки', 'Переносим автоматически');
  InstallationStep(2, '03  Готово к игре', 'Завершаем установку');
  Footer := TNewStaticText.Create(WizardForm);
  Footer.Parent := WizardForm;
  Footer.Left := ScaleX(24);
  Footer.Top := WizardForm.NextButton.Top + ScaleY(9);
  Footer.Width := ScaleX(250);
  Footer.Font.Size := 9;
  Footer.Caption := 'xlamBOT  /  {#AppVersion}';
  DownloadPage := CreateDownloadPage('Скачиваем xlamBOT', 'Получаем проверенную версию программы. Требуется интернет.', @DownloadProgress);
  DownloadPage.ShowBaseNameInsteadOfUrl := True;
  StagePage := CreateOutputMarqueeProgressPage('Подготавливаем xlamBOT', 'Осталось совсем немного.');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := PageID = wpSelectTasks;
end;

function DesktopShortcutWanted: Boolean;
begin
  Result := True;
  if DesktopChoice <> nil then Result := DesktopChoice.Checked;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  WizardForm.BackButton.Visible := False;
  if CurPageID = wpWelcome then WizardForm.NextButton.Caption := 'Установить xlamBOT';
  if CurPageID = wpWelcome then WizardForm.CancelButton.Caption := 'Позже'
    else WizardForm.CancelButton.Caption := 'Отмена';
  if CurPageID = wpFinished then WizardForm.CancelButton.Visible := False;
  if CurPageID = wpFinished then begin
    WizardForm.FinishedHeadingLabel.Caption := 'xlamBOT готов.';
    WizardForm.FinishedLabel.Top := ScaleY(116);
    WizardForm.FinishedLabel.Height := ScaleY(72);
    WizardForm.FinishedLabel.Caption := 'Можно запускать бота и возвращаться к игре.' + #13#10 + #13#10 + 'Дальнейшие обновления он получит автоматически.';
  end;
  if CurPageID = wpInstalling then begin
    WizardForm.PageNameLabel.Caption := 'Устанавливаем xlamBOT';
    WizardForm.PageDescriptionLabel.Caption := 'Размещаем файлы и переносим твои настройки.';
  end;
#ifdef TestInstaller
  // Isolated rendering previews do not install or modify the bot.
  if (CurPageID = wpWelcome) and (ExpandConstant('{param:DESIGNPAGE|}') = 'finish') then begin
    WizardForm.OuterNotebook.ActivePage := WizardForm.FinishedPage;
    WizardForm.FinishedHeadingLabel.Caption := 'xlamBOT готов.';
    WizardForm.NextButton.Caption := 'Готово';
    WizardForm.CancelButton.Visible := False;
  end;
  if (CurPageID = wpWelcome) and (ExpandConstant('{param:DESIGNPAGE|}') = 'install') then begin
    WizardForm.OuterNotebook.ActivePage := WizardForm.InnerPage;
    WizardForm.InnerNotebook.ActivePage := WizardForm.InstallingPage;
    WizardForm.MainPanel.Visible := True;
    WizardForm.PageNameLabel.Caption := 'Устанавливаем xlamBOT';
    WizardForm.PageDescriptionLabel.Caption := 'Размещаем файлы и переносим твои настройки.';
    WizardForm.StatusLabel.Caption := 'Установка файлов программы…';
    WizardForm.FilenameLabel.Caption := 'Проверенные файлы загружены. Настройки сохранены.';
    WizardForm.ProgressGauge.Position := 65;
  end;
#endif
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ArchivePath, CachedPath, JoinScript, EscapedArchivePath, BootstrapPath: String;
  JoinCode: Integer;
begin
  Result := '';
  if Prepared then exit;
  try
    ArchivePath := ExpandConstant('{tmp}\runtime.zip');
    // Optional verified cache for offline installation/testing; never an unchecked payload.
    CachedPath := ExpandConstant('{param:PAYLOAD|}');
    if CachedPath <> '' then begin
      if CompareText(GetSHA256OfFile(CachedPath), '{#PayloadHash}') <> 0 then
        RaiseException('Контрольная сумма файлов бота не совпадает.');
      if not FileCopy(CachedPath, ArchivePath, False) then
        RaiseException('Не удалось скопировать сохранённые файлы бота.');
    end else begin
      DownloadPage.Clear;
      #include "runtime-download.iss"
      DownloadPage.Show;
      try
        DownloadPage.Download;
      finally
        DownloadPage.Hide;
      end;
      JoinScript := ExpandConstant('{tmp}\join-runtime.ps1');
      EscapedArchivePath := ArchivePath;
      StringChangeEx(EscapedArchivePath, '''', '''''', True);
      if not SaveStringToFile(JoinScript,
        '$ErrorActionPreference = ''Stop''; $dest = [IO.File]::Create(''' + EscapedArchivePath + '''); try { for ($i = 1; $i -le {#PartsCount}; $i++) { $src = [IO.File]::OpenRead((Join-Path $PSScriptRoot (''part-'' + $i + ''.bin''))); try { $src.CopyTo($dest) } finally { $src.Dispose() } } } finally { $dest.Dispose() }', False) then
        RaiseException('Не удалось подготовить сборку файлов программы.');
      if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
        '-NoProfile -ExecutionPolicy Bypass -File "' + JoinScript + '"', '', SW_HIDE, ewWaitUntilTerminated, JoinCode) or (JoinCode <> 0) then
        RaiseException('Не удалось собрать архив программы.');
    end;
    if CompareText(GetSHA256OfFile(ArchivePath), '{#PayloadHash}') <> 0 then
      RaiseException('Контрольная сумма файлов бота не совпадает.');
    StagePage.SetText('Загрузка завершена', 'Распаковываем файлы и проверяем готовность программы.');
    StagePage.Show;
    try
      ExtractArchive(ArchivePath, ExpandConstant('{tmp}\payload'), '', True, nil);
    finally
      StagePage.Hide;
    end;
    if not FileExists(ExpandConstant('{tmp}\payload\xlamBOT.exe')) or
       not FileExists(ExpandConstant('{tmp}\payload\_internal\python313.dll')) then
      RaiseException('В архиве отсутствуют необходимые файлы бота.');
    BootstrapPath := ExpandConstant('{param:BOOTSTRAP|}');
    if BootstrapPath = '' then begin
      DownloadPage.Clear;
      DownloadPage.Add('{#BootstrapUrl}', 'xlamBOT-bootstrap.zip', '{#BootstrapHash}');
      DownloadPage.Show;
      try DownloadPage.Download; finally DownloadPage.Hide; end;
      BootstrapPath := ExpandConstant('{tmp}\xlamBOT-bootstrap.zip');
    end;
    if CompareText(GetSHA256OfFile(BootstrapPath), '{#BootstrapHash}') <> 0 then
      RaiseException('Контрольная сумма запускающего файла не совпадает.');
    ExtractArchive(BootstrapPath, ExpandConstant('{tmp}\payload'), '', True, nil);
    if CompareText(ExtractFileName(RemoveBackslash(ExpandConstant('{app}'))), 'xlamBOT') <> 0 then
      RaiseException('Для чистой установки нужна отдельная папка с именем xlamBOT.');
    ReplaceOld := FileExists(ExpandConstant('{app}\xlamBOT.exe'));
    if ReplaceOld then begin
      if not FileExists(ExpandConstant('{app}\_internal\python313.dll')) then
        RaiseException('Не удалось подтвердить папку старого бота. Установка остановлена.');
      StopInstalledBot;
    end;
    Prepared := True;
  except
    Result := 'Не удалось загрузить xlamBOT. Проверьте интернет и повторите установку.' + #13#10 + GetExceptionMessage;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Suffix: Integer;
begin
  if (CurStep = ssInstall) and ReplaceOld then begin
    BackupDir := ExpandConstant('{localappdata}\xlamBOT\backups\install-') + GetDateTimeString('yyyymmdd-hhnnss', '-', ':');
    Suffix := 0;
    while DirExists(BackupDir) do begin
      Suffix := Suffix + 1;
      BackupDir := BackupDir + '-' + IntToStr(Suffix);
    end;
    StagePage.SetText('Сохраняем твою настройку', 'Создаём резервную копию перед обновлением.');
    StagePage.Show;
    try
      CopyTree(ExpandConstant('{app}'), BackupDir);
    finally
      StagePage.Hide;
    end;
    Log('Saved previous installation: ' + BackupDir);
    // Download, checksum, target validation and backup all completed before deletion.
    OldDeleted := True;
    if not DelTree(ExpandConstant('{app}'), True, True, True) then
      RaiseException('Не удалось удалить старую программу. Данные сохранены: ' + BackupDir);
  end;
  if CurStep = ssPostInstall then begin
    if BackupDir <> '' then CopyUserData(BackupDir, ExpandConstant('{app}'));
    Finished := True;
  end;
end;

procedure DeinitializeSetup;
begin
  if OldDeleted and not Finished and (BackupDir <> '') then begin
    try
      CopyTree(BackupDir, ExpandConstant('{app}'));
      Log('Restored previous installation after interrupted setup.');
    except
      Log('Previous installation backup: ' + BackupDir + '. ' + GetExceptionMessage);
    end;
  end;
end;
