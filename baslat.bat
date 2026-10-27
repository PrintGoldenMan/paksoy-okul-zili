@echo off
rem Okul Zili programini kaynak koddan baslatir (Python yuklu olmalidir).
cd /d "%~dp0"
if not exist .venv (
    echo Ilk calistirma: gerekli paketler yukleniyor...
    py -3 -m venv .venv || python -m venv .venv
    .venv\Scripts\python -m pip install --upgrade pip
    .venv\Scripts\python -m pip install -r requirements.txt
)
start "" .venv\Scripts\pythonw.exe main.py
