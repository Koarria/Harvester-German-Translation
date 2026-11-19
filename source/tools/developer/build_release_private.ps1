# One-file Harvester build: locally interactive OR noninteractive in a PRIVATE GitHub Action.
# No GOG game files are read; the private delta is never published.
param(
    [string]$DeltaZipPath = '',
    [switch]$CI
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$dist = Join-Path $root 'private_release_dist'
$work = Join-Path $root 'private_release_work'
$stage = Join-Path $root 'private_release_stage'
$stageCreated = $false
$name = 'Harvester_GOG_Deutsch_Setup'
$outputRoot = Join-Path $root 'private_release_output'
$releaseFolder = Join-Path $outputRoot 'Harvester_GOG_Deutsch_v1.0.0'
$releaseZip = Join-Path $outputRoot 'Harvester_GOG_Deutsch_v1.0.0.zip'
$exe = Join-Path $dist ($name + '.exe')

function Check-Exit([string]$operation) {
    if ($LASTEXITCODE -ne 0) {
        throw "$operation fehlgeschlagen (Exit $LASTEXITCODE). Keine Spielinstallation gestartet."
    }
}

try {
    Write-Host 'HARVESTER GOG DEUTSCH - PRIVATES RELEASE-ZIP ERSTELLEN' -ForegroundColor Cyan
    Write-Host 'Das Originalspiel und die Spielstaende werden nicht angeruehrt.'
    if ($CI) {
        Write-Host 'Private GitHub-Actions-Variante: Delta-ZIP stammt aus genau diesem privaten Repository.'
        Write-Host 'Nur das erstellte ZIP wird als PRIVATES Build-Artefakt hochgeladen, kein GitHub Release.'
    } else {
        Write-Host 'Lokale Variante: Delta-ZIP bleibt auf diesem PC; keine Dateien werden hochgeladen.'
    }
    Write-Host ''
    foreach ($f in @('tools/developer/delta_onepass_installer.py',
                     'tools/developer/delta_embedded_bundle.py',
                     'tools/developer/delta_core_proof.py',
                     'payload/Regeln.xml', 'payload/VideoManifest.xml',
                     'payload/Harvester_Deutsch_Patcher.exe',
                     'requirements-build.txt',
                     'release/LIES_MICH.txt',
                     'tools/developer/release_package_audit.py')) {
        if (-not (Test-Path -LiteralPath (Join-Path $root $f) -PathType Leaf)) {
            throw "Datei fehlt: $f. Vollstaendigen privaten Ein-Datei-Branch entpacken."
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $root 'payload/subtitles') -PathType Container)) {
        throw 'Untertitelverzeichnis fehlt'
    }
    if (Test-Path -LiteralPath $exe) {
        throw "Vorhandene private EXE nicht ueberschreiben: $exe"
    }
    if (Test-Path -LiteralPath $stage) {
        throw "Vorhandenen privaten Staging-Ordner nicht ueberschreiben: $stage"
    }
    if (Test-Path -LiteralPath $outputRoot) {
        throw "Vorhandene Release-Ausgaben nicht ueberschreiben: $outputRoot"
    }

    $raw = $DeltaZipPath
    if ([string]::IsNullOrWhiteSpace($raw)) {
        if ($CI) {
            throw 'CI-Bau abgebrochen: DeltaZipPath fehlt. Kein Download-Paket erzeugt.'
        }
        $raw = Read-Host 'Vollstaendigen lokalen Pfad zur privaten Delta-Bundle-ZIP eingeben'
    }
    $pathText = $raw.Trim().Trim('"')
    if (-not $pathText) { throw 'Kein privates Delta-ZIP angegeben' }
    $zipPath = (Resolve-Path -LiteralPath $pathText -ErrorAction Stop).Path
    $zipItem = Get-Item -LiteralPath $zipPath -ErrorAction Stop
    if ($zipItem.PSIsContainer -or $zipItem.Length -le 0 -or $zipItem.Length -gt 20MB) {
        throw 'Das private Delta-ZIP muss eine Datei bis maximal 20 MiB sein'
    }
    if ($zipItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Das lokale Delta-ZIP darf kein Link/Junction sein'
    }
    # GitHub Actions uses the exact Python 3.13 chosen by actions/setup-python.
    # Interactive local builders keep the already tested Windows py launcher.
    $python = if ($CI) { 'python' } else { 'py' }
    $pythonPrefix = if ($CI) { @() } else { @('-3.13') }
    if (-not (Get-Command $python -ErrorAction SilentlyContinue)) {
        throw 'Python 3.13 zum privaten EXE-Bau ist nicht vorhanden'
    }
    & $python @pythonPrefix -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3,13) else 2)'
    Check-Exit 'Python 3.13'
    if (-not $CI) {
        $permission = Read-Host 'Python-Baupakete aus requirements-build.txt bei Bedarf installieren? JA'
        if ($permission -cne 'JA') { throw 'Keine Zustimmung zur Baupaketpruefung' }
        & $python @pythonPrefix -m pip install -r (Join-Path $root 'requirements-build.txt')
        Check-Exit 'Baupakete'
    } else {
        # Requirements were installed by the private workflow from the
        # checked-in requirements file. Never use Read-Host in automated CI.
        & $python @pythonPrefix -m PyInstaller --version
        Check-Exit 'CI-Baupakete'
    }

    Push-Location $root
    try {
        Write-Host '1/5: Synthetische Sicherheits- und Pfadtests' -ForegroundColor Cyan
        foreach ($pattern in @('test_delta_core_proof.py',
                               'test_delta_embedded_bundle.py',
                               'test_delta_onepass_installer.py',
                               'test_delta_onepass_wizard.py',
                               'test_release_package_audit.py')) {
            & $python @pythonPrefix -m unittest discover -s tools/developer -p $pattern -v
            Check-Exit "Testserie $pattern"
        }

        Write-Host '2/5: Lokales Delta-ZIP fuer privaten EXE-Bau vorbereiten' -ForegroundColor Cyan
        New-Item -ItemType Directory -Path $stage -ErrorAction Stop | Out-Null
        $stageCreated = $true
        $stageZip = Join-Path $stage 'delta.bundle.zip'
        $stageHash = Join-Path $stage 'delta.bundle.sha256'
        Copy-Item -LiteralPath $zipPath -Destination $stageZip -ErrorAction Stop
        $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash.ToLowerInvariant()
        $stagedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $stageZip).Hash.ToLowerInvariant()
        if ($sourceHash -cne $stagedHash) {
            throw 'STOPP: kopiertes Delta stimmt nicht mit privatem ZIP ueberein'
        }
        [IO.File]::WriteAllText($stageHash, ($sourceHash + [char]10), [Text.Encoding]::ASCII)
        New-Item -ItemType Directory -Force -Path $work | Out-Null

        Write-Host '3/5: Separate Python-freie EXE mit eingebautem Delta erzeugen' -ForegroundColor Cyan
        $buildArgs = @(
            '--noconfirm', '--clean', '--onefile', '--console',
            '--name', $name,
            '--paths', 'tools/developer',
            '--distpath', $dist, '--workpath', $work,
            '--add-data', 'payload/Regeln.xml;payload',
            '--add-data', 'payload/VideoManifest.xml;payload',
            '--add-data', 'payload/Harvester_Deutsch_Patcher.exe;payload',
            '--add-data', 'payload/subtitles;payload/subtitles',
            '--add-data', ($stageZip + ';private_embedded'),
            '--add-data', ($stageHash + ';private_embedded'),
            'tools/developer/delta_onepass_installer.py'
        )
        & $python @pythonPrefix -m PyInstaller @buildArgs
        Check-Exit 'EXE-Bau'
        if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
            throw 'Private EXE wurde nicht erzeugt'
        }

        Write-Host '4/5: Frozen-Selbsttests und Archivkontrolle' -ForegroundColor Cyan
        & $exe --packaged-preflight
        Check-Exit 'EXE-Preflight'
        & $exe --embedded-bundle-preflight
        Check-Exit 'Eingebautes Delta'
        & $exe --wizard-module-preflight
        Check-Exit 'Wizard-Modul'
        $inventory = & $python @pythonPrefix -m PyInstaller.utils.cliutils.archive_viewer -l -r $exe
        Check-Exit 'EXE-Archivpruefung'
        if ($inventory | Select-String -Pattern 'payload[/\\]Daten') {
            throw 'STOPP: Vollstaendige FIX2-Dateien im EXE-Archiv'
        }
        if ($inventory | Select-String -Pattern 'test_(delta_|release_|unified_delta|originalvergleich_gog)') {
            throw 'STOPP: Entwicklungs- oder Testmodul in der Spieler-EXE gefunden'
        }
        if (-not ($inventory | Select-String -SimpleMatch 'delta_embedded_bundle')) {
            throw 'STOPP: Privates Einbau-Modul fehlt im EXE-Archiv'
        }
        Write-Host '5/5: Sauberes Release-ZIP ausschliesslich aus drei Dateien herstellen' -ForegroundColor Cyan
        New-Item -ItemType Directory -Path $outputRoot -ErrorAction Stop | Out-Null
        New-Item -ItemType Directory -Path $releaseFolder -ErrorAction Stop | Out-Null
        Copy-Item -LiteralPath $exe -Destination (Join-Path $releaseFolder ($name + '.exe')) -ErrorAction Stop
        Copy-Item -LiteralPath (Join-Path $root 'release/LIES_MICH.txt') -Destination (Join-Path $releaseFolder 'LIES_MICH.txt') -ErrorAction Stop
        $finalSha = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $releaseFolder ($name + '.exe'))).Hash.ToLowerInvariant()
        [IO.File]::WriteAllText(
            (Join-Path $releaseFolder 'SHA256SUMS.txt'),
            ($finalSha + '  ' + $name + '.exe' + [char]10),
            [Text.Encoding]::ASCII
        )
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::CreateFromDirectory(
            $releaseFolder, $releaseZip,
            [IO.Compression.CompressionLevel]::Optimal, $false
        )
        & $python @pythonPrefix tools/developer/release_package_audit.py --folder $releaseFolder --zip $releaseZip
        Check-Exit 'Strenge Release-ZIP-Pruefung (nur EXE, Anleitung, SHA)'
        Write-Host ''
        Write-Host 'PASS: Sauberes lokales Release-ZIP mit genau 3 Dateien.' -ForegroundColor Green
        Write-Host "Paket: $releaseZip"
        Write-Host "EXE SHA-256: $finalSha"
        if ($CI) {
            Write-Host 'PRIVATE CI BAU PASS. Das ZIP darf NUR als privates Actions-Artefakt abgelegt werden.'
        } else {
            Write-Host 'WICHTIG: Keine oeffentliche Freigabe oder Upload durch diesen lokalen Bau.'
        }
    } finally {
        Pop-Location
    }
} catch {
    Write-Host ''
    Write-Host ("ABBRUCH: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Original-GOG, RC3b und Spielstaende wurden vom Bauvorgang nicht angefasst.'
    exit 2
} finally {
    if ($stageCreated -and (Test-Path -LiteralPath $stage)) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}
