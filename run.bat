@echo off
setlocal enabledelayedexpansion
set PORT=%1
if "%PORT%"=="" set PORT=8503
set ADDRESS=0.0.0.0
set PAGE=streamlit-demos\Home.py

cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  py -3.12 -m venv .venv
)

set PY=.venv\Scripts\python.exe
"%PY%" -m pip install --upgrade pip setuptools wheel
"%PY%" -m pip install -r requirements.txt

echo Launching Streamlit on %ADDRESS%:%PORT%
"%PY%" -m streamlit run %PAGE% --server.address %ADDRESS% --server.port %PORT%


