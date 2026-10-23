@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Run this script yourself. Build the current checkout, ignoring old root specs.
pushd "%~dp0"
if errorlevel 1 exit /b 1

set "WMPLAYER_BUILD_EXE=%CD%\dist\WMplayer.exe"
set "WMPLAYER_BUILD_SOURCE=%CD%\WMplayer.py"
set "WMPLAYER_SPEC_DIR=%CD%\build\spec"
set "WMPLAYER_PYTHON_ARGS="

echo [1/3] Checking source files and Python dependencies...
if not exist "WMplayer.py" (
    echo [ERROR] WMplayer.py is missing. Keep this script in the project root.
    goto failed
)
if not exist "assets\wmplayer.ico" (
    echo [ERROR] assets\wmplayer.ico is missing. Restore the app icon before building.
    goto failed
)
if exist ".venv\Scripts\python.exe" (
    set "WMPLAYER_PYTHON=%CD%\.venv\Scripts\python.exe"
    goto python_ready
)
if exist "venv\Scripts\python.exe" (
    set "WMPLAYER_PYTHON=%CD%\venv\Scripts\python.exe"
    goto python_ready
)
where python >nul 2>nul
if not errorlevel 1 (
    set "WMPLAYER_PYTHON=python"
    goto python_ready
)
where py >nul 2>nul
if not errorlevel 1 (
    set "WMPLAYER_PYTHON=py"
    set "WMPLAYER_PYTHON_ARGS=-3"
    goto python_ready
)
echo [ERROR] Python was not found. Install Python 3.10 or newer.
goto failed

:python_ready
echo Python: "%WMPLAYER_PYTHON%" %WMPLAYER_PYTHON_ARGS%
"%WMPLAYER_PYTHON%" %WMPLAYER_PYTHON_ARGS% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo [ERROR] The selected Python must be version 3.10 or newer.
    goto failed
)
"%WMPLAYER_PYTHON%" %WMPLAYER_PYTHON_ARGS% -c "import PyInstaller, PyQt6.QtWidgets, mutagen, PIL, win32pipe; from winrt.windows.media.interop import get_for_window; from winrt.windows.storage.streams import DataWriter; from winrt.windows.foundation import Uri"
if errorlevel 1 (
    echo [ERROR] Build dependencies are missing or cannot be loaded.
    echo Install them in the selected Python environment:
    echo   "%WMPLAYER_PYTHON%" %WMPLAYER_PYTHON_ARGS% -m pip install -r requirements.txt pyinstaller
    goto failed
)
where powershell.exe >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Windows PowerShell was not found.
    goto failed
)
if not exist "%WMPLAYER_SPEC_DIR%\" mkdir "%WMPLAYER_SPEC_DIR%"
if not exist "%WMPLAYER_SPEC_DIR%\" (
    echo [ERROR] Could not create "%WMPLAYER_SPEC_DIR%".
    goto failed
)

echo [2/3] Closing running instances from this project...
rem Match this project's executable or Python entry point, including pythonw.
rem Ask all instances to close first; force their process trees only if needed.
powershell.exe -NoProfile -NonInteractive -Command ^
    "$ErrorActionPreference = 'Stop'; try {" ^
    "$source = '(?:' + [regex]::Escape($env:WMPLAYER_BUILD_SOURCE) + '|' + [regex]::Escape($env:WMPLAYER_BUILD_SOURCE.Replace('\', '/')) + ')';" ^
    "$sourcePattern = '^\s*(?:\x22[^\x22]+\x22|\S+)\s+(?:-[uOBEsI]+\s+)*(?:\x22' + $source + '\x22|' + $source + ')(?:\s|$)';" ^
    "$targets = @(Get-CimInstance Win32_Process | Where-Object { ($_.Name -ieq 'WMplayer.exe' -and [string]::Equals($_.ExecutablePath, $env:WMPLAYER_BUILD_EXE, [System.StringComparison]::OrdinalIgnoreCase)) -or ($_.Name -match '^python(?:\d+(?:\.\d+)?)?w?\.exe$' -and $_.CommandLine -match $sourcePattern) });" ^
    "$players = @($targets | ForEach-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue });" ^
    "foreach ($player in $players) { if (-not $player.HasExited) { Write-Host ('Closing ' + $player.ProcessName + ' (PID ' + $player.Id + ')'); $null = $player.CloseMainWindow() } };" ^
    "foreach ($player in $players) { if (-not $player.HasExited -and -not $player.WaitForExit(5000)) { & taskkill.exe /PID $player.Id /T /F; if ($LASTEXITCODE -ne 0 -and -not $player.HasExited) { throw 'Could not stop WMplayer.' }; if (-not $player.WaitForExit(5000)) { throw 'WMplayer did not exit.' } } };" ^
    "exit 0 } catch { Write-Error $_; exit 1 }"
if errorlevel 1 goto failed

echo [3/3] Building the current checkout with the app icon...
rem Always generate a fresh spec under build\spec. Never consume WMplayer.spec.
"%WMPLAYER_PYTHON%" %WMPLAYER_PYTHON_ARGS% -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name WMplayer ^
    --icon "%CD%\assets\wmplayer.ico" ^
    --add-data "%CD%\assets\wmplayer.ico;assets" ^
    --specpath "%WMPLAYER_SPEC_DIR%" ^
    --distpath "%CD%\dist" ^
    --workpath "%CD%\build\pyinstaller" ^
    "%CD%\WMplayer.py"
if errorlevel 1 goto failed
if not exist "%WMPLAYER_BUILD_EXE%" (
    echo [ERROR] PyInstaller finished but the expected executable is missing.
    goto failed
)

echo.
echo [OK] Built: "%WMPLAYER_BUILD_EXE%"
popd
pause
exit /b 0

:failed
echo.
echo [ERROR] Build stopped. See the message above.
popd
pause
exit /b 1
