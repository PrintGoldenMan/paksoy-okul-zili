@echo off
rem Okul Zili programini tek bir OkulZili.exe dosyasina donusturur.
rem Gereken: Windows 10/11 ve Python 3.10 veya ustu (python.org).
cd /d "%~dp0"
if not exist .venv-build (
    py -3 -m venv .venv-build || python -m venv .venv-build
)
if not exist .venv-build\Scripts\python.exe goto :python_yok
.venv-build\Scripts\python -m pip install --upgrade pip
.venv-build\Scripts\python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :hata
.venv-build\Scripts\pyinstaller --noconfirm --onefile --windowed --name OkulZili ^
    --icon assets\okul_zili.ico --add-data "assets;assets" ^
    --collect-data customtkinter ^
    --collect-all edge_tts ^
    --collect-all yt_dlp --collect-all yt_dlp_ejs --collect-all imageio_ffmpeg --copy-metadata yt-dlp ^
    --collect-submodules pyttsx3 ^
    --collect-submodules comtypes ^
    --hidden-import comtypes.stream ^
    --hidden-import win32com.client ^
    --hidden-import pythoncom ^
    main.py
if errorlevel 1 goto :hata
echo.
echo Hazir: dist\OkulZili.exe
pause
exit /b 0

:python_yok
echo HATA: Python bulunamadi. python.org adresinden Python 3.10 veya ustunu kurun
echo (kurulumda "Add Python to PATH" kutusunu isaretleyin).
pause
exit /b 1

:hata
echo.
echo HATA: Derleme basarisiz oldu. Yukaridaki mesajlari kontrol edin.
pause
exit /b 1
