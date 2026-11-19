# Rebuild Harvester GOG Deutsch from public sources/resources on Windows.
# No original game files or saved games are accessed by this build.
param([switch]$CI)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$src = Join-Path $root 'source'
$res = Join-Path $root 'resources/payload'
$delta = Join-Path $root 'resources/delta/Harvester_GOG_Deutsch_Delta_v1.0.0.zip'
$stage = Join-Path $root 'public_build_stage'
$output = Join-Path $root 'public_build_output'
$expectedDelta = 'e690300e4d858992c140d00eceee1ef9e6a4911f32faf98ed7feba93f5794768'
$expectedNative = '9b8fada91a55db9c069309deb69137277cc951b154781523f7571c704f7a62e0'
$expectedRules = '7c72b55366546080544d603fbe4f24aa128d80c043a56cad36db4db40327266b'

function Need-File([string]$file) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "File missing: $file" }
}
function Exact-Sha([string]$file, [string]$expected) {
    Need-File $file
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash.ToLowerInvariant()
    if ($actual -cne $expected) { throw "SHA-256 mismatch: $file" }
}

try {
    if (-not (Test-Path -LiteralPath $src -PathType Container)) { throw 'Source folder missing' }
    if (-not (Test-Path -LiteralPath $res -PathType Container)) { throw 'Public payload folder missing' }
    if (Test-Path -LiteralPath $stage) { throw 'Existing public_build_stage must not be overwritten' }
    if (Test-Path -LiteralPath $output) { throw 'Existing public_build_output must not be overwritten' }
    Exact-Sha $delta $expectedDelta
    Exact-Sha (Join-Path $res 'Harvester_Deutsch_Patcher.exe') $expectedNative
    Exact-Sha (Join-Path $res 'Regeln.xml') $expectedRules
    Need-File (Join-Path $res 'VideoManifest.xml')
    Need-File (Join-Path $root 'release/LIES_MICH.txt')
    Write-Host 'Public source and translation resource SHA-256 checks PASS' -ForegroundColor Green
    New-Item -ItemType Directory -Path $stage -ErrorAction Stop | Out-Null
    Copy-Item -LiteralPath $src -Destination (Join-Path $stage 'source') -Recurse -ErrorAction Stop
    $copyRoot = Join-Path $stage 'source'
    Copy-Item -LiteralPath $res -Destination (Join-Path $copyRoot 'payload') -Recurse -ErrorAction Stop
    New-Item -ItemType Directory -Path (Join-Path $copyRoot 'release') -ErrorAction Stop | Out-Null
    Copy-Item -LiteralPath (Join-Path $root 'release/LIES_MICH.txt') -Destination (Join-Path $copyRoot 'release/LIES_MICH.txt') -ErrorAction Stop
    $build = Join-Path $copyRoot 'tools/developer/build_release_private.ps1'
    Need-File $build
    if ($CI) {
        # GitHub Actions has already installed Python 3.13 and requirements.
        & $build -DeltaZipPath $delta -CI
    } else {
        # Local interactive build requests permission to install its build deps.
        & $build -DeltaZipPath $delta
    }
    if ($LASTEXITCODE -ne 0) { throw "Windows setup builder reported exit code $LASTEXITCODE" }
    $built = Join-Path $copyRoot 'private_release_output/Harvester_GOG_Deutsch_v1.0.0.zip'
    Need-File $built
    New-Item -ItemType Directory -Path $output -ErrorAction Stop | Out-Null
    Copy-Item -LiteralPath $built -Destination (Join-Path $output 'Harvester_GOG_Deutsch_v1.0.0.zip') -ErrorAction Stop
    Write-Host 'PASS: independent Windows ZIP built from public code and translation resources.' -ForegroundColor Green
    Write-Host ('Output: ' + (Join-Path $output 'Harvester_GOG_Deutsch_v1.0.0.zip'))
    Write-Host 'No GOG originals were accessed; this new build is NOT the previously user-tested release binary.'
} catch {
    Write-Error ('Public rebuild failed: ' + $_.Exception.Message)
    exit 2
}
