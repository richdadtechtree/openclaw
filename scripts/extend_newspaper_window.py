"""Extend the existing collector retry window; never run the collector on deployment."""
import fcntl
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def transform(source):
    # The collector lives outside this repository. Refuse unknown formats instead
    # of replacing unrelated times or silently claiming that it was configured.
    cutoff = re.compile(r'^(?:export\s+)?CUTOFF=[^\n]*', re.M)
    matches = list(cutoff.finditer(source))
    if len(matches) != 1 or not re.search(r'(?<!\d)(?:07|08):00(?!\d)', matches[0][0]):
        raise ValueError('Unsupported CUTOFF assignment in run_daily.sh; no changes made')
    interval = re.compile(r'^(?:export\s+)?INTERVAL_SECONDS=(?:300|"300"|\x27300\x27)(?:[ \t]*(?:#[^\n]*)?)$', re.M)
    if len(list(interval.finditer(source))) != 1:
        raise ValueError('Expected INTERVAL_SECONDS=300; no changes made')
    return cutoff.sub(lambda m: re.sub(r'(?<!\d)07:00(?!\d)', '08:00', m[0]), source)


def apply(target):
    target = Path(target)
    if not target.is_file():
        return False
    with open(str(target) + '.window.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        source = target.read_text()
        updated = transform(source)
        if updated == source:
            return False
        fd, name = tempfile.mkstemp(prefix='.retry-window-', dir=target.parent)
        try:
            with os.fdopen(fd, 'w') as out:
                out.write(updated)
                out.flush()
                os.fsync(out.fileno())
            os.chmod(name, target.stat().st_mode & 0o7777)
            subprocess.run(['bash', '-n', name], check=True, capture_output=True)
            backup = Path(str(target) + '.before-0800')
            if not backup.exists():
                shutil.copy2(target, backup)
            os.replace(name, target)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    print('[newspaper] retry cutoff 07:00 -> 08:00; interval remains 300 seconds')
    return True


if __name__ == '__main__':
    target = Path(os.path.expanduser(os.getenv('NEWSPAPER_DIR', '~/newspaper'))) / 'scripts/run_daily.sh'
    try:
        apply(target)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('[newspaper] retry-window update failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
