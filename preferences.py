"""Lokalne preferencje użytkownika; bez kluczy i połączeń sieciowych."""
import json
import os
from pathlib import Path
import tempfile


def settings_path():
    local=os.environ.get('LOCALAPPDATA')
    base=Path(local) if local else Path(os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')
    return base/'KalkulatorFormatek'/'settings.json'


def load_preferences():
    try:
        text=settings_path().read_text(encoding='utf-8')
    except FileNotFoundError:
        return {}
    data=json.loads(text)
    if not isinstance(data,dict):
        raise ValueError('Nieprawidłowy format pliku ustawień.')
    return data


def saved_tesseract():
    try:
        value=load_preferences().get('tesseract_path')
    except (OSError,ValueError):
        return None
    if not isinstance(value,str) or not value:
        return None
    path=Path(value)
    return path if path.is_file() else None


def save_tesseract(path):
    path=Path(path)
    if not path.is_file():
        raise ValueError('Wskazany plik Tesseract nie istnieje.')
    data=load_preferences()
    data['tesseract_path']=str(path.resolve())
    target=settings_path()
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='settings-',suffix='.tmp',dir=target.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(data,stream,ensure_ascii=False,indent=2)
        os.replace(name,target)
    finally:
        if os.path.exists(name):
            os.unlink(name)
