@echo off
rem Double-click to start BillSaathi. Looks for Python in the usual places.
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw gui.py & exit /b)
where py >nul 2>nul && (py -3 -c "import sys" >nul 2>nul && (start "" pyw -3 gui.py & exit /b))
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python3*\pythonw.exe" "C:\Program Files\Python3*\pythonw.exe") do (
  if exist "%%~fP" (start "" "%%~fP" gui.py & exit /b)
)
echo Python 3.10 or newer was not found. Install it from https://www.python.org/downloads/ and tick "Add to PATH".
pause
