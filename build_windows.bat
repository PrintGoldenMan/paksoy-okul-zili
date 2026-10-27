@echo off
rem Okul Zili programini tek bir OkulZili.exe dosyasina donusturur.
rem Gereken: Windows 10/11 ve Python 3.10 veya ustu (python.org).
cd /d "%~dp0"
py -3 -m venv .venv-build || python -m venv .venv-build
.venv-build\Scripts\python -m pip install --upgrade pip
.venv-build\Scripts\python -m pip install -r requirements.txt pyinstaller
.venv-build\Scripts\pyinstaller --noconfirm --onefile --windowed --name OkulZili ^
    --collect-data customtkinter ^
    --collect-all edge_tts ^
    --hidden-import pyttsx3.drivers ^
    --hidden-import pyttsx3.drivers.sapi5 ^
    main.py
echo.
echo Hazir: dist\OkulZili.exe
pause
