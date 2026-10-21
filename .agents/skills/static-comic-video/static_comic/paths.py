"""Episode-scoped native file access, including Windows reparse points."""
from pathlib import Path, PureWindowsPath
import re


def resolve_path(root, relative, *, output=False):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Project root must be a directory")
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError(f"Non-canonical relative path: {relative!r}")
    parts = relative.split("/")
    if (PureWindowsPath(relative).drive or relative.startswith("/")
            or any(part in ("", ".", "..") or part.endswith((".", " "))
                   or re.search(r'[<>:"|?*\x00-\x1f]', part)
                   or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)
                   for part in parts)):
        raise ValueError(f"Unsafe relative path: {relative!r}")
    lexical = root.joinpath(*parts)
    resolved = lexical.resolve(strict=False)
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError(f"Path escapes project: {relative}")
    if output:
        # Do not redirect generated writes into even an in-project input subtree.
        current = root
        for part in parts:
            current /= part
            if current.is_symlink() or current.is_junction():
                raise ValueError(f"Output reparse point: {relative}")
            if current != lexical and current.exists() and not current.is_dir():
                raise ValueError(f"Output ancestor is not a directory: {relative}")
        if lexical.exists() and not lexical.is_file():
            raise ValueError(f"Output is not a regular file: {relative}")
    return resolved


def read_bytes(root, relative, limit):
    path = resolve_path(root, relative)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError(f"Missing, oversized or non-regular input: {relative}")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"Oversized input: {relative}")
    return data


def write_bytes(root, relative, data):
    path = resolve_path(root, relative, output=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Resolve again after creating ancestors; all output locations are controlled.
    path = resolve_path(root, relative, output=True)
    path.write_bytes(data)
    return path


def process_path(value):
    """Convert an authorized local path to native child-process notation.
    """
    import ntpath
    value = str(value)
    if value.startswith("\\\\?\\"):
        value = value[4:]
        if not re.match(r"^[A-Za-z]:[\\/]", value):
            raise ValueError("Only extended local drive paths are supported")
    if value.startswith(("\\\\", "//")):
        raise ValueError("UNC/device paths are not supported at the process boundary")
    if re.match(r"^[A-Za-z]:", value):
        if not re.match(r"^[A-Za-z]:[\\/]", value):
            raise ValueError("Drive-relative process path is not allowed")
        return ntpath.normpath(value)
    return value


def process_args(command, cwd=None):
    """Keep argv separate; also adapt paths in --option=value arguments."""
    argv = []
    for argument in command:
        value = str(argument)
        flag = ''
        if value.startswith('--') and '=' in value:
            option, value = value.split('=', 1)
            flag = option + '='
        # Bare strings also include FFmpeg selectors (a:0), filters and URLs.
        # Only Path objects and absolute filesystem representations are paths.
        if isinstance(argument, Path) or re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith(('\\\\', '//')):
            value = process_path(value)
        argv.append(flag + value)
    return argv, process_path(cwd) if cwd is not None else None
