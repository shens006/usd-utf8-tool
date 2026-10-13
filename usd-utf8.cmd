@echo off
rem Source-checkout launcher. No automatic downloads or installs.
if exist "%~dp0.venv\Scripts\python.exe" goto local
where py >nul 2>&1
if not errorlevel 1 goto pylauncher
where python >nul 2>&1
if not errorlevel 1 goto python
:missing
echo Python not found. Install 64-bit Python 3.12: https://www.python.org/downloads/ 1>&2
echo See INSTALL.md, then run usd-utf8.cmd doctor again. 1>&2
exit /b 2
:local
"%~dp0.venv\Scripts\python.exe" "%~dp0usd_cli.py" %*
exit /b %errorlevel%
:pylauncher
py -3.12 -c "import sys" >nul 2>&1
if errorlevel 1 goto pydefault
py -3.12 "%~dp0usd_cli.py" %*
exit /b %errorlevel%
:pydefault
py -3 -c "import sys" >nul 2>&1
if errorlevel 1 goto missing
py -3 "%~dp0usd_cli.py" %*
exit /b %errorlevel%
:python
python -c "import sys" >nul 2>&1
if errorlevel 1 goto missing
python "%~dp0usd_cli.py" %*
exit /b %errorlevel%
