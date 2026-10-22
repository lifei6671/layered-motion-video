"""系统字体与项目字体目录索引，字体路径仅由服务端白名单解析。"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from functools import lru_cache
from pathlib import Path

from font_variants import describe_variant, font_variant_sort_key, preferred_variant_key

FONT_SUFFIXES = {".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2"}
FONT_DIR = Path(__file__).resolve().parent / "fonts"


def _font_directories() -> list[Path]:
    if sys.platform == "win32":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return [windir / "Fonts", local / "Microsoft" / "Windows" / "Fonts"]
    if sys.platform == "darwin":
        return [Path("/System/Library/Fonts"), Path("/Library/Fonts"), Path.home() / "Library/Fonts"]
    return [
        Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
        Path.home() / ".local/share/fonts", Path.home() / ".fonts",
    ]


def _windows_registry_fonts(dirs: list[Path]) -> dict[Path, str]:
    if sys.platform != "win32":
        return {}
    import winreg

    fonts: dict[Path, str] = {}
    key_name = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, key_name) as key:
                idx = 0
                while True:
                    try:
                        label, filename, _ = winreg.EnumValue(key, idx)
                    except OSError:
                        break
                    idx += 1
                    if not isinstance(filename, str):
                        continue
                    possible = Path(os.path.expandvars(filename))
                    if possible.suffix.lower() not in FONT_SUFFIXES:
                        continue
                    candidates = [possible] if possible.is_absolute() else [d / possible for d in dirs]
                    for candidate in candidates:
                        if candidate.is_file():
                            pretty = re.sub(r"\s*\((?:TrueType|OpenType)\)\s*$", "", label, flags=re.I).strip()
                            fonts.setdefault(candidate.resolve(), pretty)
                            break
        except OSError:
            continue
    return fonts


@lru_cache(maxsize=1)
def list_system_fonts() -> list[dict[str, str]]:
    """系统字体只扫描一次；项目目录字体单独动态扫描。"""
    directories = _font_directories()
    found = _windows_registry_fonts(directories)
    for folder in directories:
        if not folder.is_dir():
            continue
        try:
            for path in folder.rglob("*"):
                try:
                    if path.is_file() and path.suffix.lower() in FONT_SUFFIXES:
                        resolved = path.resolve()
                        found.setdefault(resolved, path.stem)
                except OSError:
                    continue
        except OSError:
            continue

    fonts = []
    for path, label in found.items():
        identifier = hashlib.sha256(str(path).casefold().encode("utf-8")).hexdigest()[:20]
        fonts.append({
            "id": identifier,  # 保留已有模板的系统字体 ID
            "name": f"{label} · {path.name}",
            "path": str(path),
            "search": f"{label} {path.name}".casefold(),
            "source": "system",
        })
    fonts.sort(key=lambda font: (font["name"].casefold(), font["path"].casefold()))
    return fonts


def list_local_fonts() -> list[dict[str, str]]:
    """每次查询重新扫描 fonts/，支持服务运行期间增加/删除字体及子目录。"""
    root = FONT_DIR.resolve()
    if not root.is_dir():
        return []
    found = []
    try:
        paths = root.rglob("*")
        for path in paths:
            try:
                if not path.is_file() or path.suffix.lower() not in FONT_SUFFIXES:
                    continue
                resolved = path.resolve()
                if not resolved.is_relative_to(root) or resolved.stat().st_size > 80 * 1024 * 1024:
                    continue
                relative_path = path.relative_to(root)
                relative = relative_path.as_posix()
                # 保留原始基于文件相对路径的 ID，已保存模板仍能解析。
                identifier = "local:" + hashlib.sha256(relative.casefold().encode("utf-8")).hexdigest()[:20]
                family = relative_path.parts[0] if len(relative_path.parts) > 1 else "根目录字体"
                label = f"{path.stem} · {relative}"
                found.append({
                    "id": identifier,
                    "name": label,
                    "path": str(resolved),
                    "filename": path.name,
                    "relative_path": relative,
                    "family": family,
                    "search": f"{family} {label}".casefold(),
                    "source": "local",
                    **describe_variant(path),
                })
            except (OSError, ValueError):
                continue
    except OSError:
        return []
    return sorted(found, key=lambda font: (font["family"].casefold(), font_variant_sort_key(font)))


def get_font_by_id(font_id: str) -> str | None:
    """绝不使用浏览器直接提交的路径，只读取被索引的字体。"""
    if font_id.startswith("local:"):
        fonts = list_local_fonts()
    else:
        fonts = list_system_fonts()
    return next((font["path"] for font in fonts if font["id"] == font_id), None)


def default_font_id(kind: str) -> str:
    fonts = list_system_fonts()
    preferred = (
        ["华文行楷", "行楷", "stxingka", "华文新魏", "楷体", "simkai", "华文中宋", "微软雅黑", "msyh"]
        if kind == "title" else
        ["华文楷体", "stkaiti", "楷体", "simkai", "微软雅黑", "microsoft yahei",
         "msyh", "等线", "dengxian", "黑体", "simhei", "宋体"]
    )
    for keyword in preferred:
        for font in fonts:
            if keyword.casefold() in font["search"]:
                return font["id"]
    return fonts[0]["id"] if fonts else ""


def default_local_font_id() -> str:
    fonts = list_local_fonts()
    if not fonts:
        return ""
    first_family = fonts[0]["family"]
    candidates = [item for item in fonts if item["family"] == first_family]
    return min(candidates, key=preferred_variant_key)["id"]


def public_catalog() -> dict:
    """项目字体附带字形覆盖信息；系统字体在显示预览时按需解析。"""
    from font_preview import get_font_preview_info

    system_fonts = list_system_fonts()
    local_fonts = list_local_fonts()
    local_entries = [
        {
            "id": font["id"],
            "name": font["name"],
            "source": "local",
            "family": font["family"],
            "variant": font["variant"],
            "weight": font["weight"],
            "shape": font["shape"],
            "monospace": font["monospace"],
            "italic": font["italic"],
            "format": font["format"],
            "filename": font["filename"],
            "relative_path": font["relative_path"],
            **get_font_preview_info(font["path"]),
        }
        for font in local_fonts
    ]
    family_counts = {}
    for entry in local_entries:
        family_counts[entry["family"]] = family_counts.get(entry["family"], 0) + 1
    return {
        "families": [
            {"id": name, "name": name, "count": count}
            for name, count in sorted(family_counts.items(), key=lambda pair: pair[0].casefold())
        ],
        "fonts": local_entries + [
            {"id": font["id"], "name": font["name"], "source": "system"}
            for font in system_fonts
        ],
        "defaults": {
            "title": default_font_id("title"),
            "subtitle": default_font_id("subtitle"),
            "local": default_local_font_id(),
        },
        "local_count": len(local_fonts),
    }
