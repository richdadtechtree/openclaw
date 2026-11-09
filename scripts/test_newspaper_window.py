"""Validate the external shell-script migration without accessing the real collector."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('window', Path(__file__).with_name('extend_newspaper_window.py'))
window = importlib.util.module_from_spec(spec)
spec.loader.exec_module(window)


class WindowTests(unittest.TestCase):
    def test_supported_cutoffs_and_idempotence(self):
        for cutoff in ['CUTOFF="07:00"', "CUTOFF=$(date -d 'today 07:00' +%s)"]:
            source = '#!/bin/bash\nINTERVAL_SECONDS=300\n' + cutoff + '\nOTHER="07:00"\n'
            result = window.transform(source)
            self.assertIn('08:00', result)
            self.assertIn('OTHER="07:00"', result)
            self.assertEqual(window.transform(result), result)

    def test_unknown_or_ambiguous_settings_are_rejected(self):
        for source in ['CUTOFF=7\nINTERVAL_SECONDS=300\n',
                       'CUTOFF="07:00"\nINTERVAL_SECONDS=60\n',
                       'CUTOFF="07:00"\nCUTOFF="07:00"\nINTERVAL_SECONDS=300\n']:
            with self.assertRaises(ValueError):
                window.transform(source)

    def test_backup_mode_and_no_repeated_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'run_daily.sh'
            original = '#!/bin/bash\nINTERVAL_SECONDS=300\nCUTOFF="07:00"\n'
            target.write_text(original)
            target.chmod(0o750)
            self.assertTrue(window.apply(target))
            self.assertEqual(target.stat().st_mode & 0o777, 0o750)
            self.assertEqual(Path(str(target) + '.before-0800').read_text(), original)
            self.assertFalse(window.apply(target))

    def test_invalid_shell_leaves_original_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'run_daily.sh'
            original = 'INTERVAL_SECONDS=300\nCUTOFF="07:00"\nif then\n'
            target.write_text(original)
            with self.assertRaises(window.subprocess.CalledProcessError):
                window.apply(target)
            self.assertEqual(target.read_text(), original)


if __name__ == '__main__':
    unittest.main()
