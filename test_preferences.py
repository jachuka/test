import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from preferences import save_tesseract,saved_tesseract
from auto_sketch import find_tesseract


class PreferencesTests(unittest.TestCase):
    def test_selected_path_survives_new_lookup(self):
        with tempfile.TemporaryDirectory() as folder:
            executable=Path(folder)/'Niestandardowy OCR'/'tesseract.exe'
            executable.parent.mkdir();executable.touch()
            settings=Path(folder)/'settings.json'
            with patch('preferences.settings_path',return_value=settings):
                save_tesseract(executable)
                self.assertEqual(saved_tesseract(),executable.resolve())
                self.assertEqual(find_tesseract(),executable.resolve())
                self.assertEqual(json.loads(settings.read_text())['tesseract_path'],str(executable.resolve()))

    def test_preserves_other_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            executable=Path(folder)/'tesseract.exe';executable.touch()
            settings=Path(folder)/'settings.json';settings.write_text('{"other": 123}')
            with patch('preferences.settings_path',return_value=settings):
                save_tesseract(executable)
            self.assertEqual(json.loads(settings.read_text())['other'],123)

    def test_removed_binary_is_not_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            executable=Path(folder)/'tesseract.exe';executable.touch()
            with patch('preferences.settings_path',return_value=Path(folder)/'settings.json'):
                save_tesseract(executable);executable.unlink()
                self.assertIsNone(saved_tesseract())

    def test_corrupt_settings_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            executable=Path(folder)/'tesseract.exe';executable.touch()
            settings=Path(folder)/'settings.json';settings.write_text('not json')
            with patch('preferences.settings_path',return_value=settings):
                self.assertIsNone(saved_tesseract())
                with self.assertRaises(ValueError):save_tesseract(executable)
            self.assertEqual(settings.read_text(),'not json')


if __name__=='__main__':unittest.main()
