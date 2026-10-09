#define AppVersion "0.8.22.1"
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
ShowLanguageDialog=yes
DisableReadyPage=yes
ArchiveExtraction=full
CloseApplications=no
RestartApplications=no
UninstallDisplayIcon={app}\xlamBOT.exe
ExtraDiskSpaceRequired={#PayloadSize}

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[LangOptions]
DialogFontName=Segoe UI
DialogFontSize=10

[Messages]
ru.SetupWindowTitle=xlamBOT · Установка
en.SetupWindowTitle=xlamBOT · Setup
ru.WelcomeLabel1=Установим%nxlamBOT.
en.WelcomeLabel1=Let’s install%nxlamBOT.
ru.WelcomeLabel2=Всё необходимое для работы бота — в одной аккуратной установке.
en.WelcomeLabel2=Everything you need to run the bot, in one installation.
ru.FinishedHeadingLabel=xlamBOT готов.
en.FinishedHeadingLabel=xlamBOT is ready.
ru.FinishedLabel=Можно запускать бота и возвращаться к игре.%n%nДальнейшие обновления он получит автоматически.
en.FinishedLabel=Launch the bot and get back to the game.%n%nFuture updates will arrive automatically.
ru.ButtonNext=Установить
en.ButtonNext=Install
ru.ButtonFinish=Готово
en.ButtonFinish=Finish

[CustomMessages]
ru.DownloadFiles=Получаем файлы бота
en.DownloadFiles=Downloading bot files
ru.BackupFolder=Не удалось создать резервную папку.
en.BackupFolder=Could not create the backup folder.
ru.DataLink=В папке данных найдена ссылка. Установка остановлена для сохранения данных.
en.DataLink=A link was found in the data folder. Setup stopped to protect your data.
ru.SaveFile=Не удалось сохранить файл:
en.SaveFile=Could not preserve file:
ru.SaveQueue=Не удалось сохранить очередь бойцов.
en.SaveQueue=Could not preserve the brawler queue.
ru.PrepareStop=Не удалось подготовить остановку старого бота.
en.PrepareStop=Could not prepare to stop the installed bot.
ru.CloseBot=Закройте старый xlamBOT и повторите установку.
en.CloseBot=Close the installed xlamBOT and run setup again.
ru.Caption=xlamBOT · Установка
en.Caption=xlamBOT · Setup
ru.Latest=Последняя версия бота — без ручной настройки.
en.Latest=The latest bot version, without manual setup.
ru.Internet=Потребуется интернет · загрузка около 326 МБ
en.Internet=Internet required · download approximately 326 MB
ru.Current=Всегда актуальная версия
en.Current=Always up to date
ru.Automatic=Файлы и обновления загружаются автоматически.
en.Automatic=Files and updates download automatically.
ru.KeepSettings=Твои настройки остаются с тобой
en.KeepSettings=Your settings stay with you
ru.KeepData=Сохраним модели, разметку и профили устройств.
en.KeepData=We preserve your models, annotations and device profiles.
ru.Desktop=Создать ярлык на рабочем столе
en.Desktop=Create a desktop shortcut
ru.UpdatesOn=Обновления подключены
en.UpdatesOn=Updates are connected
ru.CheckUpdates=Бот сам проверит новые версии и загрузит их.
en.CheckUpdates=The bot checks for new versions and downloads them.
ru.StepFiles=01  Файлы бота
en.StepFiles=01  Bot files
ru.StepVerified=Загружены и проверены
en.StepVerified=Downloaded and verified
ru.StepSettings=02  Твои настройки
en.StepSettings=02  Your settings
ru.StepMigrate=Переносим автоматически
en.StepMigrate=Transferred automatically
ru.StepReady=03  Готово к игре
en.StepReady=03  Ready to play
ru.StepFinish=Завершаем установку
en.StepFinish=Finishing installation
ru.DownloadTitle=Скачиваем xlamBOT
en.DownloadTitle=Downloading xlamBOT
ru.DownloadNote=Получаем проверенную версию программы. Требуется интернет.
en.DownloadNote=Downloading a verified version. Internet access is required.
ru.PrepareTitle=Подготавливаем xlamBOT
en.PrepareTitle=Preparing xlamBOT
ru.Almost=Осталось совсем немного.
en.Almost=Almost ready.
ru.InstallButton=Установить xlamBOT
en.InstallButton=Install xlamBOT
ru.Later=Позже
en.Later=Later
ru.Cancel=Отмена
en.Cancel=Cancel
ru.Ready=xlamBOT готов.
en.Ready=xlamBOT is ready.
ru.InstallTitle=Устанавливаем xlamBOT
en.InstallTitle=Installing xlamBOT
ru.InstallNote=Размещаем файлы и переносим твои настройки.
en.InstallNote=Installing files and preserving your settings.
ru.Finish=Готово
en.Finish=Finish
ru.InstallFiles=Установка файлов программы…
en.InstallFiles=Installing application files…
ru.FilesReady=Проверенные файлы загружены. Настройки сохранены.
en.FilesReady=Verified files downloaded. Settings preserved.
ru.Checksum=Контрольная сумма файлов бота не совпадает.
en.Checksum=Bot file checksum does not match.
ru.CopyCache=Не удалось скопировать сохранённые файлы бота.
en.CopyCache=Could not copy cached bot files.
ru.PrepareArchive=Не удалось подготовить сборку файлов программы.
en.PrepareArchive=Could not prepare to assemble application files.
ru.JoinArchive=Не удалось собрать архив программы.
en.JoinArchive=Could not assemble the application archive.
ru.DownloadDone=Загрузка завершена
en.DownloadDone=Download complete
ru.Extract=Распаковываем файлы и проверяем готовность программы.
en.Extract=Extracting files and checking the application.
ru.MissingFiles=В архиве отсутствуют необходимые файлы бота.
en.MissingFiles=Required bot files are missing from the archive.
ru.BootstrapChecksum=Контрольная сумма запускающего файла не совпадает.
en.BootstrapChecksum=Launcher checksum does not match.
ru.TargetFolder=Для чистой установки нужна отдельная папка с именем xlamBOT.
en.TargetFolder=Setup requires a separate folder named xlamBOT.
ru.OldFolder=Не удалось подтвердить папку старого бота. Установка остановлена.
en.OldFolder=Could not verify the previous bot folder. Setup stopped.
ru.DownloadError=Не удалось загрузить xlamBOT. Проверьте интернет и повторите установку.
en.DownloadError=Could not download xlamBOT. Check your internet connection and try again.
ru.BackupTitle=Сохраняем твою настройку
en.BackupTitle=Preserving your settings
ru.BackupNote=Создаём резервную копию перед обновлением.
en.BackupNote=Creating a backup before updating.
ru.DeleteOld=Не удалось удалить старую программу. Данные сохранены:
en.DeleteOld=Could not remove the previous application. Data preserved at:
ru.Progress=%1 из %2 МБ · Дождитесь завершения загрузки
en.Progress=%1 of %2 MB · Please wait for the download to finish
ru.FinishedBody=Можно запускать бота и возвращаться к игре.%n%nДальнейшие обновления он получит автоматически.
en.FinishedBody=Launch the bot and get back to the game.%n%nFuture updates will arrive automatically.
ru.UninstallLabel=Удалить xlamBOT
en.UninstallLabel=Uninstall xlamBOT
ru.LaunchBot=Запустить xlamBOT
en.LaunchBot=Launch xlamBOT

[Files]
Source: "design\rail-en.bmp"; Flags: dontcopy
Source: "{tmp}\payload\*"; DestDir: "{app}"; Excludes: "_internal\cfg\*,_internal\models\*,_internal\playstyles\*,_internal\latest_brawler_data.json"; Flags: external ignoreversion recursesubdirs createallsubdirs
Source: "{tmp}\payload\_internal\cfg\*"; DestDir: "{app}\_internal\cfg"; Flags: external onlyifdoesntexist recursesubdirs createallsubdirs
Source: "{tmp}\payload\_internal\models\*"; DestDir: "{app}\_internal\models"; Flags: external onlyifdoesntexist recursesubdirs createallsubdirs
Source: "{tmp}\payload\_internal\playstyles\*"; DestDir: "{app}\_internal\playstyles"; Flags: external onlyifdoesntexist recursesubdirs createallsubdirs
Source: "{tmp}\payload\_internal\latest_brawler_data.json"; DestDir: "{app}\_internal"; Flags: external onlyifdoesntexist

[Icons]
#ifndef TestInstaller
Name: "{group}\xlamBOT"; Filename: "{app}\xlamBOT.exe"
Name: "{group}\{cm:UninstallLabel}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\xlamBOT"; Filename: "{app}\xlamBOT.exe"; Check: DesktopShortcutWanted
#endif

[Run]
#ifndef TestInstaller
Filename: "{app}\xlamBOT.exe"; Description: "{cm:LaunchBot}"; Flags: nowait postinstall skipifsilent
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
    DownloadPage.SetText(CustomMessage('DownloadFiles'), FmtMessage(CustomMessage('Progress'), [IntToStr(Progress div 1048576), IntToStr(ProgressMax div 1048576)]));
end;

procedure CopyTree(const SourceDir, DestDir: String);
var
  Found: TFindRec;
  SourceName, DestName: String;
begin
  if not DirExists(SourceDir) then exit;
  if not ForceDirectories(DestDir) then RaiseException(CustomMessage('BackupFolder'));
  if FindFirst(SourceDir + '\*', Found) then begin
    try
      repeat
        if (Found.Name <> '.') and (Found.Name <> '..') then begin
          if (Found.Attributes and $400) <> 0 then
            RaiseException(CustomMessage('DataLink'));
          SourceName := SourceDir + '\' + Found.Name;
          DestName := DestDir + '\' + Found.Name;
          if (Found.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
            CopyTree(SourceName, DestName)
          else if not FileCopy(SourceName, DestName, False) then
            RaiseException(CustomMessage('SaveFile') + SourceName);
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
      RaiseException(CustomMessage('SaveQueue'));
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
    RaiseException(CustomMessage('PrepareStop'));
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{tmp}\stop-installed-bot.ps1') + '"', '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
    RaiseException(CustomMessage('CloseBot'));
end;

procedure InitializeWizard;
var
  Footer: TNewStaticText;
begin
  WizardForm.Caption := CustomMessage('Caption');
  if ActiveLanguage = 'en' then begin
    ExtractTemporaryFile('rail-en.bmp');
    WizardForm.WizardBitmapImage.Bitmap.LoadFromFile(ExpandConstant('{tmp}\rail-en.bmp'));
    WizardForm.WizardBitmapImage2.Bitmap.LoadFromFile(ExpandConstant('{tmp}\rail-en.bmp'));
  end;
  WizardForm.WelcomeLabel1.Font.Name := 'Segoe UI Semibold';
  WizardForm.WelcomeLabel1.Font.Size := 27;
  WizardForm.WelcomeLabel1.Top := ScaleY(29);
  WizardForm.WelcomeLabel1.Height := ScaleY(88);
  WizardForm.WelcomeLabel2.Top := ScaleY(126);
  WizardForm.WelcomeLabel2.Height := ScaleY(28);
  WizardForm.WelcomeLabel2.Caption := CustomMessage('Latest');
  PageText(WizardForm.WelcomePage, CustomMessage('Internet'), 155, 10, False);
  PageText(WizardForm.WelcomePage, CustomMessage('Current'), 197, 12, True);
  PageText(WizardForm.WelcomePage, CustomMessage('Automatic'), 225, 10, False);
  PageText(WizardForm.WelcomePage, CustomMessage('KeepSettings'), 272, 12, True);
  PageText(WizardForm.WelcomePage, CustomMessage('KeepData'), 300, 10, False);
  DesktopChoice := TNewCheckBox.Create(WizardForm);
  DesktopChoice.Parent := WizardForm.WelcomePage;
  DesktopChoice.Left := WizardForm.WelcomeLabel1.Left;
  DesktopChoice.Top := ScaleY(368);
  DesktopChoice.Width := WizardForm.WelcomeLabel1.Width;
  DesktopChoice.Height := ScaleY(24);
  DesktopChoice.Caption := CustomMessage('Desktop');
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
  WizardForm.FinishedLabel.Caption := CustomMessage('FinishedBody');
  PageText(WizardForm.FinishedPage, CustomMessage('UpdatesOn'), 215, 12, True);
  PageText(WizardForm.FinishedPage, CustomMessage('CheckUpdates'), 243, 10, False);
  WizardForm.RunList.Top := ScaleY(338);
  WizardForm.RunList.Height := ScaleY(60);
  InstallationStep(0, CustomMessage('StepFiles'), CustomMessage('StepVerified'));
  InstallationStep(1, CustomMessage('StepSettings'), CustomMessage('StepMigrate'));
  InstallationStep(2, CustomMessage('StepReady'), CustomMessage('StepFinish'));
  Footer := TNewStaticText.Create(WizardForm);
  Footer.Parent := WizardForm;
  Footer.Left := ScaleX(24);
  Footer.Top := WizardForm.NextButton.Top + ScaleY(9);
  Footer.Width := ScaleX(250);
  Footer.Font.Size := 9;
  Footer.Caption := 'xlamBOT  /  {#AppVersion}';
  DownloadPage := CreateDownloadPage(CustomMessage('DownloadTitle'), CustomMessage('DownloadNote'), @DownloadProgress);
  DownloadPage.ShowBaseNameInsteadOfUrl := True;
  StagePage := CreateOutputMarqueeProgressPage(CustomMessage('PrepareTitle'), CustomMessage('Almost'));
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
  if CurPageID = wpWelcome then WizardForm.NextButton.Caption := CustomMessage('InstallButton');
  if CurPageID = wpWelcome then WizardForm.CancelButton.Caption := CustomMessage('Later')
    else WizardForm.CancelButton.Caption := CustomMessage('Cancel');
  if CurPageID = wpFinished then WizardForm.CancelButton.Visible := False;
  if CurPageID = wpFinished then begin
    WizardForm.FinishedHeadingLabel.Caption := CustomMessage('Ready');
    WizardForm.FinishedLabel.Top := ScaleY(116);
    WizardForm.FinishedLabel.Height := ScaleY(72);
    WizardForm.FinishedLabel.Caption := CustomMessage('FinishedBody');
  end;
  if CurPageID = wpInstalling then begin
    WizardForm.PageNameLabel.Caption := CustomMessage('InstallTitle');
    WizardForm.PageDescriptionLabel.Caption := CustomMessage('InstallNote');
  end;
#ifdef TestInstaller
  // Isolated rendering previews do not install or modify the bot.
  if (CurPageID = wpWelcome) and (ExpandConstant('{param:DESIGNPAGE|}') = 'finish') then begin
    WizardForm.OuterNotebook.ActivePage := WizardForm.FinishedPage;
    WizardForm.FinishedHeadingLabel.Caption := CustomMessage('Ready');
    WizardForm.NextButton.Caption := CustomMessage('Finish');
    WizardForm.CancelButton.Visible := False;
  end;
  if (CurPageID = wpWelcome) and (ExpandConstant('{param:DESIGNPAGE|}') = 'install') then begin
    WizardForm.OuterNotebook.ActivePage := WizardForm.InnerPage;
    WizardForm.InnerNotebook.ActivePage := WizardForm.InstallingPage;
    WizardForm.MainPanel.Visible := True;
    WizardForm.PageNameLabel.Caption := CustomMessage('InstallTitle');
    WizardForm.PageDescriptionLabel.Caption := CustomMessage('InstallNote');
    WizardForm.StatusLabel.Caption := CustomMessage('InstallFiles');
    WizardForm.FilenameLabel.Caption := CustomMessage('FilesReady');
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
        RaiseException(CustomMessage('Checksum'));
      if not FileCopy(CachedPath, ArchivePath, False) then
        RaiseException(CustomMessage('CopyCache'));
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
        RaiseException(CustomMessage('PrepareArchive'));
      if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
        '-NoProfile -ExecutionPolicy Bypass -File "' + JoinScript + '"', '', SW_HIDE, ewWaitUntilTerminated, JoinCode) or (JoinCode <> 0) then
        RaiseException(CustomMessage('JoinArchive'));
    end;
    if CompareText(GetSHA256OfFile(ArchivePath), '{#PayloadHash}') <> 0 then
      RaiseException(CustomMessage('Checksum'));
    StagePage.SetText(CustomMessage('DownloadDone'), CustomMessage('Extract'));
    StagePage.Show;
    try
      ExtractArchive(ArchivePath, ExpandConstant('{tmp}\payload'), '', True, nil);
    finally
      StagePage.Hide;
    end;
    if not FileExists(ExpandConstant('{tmp}\payload\xlamBOT.exe')) or
       not FileExists(ExpandConstant('{tmp}\payload\_internal\python313.dll')) then
      RaiseException(CustomMessage('MissingFiles'));
    BootstrapPath := ExpandConstant('{param:BOOTSTRAP|}');
    if BootstrapPath = '' then begin
      DownloadPage.Clear;
      DownloadPage.Add('{#BootstrapUrl}', 'xlamBOT-bootstrap.zip', '{#BootstrapHash}');
      DownloadPage.Show;
      try DownloadPage.Download; finally DownloadPage.Hide; end;
      BootstrapPath := ExpandConstant('{tmp}\xlamBOT-bootstrap.zip');
    end;
    if CompareText(GetSHA256OfFile(BootstrapPath), '{#BootstrapHash}') <> 0 then
      RaiseException(CustomMessage('BootstrapChecksum'));
    ExtractArchive(BootstrapPath, ExpandConstant('{tmp}\payload'), '', True, nil);
    if CompareText(ExtractFileName(RemoveBackslash(ExpandConstant('{app}'))), 'xlamBOT') <> 0 then
      RaiseException(CustomMessage('TargetFolder'));
    ReplaceOld := FileExists(ExpandConstant('{app}\xlamBOT.exe'));
    if ReplaceOld then begin
      if not FileExists(ExpandConstant('{app}\_internal\python313.dll')) then
        RaiseException(CustomMessage('OldFolder'));
      StopInstalledBot;
    end;
    Prepared := True;
  except
    Result := CustomMessage('DownloadError') + #13#10 + GetExceptionMessage;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Suffix: Integer;
begin
  if (CurStep = ssInstall) and ReplaceOld then begin
    StopInstalledBot;
    BackupDir := ExpandConstant('{localappdata}\xlamBOT\backups\install-') + GetDateTimeString('yyyymmdd-hhnnss', '-', ':');
    Suffix := 0;
    while DirExists(BackupDir) do begin
      Suffix := Suffix + 1;
      BackupDir := BackupDir + '-' + IntToStr(Suffix);
    end;
    StagePage.SetText(CustomMessage('BackupTitle'), CustomMessage('BackupNote'));
    StagePage.Show;
    try
      Log('Backing up existing installation after stopping bot.');
      CopyTree(ExpandConstant('{app}'), BackupDir);
    finally
      StagePage.Hide;
    end;
    Log('Saved previous installation: ' + BackupDir);
    // A pending update helper may have restarted the old executable during
    // extraction or backup. Stop it again immediately before replacing files.
    StopInstalledBot;
    // Download, checksum, target validation and backup all completed before deletion.
    OldDeleted := True;
    if not DelTree(ExpandConstant('{app}'), True, True, True) then
      RaiseException(CustomMessage('DeleteOld') + BackupDir);
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
      StopInstalledBot;
      CopyTree(BackupDir, ExpandConstant('{app}'));
      Log('Restored previous installation after interrupted setup.');
    except
      Log('Previous installation backup: ' + BackupDir + '. ' + GetExceptionMessage);
    end;
  end;
end;
