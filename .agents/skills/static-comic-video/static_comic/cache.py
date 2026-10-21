"""Verified, content-addressed stage products and failure-safe publication (SC-P6)."""
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path
import os
import re
import shutil
import tempfile
import uuid

from .contracts import canonical, digest, read_json
from .media import file_hash
from .paths import resolve_path

BASE = Path(__file__).resolve().parents[1]


def versions(*names, packages=()):
    return {'cache': file_hash(Path(__file__)),
            'sources': {name: file_hash(BASE / name) for name in names},
            'packages': {name: version(name) for name in packages}}


def publish(root, outputs):
    """Stage every byte first; per-file atomic replace, rollback on caught failure.

    Records are supplied last by callers. An interrupted process can leave a mixed
    generation, which hash-bound readers reject; it cannot publish unchecked bytes.
    """
    paths = {name: resolve_path(root, name, output=True) for name in outputs}
    pending, backups, replaced = {}, {}, []
    rollback_failed = False
    try:
        for name, target in paths.items():
            source = outputs[name]
            if target.exists() and ((isinstance(source, bytes) and target.read_bytes() == source)
                    or (isinstance(source, Path) and file_hash(target) == file_hash(source))):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            resolve_path(root, name, output=True)
            tag = uuid.uuid4().hex
            temp = target.with_name('.' + target.name + '.' + tag + '.tmp')
            pending[name] = temp
            if isinstance(source, bytes):
                temp.write_bytes(source)
                if temp.read_bytes() != source:
                    raise ValueError('Publication byte verification failed')
            else:
                shutil.copyfile(source, temp)
                if file_hash(source) != file_hash(temp):
                    raise ValueError('Publication hash verification failed')
            if target.exists():
                backup = target.with_name('.' + target.name + '.' + tag + '.bak')
                backups[name] = backup
                shutil.copyfile(target, backup)
        for name, temp in pending.items():
            resolve_path(root, name, output=True)
            os.replace(temp, paths[name]); replaced.append(name)
    except BaseException as failure:
        errors = []
        for name in reversed(replaced):
            try:
                resolve_path(root, name, output=True)
                if name in backups:
                    os.replace(backups[name], paths[name])
                else:
                    paths[name].unlink()
            except OSError as error:
                errors.append(f"{name}: {error}")
            except ValueError as error:
                errors.append(f"{name}: {error}")
        if errors:
            rollback_failed = True
            raise ValueError('Publication rollback incomplete; preserve .bak files and restore before retry: '
                             + '; '.join(errors)) from failure
        raise
    finally:
        # A failed rollback must never delete the only remaining original bytes.
        for path in pending.values():
            path.unlink(missing_ok=True)
        if not rollback_failed:
            for path in backups.values():
                path.unlink(missing_ok=True)


def lookup(root, stage, inputs):
    if not re.fullmatch(r'[a-z0-9_-]+', stage):
        raise ValueError('Invalid cache stage')
    inputs = read_json(canonical(inputs))
    key = digest(inputs)
    folder = resolve_path(root, f'work/cache/{stage}/{key}/manifest.json', output=True).parent
    try:
        record = read_json(resolve_path(root, f'work/cache/{stage}/{key}/manifest.json').read_bytes())
        if (not isinstance(record, dict) or record.get('key') != key or record.get('inputs') != inputs
                or not isinstance(record.get('files'), dict) or not record['files']
                or 'result' not in record or record.get('result_sha256') != digest(record['result'])):
            raise ValueError('Cache key/manifest mismatch')
        for name, sha in record['files'].items():
            if not isinstance(name, str) or not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{64}', sha):
                raise ValueError('Malformed cache file inventory')
            path = resolve_path(folder, name)
            if name == 'manifest.json' or file_hash(path) != sha:
                raise ValueError('Cache artifact hash mismatch')
        actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
        if actual != set(record['files']) | {'manifest.json'}:
            raise ValueError('Cache artifact inventory mismatch')
        return folder, record, 'verified_same_key'
    except (OSError, ValueError, KeyError, TypeError):
        return folder, None, 'missing_corrupt_or_incompatible'


def event(root, stage, key, status, reason):
    value = {'stage': stage, 'key': key, 'status': status, 'reason': reason}
    publish(root, {f'reports/cache/{stage}.json': canonical(value)})
    return value


def cached(root, stage, inputs, build, *, rebuild_reason=None):
    root = Path(root).resolve(strict=True)
    inputs = read_json(canonical(inputs))
    folder, record, reason = lookup(root, stage, inputs)
    key = digest(inputs)
    if record is not None and rebuild_reason is None:
        event(root, stage, key, 'HIT', reason)
        return folder, record['result']
    previous = resolve_path(root, f'reports/cache/{stage}.json')
    if previous.exists():
        try:
            if read_json(previous.read_bytes()).get('key') != key:
                reason = 'inputs_or_version_changed'
        except ValueError:
            pass
    reason = rebuild_reason or reason
    parent = resolve_path(root, 'work/cache/.temporary/.probe', output=True).parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            temp = Path(directory)
            result = build(temp)
            files = {p.relative_to(temp).as_posix(): file_hash(p) for p in temp.rglob('*') if p.is_file()}
            if not files or 'manifest.json' in files:
                raise ValueError('Cache builder must produce payload files only')
            record = {'key': key, 'inputs': inputs, 'files': files, 'result': result, 'result_sha256': digest(result)}
            # A corrupt entry is never reused; remove only its validated scoped folder.
            if folder.exists():
                shutil.rmtree(folder)
            prefix = folder.relative_to(Path(root)).as_posix()
            publish(root, {**{prefix+'/'+n: temp/n for n in files},
                           prefix+'/manifest.json': canonical(record)})
        event(root, stage, key, 'REBUILT', reason)
        return folder, result
    except BaseException as error:
        event(root, stage, key, 'FAILED', str(error))
        raise


def cached_json(root, stage, inputs, compute):
    def build(temp):
        (temp/'value.json').write_bytes(canonical(compute()))
    folder, _ = cached(root, stage, inputs, build)
    return read_json((folder/'value.json').read_bytes())


@contextmanager
def operation(root, name, reports):
    """Record the outcome of the current stage attempt."""
    old = {}
    for stage in ('preview', 'visual', 'render'):
        path = resolve_path(root, reports+'/'+stage+'.json')
        if path.exists():
            try:
                record = read_json(path.read_bytes())
                valid = all(resolve_path(root, name).is_file() and file_hash(resolve_path(root, name)) == sha
                            for name, sha in record['files'].items())
                old[stage] = {'input_digest': digest(record['snapshot']), 'files': record['files'],
                              'files_verified': valid}
            except (ValueError, KeyError):
                pass
    attempt = {'operation': name, 'status': 'RUNNING', 'retained_previous': old}
    target = reports+'/attempt.json'
    publish(root, {target: canonical(attempt)})
    try:
        yield
    except BaseException as error:
        publish(root, {target: canonical({**attempt, 'status': 'FAILED', 'error': str(error)})})
        raise
    publish(root, {target: canonical({**attempt, 'status': 'SUCCEEDED'})})
