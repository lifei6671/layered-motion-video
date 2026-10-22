"""正式封面编辑器的本机构建准备。

构建只在缺失或源文件更新时执行，保留 Python 独立启动的使用方式。
不修改场景、字体、素材及 Git 状态。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _native_path(path: Path) -> str:
    """Windows 扩展路径前缀会让 npm.cmd 将本机磁盘误判为 UNC 路径。"""
    value = str(path.resolve())
    return value[4:] if os.name == "nt" and value.startswith("\\\\?\\") else value


def editor_bundle_stale(root: Path) -> bool:
    frontend = root / "fabric-poc"
    bundle = root / "static" / "fabric-poc.bundle.js"
    if not bundle.is_file() or bundle.stat().st_size == 0:
        return True
    timestamp = bundle.stat().st_mtime_ns
    sources = [
        frontend / "package.json",
        frontend / "package-lock.json",
        *list((frontend / "src").rglob("*.js")),
        *list((frontend / "src").rglob("*.mjs")),
    ]
    return any(not file.is_file() or file.stat().st_mtime_ns > timestamp for file in sources)


def ensure_editor_bundle(root: Path) -> tuple[bool, str]:
    """返回（是否可用、状态描述）。构建失败时保留服务供兼容入口使用。"""
    root = Path(root)
    frontend = root / "fabric-poc"
    if not editor_bundle_stale(root):
        return True, "Fabric.js 封面编辑器资源已就绪。"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm") or shutil.which("npm")
    if not npm:
        return False, "新版前端需要 Node.js 与 npm。请安装 Node.js 后重新启动。"
    cwd = _native_path(frontend)
    modules = frontend / "node_modules"
    steps = []
    if not (modules / "fabric").is_dir() or not (modules / "esbuild").is_dir():
        steps.append(("安装前端依赖", ["ci", "--ignore-scripts", "--no-audit", "--no-fund"]))
    steps.append(("构建封面编辑器", ["run", "build"]))
    for label, args in steps:
        command = ["cmd.exe", "/d", "/c", "npm", *args] if os.name == "nt" else [npm, *args]
        try:
            result = subprocess.run(
                command, cwd=cwd, capture_output=True, text=True,
                encoding="utf-8", errors="replace", check=False,
                timeout=240 if args[0] == "ci" else 120,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"{label}执行失败：{exc}"
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "未知错误").strip()[-1400:]
            return False, f"{label}执行失败（退出码 {result.returncode}）：{detail}"
    bundle = root / "static" / "fabric-poc.bundle.js"
    if not bundle.is_file() or bundle.stat().st_size == 0:
        return False, "前端构建完成，但没有生成可用的浏览器脚本。"
    return True, "Fabric.js 封面编辑器构建成功，主页可以使用。"
