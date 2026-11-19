# Harvester GOG Deutsch - einmalige Windows-Einrichtung.
# Keine Aenderungen am englischen GOG-Original. Keine Python-/FFmpeg-Abhaengigkeit.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$package = $PSScriptRoot
$targetName = 'Harvester GOG Deutsch'
$log = Join-Path $package ('INSTALLATIONS_LOG_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.txt')
$transcript = $false
$tmp = $null

function Is-HarvesterFolder([string]$path) {
    if ([string]::IsNullOrWhiteSpace($path)) { return $false }
    try {
        $full = [IO.Path]::GetFullPath($path.Trim().Trim('"').TrimEnd([char[]]'\/'))
        if (-not (Test-Path -LiteralPath $full -PathType Container)) { return $false }
        foreach ($f in @('HARVEST.EXE', 'HARVEST.DAT', 'HARVEST3.DAT', 'HARVEST4.DAT', 'DOSBOX\DOSBox.exe', 'dosbox_harvester_single.conf')) {
            if (-not (Test-Path -LiteralPath (Join-Path $full $f) -PathType Leaf)) { return $false }
        }
        return $true
    } catch { return $false }
}

function Find-GogOriginal {
    foreach ($hive in @([Microsoft.Win32.RegistryHive]::LocalMachine, [Microsoft.Win32.RegistryHive]::CurrentUser)) {
        foreach ($view in @([Microsoft.Win32.RegistryView]::Registry32, [Microsoft.Win32.RegistryView]::Registry64)) {
            try {
                $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive, $view)
                try {
                    $key = $base.OpenSubKey('Software\GOG.com\Games\1207661373', $false)
                    if ($null -eq $key) { continue }
                    try {
                        foreach ($value in @('DOSBOXFOLDER', 'path', 'gamepath')) {
                            $candidate = [string]$key.GetValue($value, '')
                            if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
                            try {
                                $candidate = [IO.Path]::GetFullPath($candidate.Trim().Trim('"').TrimEnd([char[]]'\/'))
                                # DOSBOXFOLDER usually points to <Game>\DOSBOX.
                                # Some Registry versions use a game directory instead.
                                foreach ($c in @($candidate, [IO.Path]::GetDirectoryName($candidate), [IO.Path]::GetDirectoryName([IO.Path]::GetDirectoryName($candidate)))) {
                                    if (Is-HarvesterFolder $c) { return $c }
                                }
                            } catch { }
                        }
                    } finally { $key.Close() }
                } finally { $base.Close() }
            } catch { }
        }
    }
    return $null
}

function Choose-Paths([string]$detected) {
    $finalName = "Harvester GOG Deutsch"
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    [System.Windows.Forms.Application]::EnableVisualStyles()

    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'Harvester GOG Deutsch - Installation'
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
    $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
    $form.ClientSize = [System.Drawing.Size]::new(750, 330)
    $form.ShowInTaskbar = $true
    $form.TopMost = $true    # Verhindert das Verstecken hinter dem CMD-Fenster.
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.Font = [System.Drawing.Font]::new('Segoe UI', 9)

    $heading = New-Object System.Windows.Forms.Label
    $heading.Text = 'Deutsches Harvester installieren'
    $heading.Font = [System.Drawing.Font]::new('Segoe UI', 13, [System.Drawing.FontStyle]::Bold)
    $heading.Location = [System.Drawing.Point]::new(18, 13)
    $heading.Size = [System.Drawing.Size]::new(710, 32)
    $form.Controls.Add($heading)

    $info = New-Object System.Windows.Forms.Label
    $info.Text = 'Die englische GOG-Version bleibt unveraendert. Pruefe den vorgeschlagenen Quellordner.'
    $info.Location = [System.Drawing.Point]::new(18, 49)
    $info.Size = [System.Drawing.Size]::new(710, 24)
    $form.Controls.Add($info)

    $sourceLabel = New-Object System.Windows.Forms.Label
    $sourceLabel.Text = '1. Englischer GOG-Spielordner:'
    $sourceLabel.Location = [System.Drawing.Point]::new(18, 83)
    $sourceLabel.Size = [System.Drawing.Size]::new(500, 20)
    $form.Controls.Add($sourceLabel)

    $sourceBox = New-Object System.Windows.Forms.TextBox
    $sourceBox.Location = [System.Drawing.Point]::new(18, 105)
    $sourceBox.Size = [System.Drawing.Size]::new(608, 25)
    $sourceBox.Text = [string]$detected
    $form.Controls.Add($sourceBox)
    $sourceBrowse = New-Object System.Windows.Forms.Button
    $sourceBrowse.Text = 'Auswaehlen...'
    $sourceBrowse.Location = [System.Drawing.Point]::new(635, 103)
    $sourceBrowse.Size = [System.Drawing.Size]::new(100, 29)
    $form.Controls.Add($sourceBrowse)

    $destLabel = New-Object System.Windows.Forms.Label
    $destLabel.Text = '2. Ziel-Speicherort (hier wird ein neuer Unterordner angelegt):'
    $destLabel.Location = [System.Drawing.Point]::new(18, 147)
    $destLabel.Size = [System.Drawing.Size]::new(710, 20)
    $form.Controls.Add($destLabel)

    $destBox = New-Object System.Windows.Forms.TextBox
    $destBox.Location = [System.Drawing.Point]::new(18, 170)
    $destBox.Size = [System.Drawing.Size]::new(608, 25)
    if ($detected) { $destBox.Text = [IO.Path]::GetDirectoryName($detected) }
    $form.Controls.Add($destBox)
    $destBrowse = New-Object System.Windows.Forms.Button
    $destBrowse.Text = 'Auswaehlen...'
    $destBrowse.Location = [System.Drawing.Point]::new(635, 168)
    $destBrowse.Size = [System.Drawing.Size]::new(100, 29)
    $form.Controls.Add($destBrowse)

    $preview = New-Object System.Windows.Forms.Label
    $preview.Location = [System.Drawing.Point]::new(18, 211)
    $preview.Size = [System.Drawing.Size]::new(715, 39)
    $preview.AutoEllipsis = $true
    $form.Controls.Add($preview)
    $destBox.Add_TextChanged({
        if ([string]::IsNullOrWhiteSpace($destBox.Text)) { $preview.Text = ('Neuer Ordner: ' + $finalName) }
        else { $preview.Text = ('Neuer Ordner: ' + [IO.Path]::Combine($destBox.Text.Trim().Trim('"'), $finalName)) }
    }.GetNewClosure())
    if ($destBox.Text) { $preview.Text = ('Neuer Ordner: ' + [IO.Path]::Combine($destBox.Text.Trim().Trim('"'), $finalName)) }
    else { $preview.Text = ('Neuer Ordner: ' + $finalName) }

    $note = New-Object System.Windows.Forms.Label
    $note.Text = 'Ein vorhandener Zielordner wird niemals ueberschrieben.'
    $note.Location = [System.Drawing.Point]::new(18, 259)
    $note.Size = [System.Drawing.Size]::new(440, 20)
    $form.Controls.Add($note)

    $cancel = New-Object System.Windows.Forms.Button
    $cancel.Text = 'Abbrechen'
    $cancel.Location = [System.Drawing.Point]::new(502, 284)
    $cancel.Size = [System.Drawing.Size]::new(108, 32)
    $cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.Controls.Add($cancel)
    $form.CancelButton = $cancel

    $install = New-Object System.Windows.Forms.Button
    $install.Text = 'Installieren'
    $install.Location = [System.Drawing.Point]::new(620, 284)
    $install.Size = [System.Drawing.Size]::new(115, 32)
    $form.Controls.Add($install)
    $form.AcceptButton = $install

    $sourceBrowse.Add_Click({
        $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
        try {
            $dlg.Description = 'Englischen GOG-Harvester-Spielordner auswaehlen'
            $dlg.ShowNewFolderButton = $false
            if (Test-Path -LiteralPath $sourceBox.Text -PathType Container) { $dlg.SelectedPath = $sourceBox.Text }
            if ($dlg.ShowDialog($form) -eq [System.Windows.Forms.DialogResult]::OK) {
                $oldParent = ''
                try { if ($sourceBox.Text) { $oldParent = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($sourceBox.Text)) } } catch { }
                $sourceBox.Text = $dlg.SelectedPath
                if (-not $destBox.Text -or $destBox.Text -eq $oldParent) {
                    $destBox.Text = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($dlg.SelectedPath))
                }
            }
        } finally { $dlg.Dispose(); $form.Activate() }
    }.GetNewClosure())
    $destBrowse.Add_Click({
        $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
        try {
            $dlg.Description = 'Oberordner auswaehlen, in dem Harvester GOG Deutsch angelegt wird'
            $dlg.ShowNewFolderButton = $true
            if (Test-Path -LiteralPath $destBox.Text -PathType Container) { $dlg.SelectedPath = $destBox.Text }
            if ($dlg.ShowDialog($form) -eq [System.Windows.Forms.DialogResult]::OK) { $destBox.Text = $dlg.SelectedPath }
        } finally { $dlg.Dispose(); $form.Activate() }
    }.GetNewClosure())
    $install.Add_Click({
        try {
            if (-not (Test-Path -LiteralPath $sourceBox.Text -PathType Container)) { throw 'Der englische GOG-Ordner wurde nicht gefunden.' }
            foreach ($needed in @('HARVEST.EXE','HARVEST.DAT','HARVEST3.DAT','HARVEST4.DAT','DOSBOX\DOSBox.exe','dosbox_harvester_single.conf')) {
                if (-not (Test-Path -LiteralPath (Join-Path $sourceBox.Text $needed) -PathType Leaf)) { throw ('Im GOG-Quellordner fehlt: ' + $needed) }
            }
            if ([string]::IsNullOrWhiteSpace($destBox.Text)) { throw 'Bitte einen Speicherort fuer die deutsche Version auswaehlen.' }
            $par = [IO.Path]::GetFullPath($destBox.Text.Trim().Trim('"')).TrimEnd([char[]]'\/')
            if (-not (Test-Path -LiteralPath $par -PathType Container)) { throw 'Der Ziel-Speicherort existiert nicht. Bitte einen vorhandenen Ordner auswaehlen.' }
            $src = [IO.Path]::GetFullPath($sourceBox.Text.Trim().Trim('"')).TrimEnd([char[]]'\/')
            $dest = [IO.Path]::Combine($par, $finalName)
            if (Test-Path -LiteralPath $dest) { throw ('Der Zielordner existiert bereits: ' + $dest + '. Bitte einen anderen Speicherort waehlen.') }
            if ([string]::Equals($dest, $src, [StringComparison]::OrdinalIgnoreCase) -or $dest.StartsWith($src + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or $src.StartsWith($dest + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
                throw 'Quelle und Ziel duerfen nicht ineinander liegen. Bitte anderen Speicherort waehlen.'
            }
            $form.Tag = @{ Source = $src; Target = $dest }
            $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
            $form.Close()
        } catch {
            [void][System.Windows.Forms.MessageBox]::Show($form, $_.Exception.Message, 'Ordner pruefen', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)
            $form.Activate()
        }
    }.GetNewClosure())
    $form.Add_Shown({ $form.Activate(); $form.BringToFront(); $sourceBox.Focus() | Out-Null }.GetNewClosure())
    try {
        if ($form.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { return $null }
        return $form.Tag
    } finally { $form.Dispose() }
}

try {
    Start-Transcript -Path $log -ErrorAction Stop | Out-Null
    $transcript = $true
    Write-Host ''
    Write-Host 'HARVESTER GOG DEUTSCH - INSTALLATION' -ForegroundColor Cyan
    Write-Host 'Originale werden nicht veraendert; 3 Spielstarter mit gemeinsamem Speicherstand.'
    Write-Host ''
    foreach ($f in @('Regeln.xml', 'Harvester_Deutsch_Patcher.exe', 'VideoUntertitel\VideoManifest.xml', 'Quellcode\DeutschPatcher.cs', 'Quellcode\VideoInstaller.cs', 'Quellcode\VideoReleaseBridge.cs')) {
        if (-not (Test-Path -LiteralPath (Join-Path $package $f) -PathType Leaf)) { throw ('Installationspaket unvollstaendig: ' + $f) }
    }
    $detected = Find-GogOriginal
    if ($detected) { Write-Host ('GOG-Installation erkannt: ' + $detected) }
    else { Write-Host 'Registry-Pfad nicht gefunden oder ungueltig. Bitte Originalordner auswaehlen.' -ForegroundColor Yellow }
    $paths = Choose-Paths $detected
    if ($null -eq $paths) { Write-Host 'Installation abgebrochen. Es wurde nichts veraendert.'; exit 0 }
    $source = $paths.Source
    $target = $paths.Target
    Write-Host ('Quelle: ' + $source)
    Write-Host ('Ziel: ' + $target)
    if ([IO.Path]::GetFullPath($package).StartsWith($source + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Bitte das Installationspaket NICHT innerhalb des englischen GOG-Spieleordners entpacken.'
    }
    if (Test-Path -LiteralPath $target) { throw ('Ziel existiert bereits: ' + $target) }

    Write-Host '[1/4] Pruefe die Windows-.NET-Komponenten ...'
    $compilers = @(
        (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
        (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
    )
    $compiler = $compilers | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $compiler) { throw 'Der Windows-.NET-Framework-C#-Compiler fehlt. Bitte Windows-.NET-Framework 4.x aktivieren. Es wurde noch nichts installiert.' }
    $tmp = Join-Path $env:TEMP ('Harvester_GOG_Deutsch_' + [Guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($tmp) | Out-Null
    $dll = Join-Path $tmp 'HarvesterVideoRelease.dll'
    $csargs = @(
        '/nologo', '/target:library', '/platform:anycpu', ('/out:' + $dll),
        '/r:System.dll', '/r:System.Core.dll', '/r:System.Xml.dll', '/r:System.Windows.Forms.dll',
        (Join-Path $package 'Quellcode\DeutschPatcher.cs'),
        (Join-Path $package 'Quellcode\VideoInstaller.cs'),
        (Join-Path $package 'Quellcode\VideoReleaseBridge.cs')
    )
    & $compiler @csargs
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $dll)) { throw 'Die interne Windows-Hilfsroutine konnte nicht erstellt werden. Bitte Installationslog pruefen.' }
    Add-Type -Path $dll -ErrorAction Stop
    $count = [DeutschPatcher]::ReleasePreflight($package)
    if ($count -ne 196) { throw 'Unvollstaendiges Untertitelpaket' }
    Write-Host '[2/4] Untertitelpaket vollstaendig: 66 Filme, 196 CD-Positionen (10/11 px).'

    [int64]$originalBytes = 0
    Get-ChildItem -LiteralPath $source -Recurse -File -ErrorAction Stop | ForEach-Object { $originalBytes += [int64]$_.Length }
    [int64]$cdBytes = 0
    foreach ($cd in @('HARVEST.DAT', 'HARVEST3.DAT', 'HARVEST4.DAT')) { $cdBytes += [int64](Get-Item -LiteralPath (Join-Path $source $cd)).Length }
    [int64]$requiredBytes = $originalBytes + 7 * $cdBytes + [int64](2GB)
    $drive = New-Object System.IO.DriveInfo -ArgumentList ([IO.Path]::GetPathRoot($target))
    if ($drive.AvailableFreeSpace -lt $requiredBytes) {
        throw ('Zu wenig Speicher am Ziel. Frei: ' + [math]::Floor($drive.AvailableFreeSpace / 1GB) + ' GB; fuer sichere Installation benoetigt: ca. ' + [math]::Ceiling($requiredBytes / 1GB) + ' GB.')
    }
    Write-Host '[3/4] Installiere das unveraenderte deutsche FIX2-Spiel als neue Kopie ...'
    & (Join-Path $package 'Harvester_Deutsch_Patcher.exe') '--source' $source '--target' $target
    if ($LASTEXITCODE -ne 0) { throw ('FIX2 konnte die Spielkopie nicht fertigstellen (Exit ' + $LASTEXITCODE + ').') }
    if (-not (Test-Path -LiteralPath (Join-Path $target 'Deutsch_Pruefnachweis.xml') -PathType Leaf)) {
        throw 'FIX2 hat keinen erfolgreichen Installationsnachweis erstellt.'
    }
    $marker = Join-Path $target 'INSTALLATION_UNVOLLSTAENDIG.txt'
    'Untertitel-CD-Bau ist noch nicht fertig. Dieses Spiel bitte noch NICHT starten.' | Set-Content -LiteralPath $marker -Encoding UTF8
    Write-Host '[4/4] Erzeuge beide deutschen Untertitel-CD-Saetze und drei Spielstarter ...'
    [DeutschPatcher]::ReleaseCreateModes($package, $target)
    if (Test-Path -LiteralPath $marker) { Remove-Item -LiteralPath $marker -Force }
    @(
        'HARVESTER GOG DEUTSCH',
        '',
        'Starte das Spiel ueber genau eine dieser drei Dateien:',
        'Harvester_Deutsch_ohne_Videountertitel.cmd',
        'Harvester_Deutsch_mit_10px_Videountertiteln.cmd',
        'Harvester_Deutsch_mit_11px_Videountertiteln.cmd',
        '',
        'Alle drei nutzen dieselben deutschen Texte und denselben Spielstand-Ordner cloud_saves.',
        'Vor einem Wechsel zwischen 10px/11px/ohne das Spiel immer komplett beenden.',
        'Englisches GOG-Original und fruehere Testinstallationen bleiben unveraendert.'
    ) | Set-Content -LiteralPath (Join-Path $target 'LIES_MICH_SPIELSTART.txt') -Encoding UTF8
    Write-Host ''
    Write-Host 'INSTALLATION ERFOLGREICH' -ForegroundColor Green
    Write-Host ('Ordner: ' + $target)
    Write-Host 'Darin sind die drei deutschen Start-CMDs; gemeinsames cloud_saves-Verzeichnis.'
} catch {
    Write-Host ''
    Write-Host ('FEHLER: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host ('Installationslog: ' + $log)
    Write-Host 'Die englische GOG-Quelle wird von diesem Installer nur gelesen.'
    Write-Host 'Falls bereits ein neuer Zielordner existiert, kann er nach einem Abbruch unvollstaendig sein.'
    exit 1
} finally {
    if ($transcript) { try { Stop-Transcript | Out-Null } catch {} }
    if ($tmp -and (Test-Path -LiteralPath $tmp)) { try { Remove-Item -LiteralPath $tmp -Recurse -Force } catch {} }
}
exit 0
