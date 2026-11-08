#!/usr/bin/python3
"""Apply narrowly scoped update policy; --root supports offline validation."""
import argparse
import contextlib
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
import tempfile

PERIODIC = '''APT::Periodic::Enable "0";
APT::Periodic::Update-Package-Lists "0";
APT::Periodic::Download-Upgradeable-Packages "0";
APT::Periodic::Unattended-Upgrade "0";
'''
PIN = 'Package: *\nPin: release a=jammy-proposed\nPin-Priority: -1\n'
DESKTOP = '[Desktop Entry]\nType=Application\nName=Disabled update notification\nHidden=true\nX-GNOME-Autostart-enabled=false\n'


def safe(root, path):
    path = root / str(path).lstrip('/')
    for part in (path, *path.parents):
        if part == root.parent:
            break
        if part.is_symlink():
            raise ValueError(f'symlink refused: {part}')
    return path


def one_line(content, path):
    result = []
    for line in content.splitlines(keepends=True):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            result.append(line)
            continue
        try:
            words = shlex.split(line, comments=True)
        except ValueError as exc:
            raise ValueError(f'{path}: invalid source: {exc}') from exc
        if not words or words[0] not in ('deb', 'deb-src'):
            raise ValueError(f'{path}: unknown source format')
        body = re.match(r'^\s*deb(?:-src)?\s+(?:\[[^\]\n]+\]\s+)?\S+\s+(\S+)(?:\s|$)', line)
        if not body:
            raise ValueError(f'{path}: invalid source format')
        result.append('# LIGHT-BELT disabled: ' + line if body.group(1) == 'jammy-proposed' else line)
    return ''.join(result)


def deb822(content, path):
    result = []
    for stanza in re.split(r'(\n\s*\n)', content):
        if not stanza.strip() or all(not x.strip() or x.lstrip().startswith('#') for x in stanza.splitlines()):
            result.append(stanza)
            continue
        lines = stanza.splitlines(keepends=True)
        fields = {}
        current = None
        for i, line in enumerate(lines):
            if line.lstrip().startswith('#'):
                continue
            if line[:1].isspace():
                if current is None:
                    raise ValueError(f'{path}: orphan continuation')
                fields[current].append(i)
                continue
            m = re.match(r'^([A-Za-z0-9-]+):\s*(.*?)(\r?\n)?$', line)
            if not m or m.group(1).lower() in fields:
                raise ValueError(f'{path}: invalid or duplicate field')
            current = m.group(1).lower()
            fields[current] = [i]
        if not {'types', 'uris', 'suites'} <= fields.keys():
            raise ValueError(f'{path}: incomplete deb822 source')
        indexes = fields['suites']
        values = ' '.join(lines[i].split(':', 1)[1] if n == 0 else lines[i] for n, i in enumerate(indexes)).split()
        if 'jammy-proposed' in values:
            remaining = [v for v in values if v != 'jammy-proposed']
            if remaining:
                first = indexes[0]
                lines[first] = re.sub(r':.*', ': ' + ' '.join(remaining), lines[first].rstrip('\r\n')) + ('\n' if lines[first].endswith('\n') else '')
                for i in reversed(indexes[1:]):
                    del lines[i]
            elif 'enabled' in fields:
                idx = fields['enabled'][0]
                if len(fields['enabled']) != 1:
                    raise ValueError(f'{path}: complex Enabled field')
                lines[idx] = 'Enabled: no\n'
            else:
                if lines and not lines[-1].endswith('\n'):
                    lines[-1] += '\n'
                lines.append('Enabled: no\n')
        result.append(''.join(lines))
    return ''.join(result)


def setting(content, key, value):
    pattern = re.compile(r'^\s*' + re.escape(key) + r'\s*=.*$', re.M)
    if pattern.search(content):
        return pattern.sub(key + '=' + value, content)
    return content + ('' if not content or content.endswith('\n') else '\n') + key + '=' + value + '\n'


def read(path):
    with path.open('r', encoding='utf-8', newline='') as stream:
        return stream.read()


def atomic_write(path, content, owner=None):
    old = path.stat() if path.exists() else None
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name == 'posix':
            if owner is not None:
                os.chown(temporary, owner.st_uid, owner.st_gid)
            elif old is not None:
                os.chown(temporary, old.st_uid, old.st_gid)
        os.chmod(temporary, old.st_mode & 0o7777 if old else 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextlib.contextmanager
def apt_locks(enabled):
    with contextlib.ExitStack() as stack:
        if enabled:
            import fcntl
            for name in ('/var/lib/dpkg/lock-frontend', '/var/lib/dpkg/lock', '/var/lib/apt/lists/lock', '/var/cache/apt/archives/lock'):
                if os.path.exists(name):
                    handle = stack.enter_context(open(name, 'a'))
                    try:
                        fcntl.lockf(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError as exc:
                        raise ValueError(f'APT/dpkg transaction active at {name}; wait and retry') from exc
        yield


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='/')
    parser.add_argument('--home', required=True)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--lock', action='store_true')
    parser.add_argument('--probe-lock', action='store_true')
    args = parser.parse_args()
    if args.probe_lock and not args.lock:
        raise ValueError('--probe-lock requires --lock')
    if args.lock and args.root != '/':
        raise ValueError('--lock requires the live root')
    with apt_locks(args.lock):
        if args.probe_lock:
            return 0
        return apply(args)


def apply(args):
    root = Path(args.root).absolute()
    if not args.home.startswith('/') or '..' in Path(args.home).parts:
        raise ValueError('invalid home directory')
    changes = {}
    source_dir = safe(root, 'etc/apt/sources.list.d')
    sources = [safe(root, 'etc/apt/sources.list')]
    if source_dir.exists():
        sources.extend(sorted(source_dir.glob('*.list')))
        sources.extend(sorted(source_dir.glob('*.sources')))
    for path in sources:
        safe(root, path.relative_to(root))
        if path.exists():
            original = read(path)
            changes[path] = (deb822 if path.suffix == '.sources' else one_line)(original, path)
    changes[safe(root, 'etc/apt/apt.conf.d/99light-belt-updates')] = PERIODIC
    changes[safe(root, 'etc/apt/preferences.d/light-belt-no-proposed')] = PIN
    for file, key, value in [('etc/update-manager/release-upgrades', 'Prompt', 'never'), ('etc/default/apport', 'enabled', '0')]:
        path = safe(root, file)
        if path.exists():
            changes[path] = setting(read(path), key, value)
    for name in ('update-notifier.desktop', 'ubuntu-advantage-notification.desktop', 'apport-gtk.desktop', 'whoopsie.desktop'):
        if safe(root, 'etc/xdg/autostart/' + name).exists():
            changes[safe(root, args.home + '/.config/autostart/' + name)] = DESKTOP
    dirty = []
    for path, content in changes.items():
        if not path.exists() or read(path) != content:
            dirty.append((path, content))
        backup = path.with_name(path.name + '.light-belt.bak')
        safe(root, backup.relative_to(root))
    if args.check:
        for path, _ in dirty:
            print(f'NONCOMPLIANT: {path}')
        return bool(dirty)
    for path, content in dirty:
        user_home = safe(root, args.home)
        user_path = user_home in path.parents
        new_dirs = []
        parent = path.parent
        while user_path and parent != user_home and not parent.exists():
            new_dirs.append(parent)
            parent = parent.parent
        path.parent.mkdir(parents=True, exist_ok=True)
        if user_path and os.name == 'posix':
            owner = user_home.stat()
            for directory in new_dirs:
                os.chown(directory, owner.st_uid, owner.st_gid)
        if path.exists():
            backup = path.with_name(path.name + '.light-belt.bak')
            if not backup.exists():
                shutil.copy2(path, backup)
        atomic_write(path, content, owner if user_path and os.name == 'posix' else None)
    print('Update policy configured. Previously installed proposed packages require manual review; none were downgraded or removed.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, UnicodeError, ValueError) as exc:
        print(f'Update policy error: {exc}', file=sys.stderr)
        sys.exit(2)
