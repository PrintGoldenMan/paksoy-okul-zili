@echo off
rem Okul Zili programini kaynak koddan baslatir (Python yuklu olmalidir).
cd /d "%~dp0"
rem Kurulum basariyla bittiginde .venv\kurulum_tamam dosyasi olusur; yoksa kurulum yeniden denenir.
if not exist .venv\kurulum_tamam (
    echo Gerekli paketler yukleniyor, lutfen bekleyin...
    if not exist .venv (
        py -3 -m venv .venv || python -m venv .venv
    )
    if not exist .venv\Scripts\python.exe (
        echo HATA: Python bulunamadi. python.org adresinden Python 3.10 veya ustunu kurun.
        pause
        exit /b 1
    )
    .venv\Scripts\python -m pip install --upgrade pip
    .venv\Scripts\python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo HATA: Paketler yuklenemedi. Internet baglantisini kontrol edip tekrar deneyin.
        pause
        exit /b 1
    )
    echo ok> .venv\kurulum_tamam
)
start "" .venv\Scripts\pythonw.exe main.py
