@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ============================================================================
rem TGPAssure - Build a single Windows EXE with the existing venv.
rem
rem REQUIRED FOLDER LAYOUT:
rem   MainFolder\
rem       BUILD_SINGLE_EXE.bat
rem       venv\
rem           Scripts\python.exe
rem       tgpassure\
rem           run_app.py
rem           TGPAssure_onefile.spec
rem           assets\logo\logo.ico
rem           ...rest of project...
rem
rem OUTPUT:
rem   MainFolder\dist\TGPAssure.exe
rem ============================================================================

set "ROOT=%~dp0"
set "VENV=%ROOT%venv"
set "APP=%ROOT%tgpassure"
set "PY=%VENV%\Scripts\python.exe"
set "SPEC=%APP%\TGPAssure_onefile.spec"
set "ICON=%APP%\assets\logo\logo.ico"
set "DIST=%ROOT%dist"
set "WORK=%ROOT%build"

cls
echo ============================================================
echo              TGPAssure SINGLE EXE BUILDER
echo ============================================================
echo.
echo Main folder : %ROOT%
echo Virtual env : %VENV%
echo Project     : %APP%
echo Output      : %DIST%\TGPAssure.exe
echo.

if not exist "%PY%" (
    echo [ERROR] Virtual environment Python was not found:
    echo         %PY%
    echo.
    echo Expected layout: MainFolder\venv and MainFolder\tgpassure
    goto :FAIL
)

if not exist "%APP%\run_app.py" (
    echo [ERROR] TGPAssure project was not found at:
    echo         %APP%
    goto :FAIL
)

if not exist "%SPEC%" (
    echo [ERROR] PyInstaller spec file was not found:
    echo         %SPEC%
    goto :FAIL
)

if not exist "%ICON%" (
    echo [ERROR] Application icon was not found:
    echo         %ICON%
    echo The EXE will not be built without the requested TGPAssure icon.
    goto :FAIL
)

rem Make sure Python itself starts correctly.
"%PY%" -c "import sys; print('[OK] Python:', sys.version); print('[OK] Interpreter:', sys.executable)"
if errorlevel 1 goto :FAIL

rem Validate the principal runtime dependencies before spending time on a build.
echo.
echo [1/5] Checking application dependencies...
"%PY%" -c "import PySide6, numpy, scipy, pyqtgraph, OpenGL, reportlab, openpyxl, PIL, shapefile, tifffile, ebcdic, psutil, matplotlib, qtawesome; print('[OK] Core runtime dependencies are importable.')"
if errorlevel 1 (
    echo.
    echo [ERROR] One or more TGPAssure dependencies are missing from venv.
    echo Install the project into the existing venv first, for example:
    echo   "%PY%" -m pip install -e "%APP%"
    goto :FAIL
)

rem Install PyInstaller only when it is not already available in this venv.
echo.
echo [2/5] Checking PyInstaller...
"%PY%" -c "import PyInstaller; print('[OK] PyInstaller', PyInstaller.__version__)" >nul 2>&1
if errorlevel 1 (
    echo PyInstaller is not installed in this venv. Installing build tools...
    "%PY%" -m pip install "pyinstaller>=6.16,<7" "pyinstaller-hooks-contrib>=2025.8"
    if errorlevel 1 goto :FAIL
) else (
    "%PY%" -c "import PyInstaller; print('[OK] PyInstaller', PyInstaller.__version__)"
)

rem Compile-check project source before freezing it.
echo.
echo [3/5] Checking Python source...
"%PY%" -m compileall -q "%APP%"
if errorlevel 1 (
    echo [ERROR] Python compilation check failed. Fix source errors before packaging.
    goto :FAIL
)
echo [OK] Source compilation passed.

rem Clean only generated packaging folders. User/project data are untouched.
echo.
echo [4/5] Cleaning old build output...
if exist "%WORK%" rmdir /s /q "%WORK%"
if exist "%DIST%" rmdir /s /q "%DIST%"
mkdir "%WORK%" >nul 2>&1
mkdir "%DIST%" >nul 2>&1

rem Build from the spec. PyInstaller must run on Windows to create a Windows EXE.
echo.
echo [5/5] Building one-file TGPAssure.exe...
pushd "%APP%"
"%PY%" -m PyInstaller --noconfirm --clean --distpath "%DIST%" --workpath "%WORK%" "%SPEC%"
set "BUILD_RC=%ERRORLEVEL%"
popd

if not "%BUILD_RC%"=="0" (
    echo.
    echo [ERROR] PyInstaller failed with exit code %BUILD_RC%.
    goto :FAIL
)

if not exist "%DIST%\TGPAssure.exe" (
    echo [ERROR] Build completed without producing the expected EXE.
    goto :FAIL
)

for %%F in ("%DIST%\TGPAssure.exe") do set "EXE_SIZE=%%~zF"
set /a EXE_MB=!EXE_SIZE!/1048576

echo.
echo ============================================================
echo BUILD SUCCESSFUL
echo ============================================================
echo EXE: %DIST%\TGPAssure.exe
echo Approx size: !EXE_MB! MB
echo.
echo The end user only needs TGPAssure.exe to launch the application.
echo One-file startup can take a few seconds because bundled files are unpacked
rem by the PyInstaller bootloader into a temporary runtime directory.
echo.
start "" "%DIST%"
exit /b 0

:FAIL
echo.
echo ============================================================
echo BUILD FAILED
echo ============================================================
echo Review the error above. No source files were deleted.
echo.
pause
exit /b 1
