@echo off
REM ============================================================
REM  HIHO MOCAP - One-Click Python Environment Setup (Windows)
REM  Double-click this file. If Windows warns you, click
REM  "More info" then "Run anyway".
REM ============================================================
title HIHO Mocap Setup
echo.
echo === HIHO Mocap - Python Environment Setup ===
echo.
echo This will take a few minutes. Leave this window open.
echo.

REM --- Step 1: install uv if it isn't already installed ---
where uv >nul 2>&1
if errorlevel 1 (
    if exist "%USERPROFILE%\.local\bin\uv.exe" (
        echo [1/3] uv already installed - skipping.
    ) else (
        echo [1/3] Installing uv - Python environment manager...
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    )
) else (
    echo [1/3] uv already installed - skipping.
)
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

REM --- Step 2: create the environment with Python 3.11 ---
echo.
echo [2/3] Creating Python 3.11 environment at %USERPROFILE%\freemocap-env ...
uv venv "%USERPROFILE%\freemocap-env" --python 3.11
if errorlevel 1 goto :failed

REM --- Step 3: install FreeMoCap ---
echo.
echo [3/3] Installing FreeMoCap - this is the slow part, be patient...
uv pip install --python "%USERPROFILE%\freemocap-env\Scripts\python.exe" "freemocap==1.8.2"
if errorlevel 1 goto :failed

REM --- Done ---
echo.
echo ============================================================
echo   DONE!
echo.
echo   Now open Blender and go to:
echo   Edit ^> Preferences ^> Add-ons ^> HIHO Mocap
echo.
echo   Set 'FreeMoCap environment' to:
echo.
echo   %USERPROFILE%\freemocap-env\Scripts\python.exe
echo.
echo   (The path above is copied to your clipboard already.)
echo ============================================================
echo.
echo %USERPROFILE%\freemocap-env\Scripts\python.exe| clip
pause
exit /b 0

:failed
echo.
echo ============================================================
echo   Something went wrong. Take a screenshot of this window
echo   and post it on the Discord - that's exactly the kind of
echo   bug report we need!
echo ============================================================
pause
exit /b 1
