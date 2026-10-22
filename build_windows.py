"""Buduj EXE na Windows, dołączając Tesseract, jeśli jest lokalnie zainstalowany."""
import os
from pathlib import Path
import subprocess
import sys


def main():
    if sys.platform!='win32':
        raise SystemExit('Plik EXE należy budować na Windows.')
    root=Path(__file__).resolve().parent
    from auto_sketch import find_tesseract
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--name','KalkulatorFormatek']
    executable=find_tesseract()
    if executable:
        folder=executable.resolve().parent
        if not (folder/'tessdata'/'eng.traineddata').is_file():
            raise SystemExit('Tesseract nie zawiera modelu eng.traineddata. Doinstaluj język angielski w Tesseract.')
        print('Dołączam lokalny Tesseract i jego dane do EXE. Plik może być znacznie większy.')
        command+=['--add-data',str(folder)+os.pathsep+'tesseract']
    else:
        print('Brak Tesseract: EXE będzie wykrywać obrysy i pytać o wymiary; OCR wymaga instalacji Tesseract.')
    command.append(str(root/'app.py'))
    raise SystemExit(subprocess.run(command,cwd=root).returncode)


if __name__=='__main__':
    main()
