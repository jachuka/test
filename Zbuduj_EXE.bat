@echo off
setlocal
cd /d "%~dp0"
echo Budowanie kalkulatora formatek dla Windows...
py -3 --version >nul 2>&1
if errorlevel 1 (
  echo Zainstaluj Python z https://www.python.org/downloads/windows/
  echo W instalatorze pozostaw wlaczone Tcl/Tk oraz Python Launcher.
  goto :failure
)
if not exist ".venv-build\Scripts\python.exe" (
  py -3 -m venv .venv-build
  if errorlevel 1 goto :failure
)
".venv-build\Scripts\python.exe" -c "import tkinter; t=tkinter.Tk(); t.withdraw(); t.destroy()"
if errorlevel 1 goto :failure
".venv-build\Scripts\python.exe" --version
".venv-build\Scripts\python.exe" -m pip install "PyInstaller==6.22.3" -r requirements.txt
if errorlevel 1 goto :failure
".venv-build\Scripts\python.exe" -m unittest -v
if errorlevel 1 goto :failure
".venv-build\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name KalkulatorFormatek app.py
if errorlevel 1 goto :failure
echo.
echo Gotowe! Aplikacja: dist\KalkulatorFormatek.exe
echo Ten plik mozna przeniesc na pulpit. Do uruchamiania nie wymaga Pythona.
explorer "%CD%\dist"
pause
exit /b 0
:failure
echo.
echo Budowanie nie powiodlo sie. Sprawdz komunikat powyzej.
pause
exit /b 1
