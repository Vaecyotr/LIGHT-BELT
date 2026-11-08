"""Running Host identity and bounded player readiness checks."""
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


def check_mpv(ipc_path: str) -> dict:
    from light_engine.media.mpv_adapter import MpvIPCAdapter
    client = MpvIPCAdapter(ipc_path)
    try:
        client.connect()
        values = {name: client.get_property(name) for name in (
            'vo-configured', 'fullscreen', 'idle-active', 'options/gpu-context',
        )}
        values['mpv_ready'] = (values['vo-configured'] is True
                               and values['fullscreen'] is True
                               and isinstance(values['idle-active'], bool)
                               and values['options/gpu-context'] == 'wayland')
        return values
    finally:
        client.close()


if __name__ == '__main__':
    import argparse
    import json
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument('--mpv-socket', required=True)
    args = parser.parse_args()
    try:
        result = check_mpv(args.mpv_socket)
    except (OSError, RuntimeError) as exc:
        result = {'mpv_ready': False, 'error': str(exc)}
    print(json.dumps(result))
    sys.exit(0 if result['mpv_ready'] else 1)
