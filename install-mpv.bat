@echo off
setlocal

chcp 65001 >nul
title WMplayer mpv installer

echo.
echo WMplayer mpv installer
echo ------------------------
echo Step 1/4  Choose the Windows user install folder
echo Step 2/4  Download mpv from GitHub
echo Step 3/4  Install mpv for all apps used by this Windows user
echo Step 4/4  Add mpv to your user PATH
echo.
echo If this WMplayer folder already has an mpv folder, this installer will use that and skip downloading.
echo WMplayer folder:
echo   %~dp0
echo.
echo Default install folder:
echo   %%LOCALAPPDATA%%\Programs\mpv
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$bat='%~f0'; $root='%~dp0'; $tmp=Join-Path $env:TEMP ('wmplayer-install-mpv-' + [guid]::NewGuid().ToString('N') + '.ps1'); $raw=Get-Content -LiteralPath $bat -Raw; $marker='# POWERSHELL_PAYLOAD'; $i=$raw.LastIndexOf($marker); if ($i -lt 0) { Write-Error 'Installer payload is missing.'; exit 1 }; $payload=$raw.Substring($i + $marker.Length); Set-Content -LiteralPath $tmp -Value $payload -Encoding UTF8; try { & $tmp -ProjectRoot $root %*; exit $LASTEXITCODE } finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Finished. Open a new terminal, then run WMplayer.
) else (
    echo Install failed. Error code: %EXIT_CODE%
    echo.
    echo Common fixes:
    echo   1. Check your internet connection.
    echo   2. Install 7-Zip if Windows tar cannot extract the downloaded file.
    echo   3. Run this file again.
)
echo.
pause
exit /b %EXIT_CODE%

# POWERSHELL_PAYLOAD
param(
    [string]$ProjectRoot,
    [string]$InstallDir,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch {
}

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message"
}

function Split-PathEntries {
    param([string[]]$Entries)

    $result = @()
    foreach ($entry in $Entries) {
        if ([string]::IsNullOrWhiteSpace($entry)) {
            continue
        }
        $parts = [regex]::Split($entry.Trim(), '\s+(?=[A-Za-z]:\\|\\\\)')
        foreach ($part in $parts) {
            if (-not [string]::IsNullOrWhiteSpace($part)) {
                $result += $part.Trim()
            }
        }
    }
    $result
}

function Add-UserPath {
    param([string]$Directory)

    $resolved = [System.IO.Path]::GetFullPath($Directory).TrimEnd('\')
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $entries = @()
    if (-not [string]::IsNullOrWhiteSpace($userPath)) {
        $entries = $userPath -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    }
    $entries = Split-PathEntries $entries

    $keptEntries = @()
    $alreadyPresent = $false
    foreach ($entry in $entries) {
        $trimmed = $entry.Trim()
        if ([string]::Equals($trimmed.TrimEnd('\'), $resolved, [System.StringComparison]::OrdinalIgnoreCase)) {
            $alreadyPresent = $true
        } elseif ($trimmed.StartsWith($resolved, [System.StringComparison]::OrdinalIgnoreCase)) {
            $alreadyPresent = $true
            $tail = $trimmed.Substring($resolved.Length)
            if ($tail -match '^[A-Za-z]:\\|^\\\\') {
                $keptEntries += $tail
            }
        } else {
            $keptEntries += $trimmed
        }
    }

    $newPath = ((@($resolved) + $keptEntries) -join ';')
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    if ($alreadyPresent) {
        Write-Step "Moved to the front of user PATH: $resolved"
    } else {
        Write-Step "Added to the front of user PATH: $resolved"
    }

    $processEntries = $env:Path -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $processEntries = Split-PathEntries $processEntries
    $keptProcessEntries = @()
    foreach ($entry in $processEntries) {
        $trimmed = $entry.Trim()
        if ([string]::Equals($trimmed.TrimEnd('\'), $resolved, [System.StringComparison]::OrdinalIgnoreCase)) {
            continue
        }
        if ($trimmed.StartsWith($resolved, [System.StringComparison]::OrdinalIgnoreCase)) {
            $tail = $trimmed.Substring($resolved.Length)
            if ($tail -match '^[A-Za-z]:\\|^\\\\') {
                $keptProcessEntries += $tail
            }
        } else {
            $keptProcessEntries += $trimmed
        }
    }
    $env:Path = ((@($resolved) + $keptProcessEntries) -join ';')
}

function Get-MpvDownload {
    $headers = @{ "User-Agent" = "WMplayer-mpv-installer" }
    $fallbackUrl = "https://github.com/shinchiro/mpv-winbuild-cmake/releases/download/20260610/mpv-x86_64-20260610-git-304426c.7z"

    Write-Step "Finding mpv on GitHub"
    try {
        $latest = Invoke-WebRequest -Uri "https://github.com/shinchiro/mpv-winbuild-cmake/releases/latest" -Headers $headers -UseBasicParsing
        $latestUrl = $latest.BaseResponse.ResponseUri.AbsoluteUri
        $tag = Split-Path -Leaf $latestUrl
        if ([string]::IsNullOrWhiteSpace($tag) -or $tag -eq "latest") {
            throw "Could not read the latest release tag."
        }

        $assetsUrl = "https://github.com/shinchiro/mpv-winbuild-cmake/releases/expanded_assets/$tag"
        $assets = Invoke-WebRequest -Uri $assetsUrl -Headers $headers -UseBasicParsing
        $matches = [regex]::Matches($assets.Content, '/shinchiro/mpv-winbuild-cmake/releases/download/[^"'']+/mpv-x86_64-[^"'']+?\.7z')
        $assetPath = $null
        foreach ($match in $matches) {
            if ($match.Value -notmatch 'dev|v3') {
                $assetPath = $match.Value
                break
            }
        }

        if (-not $assetPath) {
            throw "Could not find a normal x86_64 release asset."
        }

        $downloadUrl = "https://github.com$assetPath"
        [pscustomobject]@{
            Name = [System.IO.Path]::GetFileName($downloadUrl)
            Url = $downloadUrl
        }
        return
    } catch {
        Write-Step "Could not read GitHub release page, using a known mpv download URL"
        [pscustomobject]@{
            Name = [System.IO.Path]::GetFileName($fallbackUrl)
            Url = $fallbackUrl
        }
    }
}

function Expand-MpvArchive {
    param(
        [string]$ArchivePath,
        [string]$Destination
    )

    $sevenZip = Get-Command 7z -ErrorAction SilentlyContinue
    if ($sevenZip) {
        Write-Step "Extracting with 7-Zip"
        & $sevenZip.Source x $ArchivePath "-o$Destination" -y | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return
        }
    }

    $tar = Get-Command tar -ErrorAction SilentlyContinue
    if ($tar) {
        Write-Step "Extracting with Windows tar"
        & $tar.Source -xf $ArchivePath -C $Destination
        if ($LASTEXITCODE -eq 0) {
            return
        }
    }

    throw "Could not extract the downloaded .7z file. Install 7-Zip, then run install-mpv.bat again."
}

if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $InstallDir = Join-Path $env:USERPROFILE "AppData\Local\Programs\mpv"
    } else {
        $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\mpv"
    }
}

$projectMpvDir = $null
if (-not [string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $projectPath = [System.IO.Path]::GetFullPath($ProjectRoot)
    $candidateDir = Join-Path $projectPath "mpv"
    $candidateExe = Join-Path $candidateDir "mpv.exe"
    $candidateCom = Join-Path $candidateDir "mpv.com"
    if ((Test-Path $candidateExe -PathType Leaf) -or (Test-Path $candidateCom -PathType Leaf)) {
        $projectMpvDir = $candidateDir
    }
}

if ($projectMpvDir -and -not $Force) {
    Write-Step "Found mpv in this WMplayer folder: $projectMpvDir"
    Add-UserPath $projectMpvDir
    $projectMpv = Join-Path $projectMpvDir "mpv.exe"
    if (-not (Test-Path $projectMpv -PathType Leaf)) {
        $projectMpv = Join-Path $projectMpvDir "mpv.com"
    }
    & $projectMpv --version
    exit 0
}

$installPath = [System.IO.Path]::GetFullPath($InstallDir)
$mpvExe = Join-Path $installPath "mpv.exe"
$mpvCom = Join-Path $installPath "mpv.com"

Write-Step "Install folder: $installPath"

if ((Test-Path $mpvExe -PathType Leaf) -or (Test-Path $mpvCom -PathType Leaf)) {
    if (-not $Force) {
        Write-Step "mpv is already installed: $installPath"
        Add-UserPath $installPath
        $localMpv = $mpvExe
        if (-not (Test-Path $localMpv -PathType Leaf)) {
            $localMpv = $mpvCom
        }
        & $localMpv --version
        exit 0
    }

    Write-Step "Replacing existing mpv: $installPath"
    Remove-Item -LiteralPath $installPath -Recurse -Force
}

$asset = Get-MpvDownload
Write-Step "Downloading $($asset.Name)"

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("wmplayer-mpv-" + [guid]::NewGuid().ToString("N"))
$archivePath = Join-Path $tempRoot $asset.Name
$extractPath = Join-Path $tempRoot "extract"
New-Item -ItemType Directory -Path $tempRoot, $extractPath -Force | Out-Null

try {
    Invoke-WebRequest -Uri $asset.Url -OutFile $archivePath -Headers @{ "User-Agent" = "WMplayer-mpv-installer" } -UseBasicParsing
    Expand-MpvArchive -ArchivePath $archivePath -Destination $extractPath

    $extractedMpv = Get-ChildItem -Path $extractPath -Filter "mpv.exe" -Recurse -File | Select-Object -First 1
    if (-not $extractedMpv) {
        throw "The downloaded archive did not contain mpv.exe."
    }

    $sourceDir = $extractedMpv.Directory.FullName
    New-Item -ItemType Directory -Path $installPath -Force | Out-Null
    Copy-Item -Path (Join-Path $sourceDir "*") -Destination $installPath -Recurse -Force
    Add-UserPath $installPath

    Write-Step "Installed mpv: $installPath"
    & (Join-Path $installPath "mpv.exe") --version
    exit 0
} finally {
    if (Test-Path $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
