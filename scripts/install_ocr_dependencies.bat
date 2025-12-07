@echo off
REM ============================================================================
REM VAMP OCR Dependencies Installer
REM Installs Tesseract OCR, Poppler, and Python packages for offline app
REM ============================================================================

setlocal EnableDelayedExpansion

echo.
echo ============================================================================
echo VAMP OCR Dependencies Installer
echo ============================================================================
echo.
echo This script will install:
echo   1. Tesseract OCR (via Chocolatey or manual prompt)
echo   2. Poppler (for PDF to image conversion)
echo   3. Python packages: pytesseract, pillow, pdf2image
echo.
echo ============================================================================
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] This script requires administrator privileges.
    echo Please right-click and select "Run as Administrator"
    pause
    exit /b 1
)

echo [INFO] Administrator privileges confirmed.
echo.

REM ============================================================================
REM Step 1: Check/Install Chocolatey
REM ============================================================================

echo [STEP 1/4] Checking for Chocolatey package manager...
where choco >nul 2>&1
if %errorLevel% equ 0 (
    echo [OK] Chocolatey is already installed.
) else (
    echo [WARN] Chocolatey not found. Installing Chocolatey...
    echo.
    powershell -NoProfile -ExecutionPolicy Bypass -Command "[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"
    
    if !errorLevel! neq 0 (
        echo [ERROR] Chocolatey installation failed.
        echo Please install manually from: https://chocolatey.org/install
        pause
        exit /b 1
    )
    
    REM Refresh environment variables
    refreshenv
    echo [OK] Chocolatey installed successfully.
)
echo.

REM ============================================================================
REM Step 2: Install Tesseract OCR
REM ============================================================================

echo [STEP 2/4] Installing Tesseract OCR...
tesseract --version >nul 2>&1
if %errorLevel% equ 0 (
    echo [OK] Tesseract is already installed.
    tesseract --version
) else (
    echo [INFO] Installing Tesseract OCR via Chocolatey...
    choco install tesseract -y
    
    if !errorLevel! neq 0 (
        echo [ERROR] Tesseract installation failed.
        echo.
        echo Please install manually:
        echo 1. Download from: https://github.com/UB-Mannheim/tesseract/wiki
        echo 2. Run installer and select "Add to PATH"
        echo 3. Re-run this script
        pause
        exit /b 1
    )
    
    REM Refresh PATH
    set "PATH=%PATH%;C:\Program Files\Tesseract-OCR"
    echo [OK] Tesseract installed successfully.
)
echo.

REM ============================================================================
REM Step 3: Install Poppler (for pdf2image)
REM ============================================================================

echo [STEP 3/4] Installing Poppler...
where pdftoppm >nul 2>&1
if %errorLevel% equ 0 (
    echo [OK] Poppler is already installed.
) else (
    echo [INFO] Installing Poppler via Chocolatey...
    choco install poppler -y
    
    if !errorLevel! neq 0 (
        echo [WARN] Poppler installation via Chocolatey failed.
        echo.
        echo Please install manually:
        echo 1. Download from: https://github.com/oschwartz10612/poppler-windows/releases/
        echo 2. Extract and add bin\ folder to PATH
        echo.
        echo Note: pdf2image may still work without Poppler on some systems.
    ) else (
        echo [OK] Poppler installed successfully.
    )
)
echo.

REM ============================================================================
REM Step 4: Install Python Packages
REM ============================================================================

echo [STEP 4/4] Installing Python OCR packages...
echo.

REM Check if Python is available
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.8+ from: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [INFO] Python found:
python --version
echo.

REM Check if pip is available
pip --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] pip is not installed or not in PATH.
    echo Please reinstall Python with pip enabled.
    pause
    exit /b 1
)

echo [INFO] Installing pytesseract...
pip install pytesseract --quiet
if %errorLevel% neq 0 (
    echo [ERROR] Failed to install pytesseract
    pause
    exit /b 1
)
echo [OK] pytesseract installed.

echo [INFO] Installing pillow...
pip install pillow --quiet
if %errorLevel% neq 0 (
    echo [ERROR] Failed to install pillow
    pause
    exit /b 1
)
echo [OK] pillow installed.

echo [INFO] Installing pdf2image...
pip install pdf2image --quiet
if %errorLevel% neq 0 (
    echo [ERROR] Failed to install pdf2image
    pause
    exit /b 1
)
echo [OK] pdf2image installed.

echo.
echo ============================================================================
echo Installation Complete!
echo ============================================================================
echo.

REM ============================================================================
REM Verification
REM ============================================================================

echo [VERIFY] Running verification checks...
echo.

set "ERRORS=0"

REM Check Tesseract
tesseract --version >nul 2>&1
if %errorLevel% equ 0 (
    echo [OK] Tesseract: INSTALLED
    tesseract --version | findstr /C:"tesseract"
) else (
    echo [FAIL] Tesseract: NOT FOUND IN PATH
    set "ERRORS=1"
)

REM Check Python packages
echo.
echo [INFO] Checking Python packages...
python -c "import pytesseract; print('[OK] pytesseract version:', pytesseract.get_tesseract_version())" 2>nul
if %errorLevel% neq 0 (
    echo [FAIL] pytesseract: IMPORT ERROR
    set "ERRORS=1"
)

python -c "import PIL; print('[OK] pillow version:', PIL.__version__)" 2>nul
if %errorLevel% neq 0 (
    echo [FAIL] pillow: IMPORT ERROR
    set "ERRORS=1"
)

python -c "import pdf2image; print('[OK] pdf2image: INSTALLED')" 2>nul
if %errorLevel% neq 0 (
    echo [FAIL] pdf2image: IMPORT ERROR
    set "ERRORS=1"
)

echo.
echo ============================================================================

if %ERRORS% equ 0 (
    echo [SUCCESS] All dependencies installed successfully!
    echo.
    echo Next steps:
    echo   1. Close and reopen your terminal to refresh PATH
    echo   2. Run: python frontend/offline_app/offline_app.py
    echo   3. Scan a folder with PDFs
    echo   4. Check console for OCR messages like:
    echo      [OCR] Extracting text from scanned PDF: document.pdf
    echo.
    echo Full documentation: docs/OCR_SETUP.md
) else (
    echo [WARNING] Some dependencies failed verification.
    echo.
    echo Troubleshooting:
    echo   1. Close this terminal and open a NEW terminal as Administrator
    echo   2. Check PATH includes: C:\Program Files\Tesseract-OCR
    echo   3. Verify Python and pip are in PATH
    echo   4. Re-run this script
    echo.
    echo For manual installation steps, see: docs/OCR_SETUP.md
)

echo ============================================================================
echo.
pause
exit /b %ERRORS%
