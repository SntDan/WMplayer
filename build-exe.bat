@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Run this file yourself to close dist\WMplayer.exe and rebuild it.
pushd "%~dp0"
if errorlevel 1 exit /b 1

set "WMPLAYER_BUILD_EXE=%CD%\dist\WMplayer.exe"
set "WMPLAYER_PYTHON_ARGS="
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
echo [ERROR] Python was not found. Install Python or create a project virtual environment.
goto failed

:python_ready
if not exist "WMplayer.py" (
    echo [ERROR] WMplayer.py is missing. Keep this script in the project root.
    goto failed
)
"%WMPLAYER_PYTHON%" %WMPLAYER_PYTHON_ARGS% -c "import PyInstaller, PyQt6, mutagen, PIL, win32pipe" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Build dependencies are missing from the selected Python environment.
    echo Python: "%WMPLAYER_PYTHON%" %WMPLAYER_PYTHON_ARGS%
    echo Install with:
    echo   "%WMPLAYER_PYTHON%" %WMPLAYER_PYTHON_ARGS% -m pip install -r requirements.txt pyinstaller
    goto failed
)

echo [1/2] Closing "%WMPLAYER_BUILD_EXE%" if running...
rem Match the full executable path so other copies of WMplayer are untouched.
rem Ask all instances to close first; force their process trees only if needed.
powershell.exe -NoProfile -Command "$ErrorActionPreference = 'Stop'; try { $players = @(Get-Process -Name 'WMplayer' -ErrorAction SilentlyContinue | Where-Object { $_.Path -and [string]::Equals($_.Path, $env:WMPLAYER_BUILD_EXE, [System.StringComparison]::OrdinalIgnoreCase) }); foreach ($player in $players) { if (-not $player.HasExited) { $null = $player.CloseMainWindow() } }; foreach ($player in $players) { if (-not $player.HasExited -and -not $player.WaitForExit(5000)) { & taskkill.exe /PID $player.Id /T /F; if ($LASTEXITCODE -ne 0 -and -not $player.HasExited) { throw 'Could not stop WMplayer.' }; if (-not $player.WaitForExit(5000)) { throw 'WMplayer did not exit.' } } }; exit 0 } catch { Write-Error $_; exit 1 }"
if errorlevel 1 goto failed

echo [2/2] Building WMplayer.exe...
if exist "WMplayer.spec" (
    "%WMPLAYER_PYTHON%" %WMPLAYER_PYTHON_ARGS% -m PyInstaller --noconfirm --clean --distpath "%CD%\dist" --workpath "%CD%\build" "WMplayer.spec"
) else (
    "%WMPLAYER_PYTHON%" %WMPLAYER_PYTHON_ARGS% -m PyInstaller --noconfirm --clean --onefile --windowed --name WMplayer --icon "assets\wmplayer.ico" --add-data "assets\wmplayer.ico;assets" --distpath "%CD%\dist" --workpath "%CD%\build" "WMplayer.py"
)
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
