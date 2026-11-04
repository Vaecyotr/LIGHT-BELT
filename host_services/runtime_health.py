"""Build identity captured before the running application imports its adapters."""
from pathlib import Path
import re
import subprocess


def capture_identity(root: Path) -> dict:
    try:
        commit = subprocess.check_output(
            ['git', '-C', str(root), 'rev-parse', 'HEAD'], timeout=5,
        ).decode('ascii').strip()
        if not re.fullmatch(r'[0-9a-f]{40}', commit):
            raise ValueError('Invalid build commit')
        dirty = subprocess.check_output(
            ['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=normal'], timeout=5,
        )
        return {'commit': commit, 'source_clean': not bool(dirty)}
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        return {'commit': None, 'source_clean': False}
