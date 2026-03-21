"""
utils/pg_finder.py
------------------
Locates PostgreSQL binaries (pg_dump, pg_restore, pg_basebackup) on the
current machine.

Strategy (in order):
  1. Check PATH via shutil.which -- if found, done.
  2. Scan a hard-coded list of common install locations per OS.
  3. Return None so the caller (Settings panel) can ask the user to browse.

All results are cached in memory for the lifetime of the process.
"""

from __future__ import annotations

import glob
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------
#  Per-OS candidate directories
# ---------------------------------------------------------------

_WINDOWS_PG_ROOTS: List[str] = [
    r"C:\Program Files\PostgreSQL",
    r"C:\Program Files (x86)\PostgreSQL",
    r"C:\PostgreSQL",
    r"D:\Program Files\PostgreSQL",
    r"D:\PostgreSQL",
]

_MACOS_ROOTS: List[str] = [
    "/Applications/Postgres.app/Contents/Versions",  # Postgres.app
    "/usr/local/opt/postgresql",                       # Homebrew Intel
    "/opt/homebrew/opt/postgresql",                    # Homebrew Apple Silicon
    "/usr/local/bin",
    "/usr/bin",
]

_LINUX_ROOTS: List[str] = [
    "/usr/lib/postgresql",  # Debian/Ubuntu (versioned sub-dirs handled below)
    "/usr/bin",
    "/usr/local/bin",
    "/opt/postgresql",
    "/opt/pgsql",
]

# Every binary this module tracks
BINARIES = ("pg_dump", "pg_restore", "pg_basebackup")

_cache: Dict[str, Optional[Path]] = {}


# ---------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------

def _exe(name: str) -> str:
    """Append .exe on Windows, leave unchanged elsewhere."""
    return name + ".exe" if sys.platform == "win32" else name


def _candidate_dirs() -> List[Path]:
    """Return an ordered list of directories to probe for binaries."""
    dirs: List[Path] = []

    if sys.platform == "win32":
        for root in _WINDOWS_PG_ROOTS:
            rp = Path(root)
            if rp.is_dir():
                # Iterate version sub-folders newest-first, e.g. 16, 15, 14 ...
                for sub in sorted(rp.iterdir(), reverse=True):
                    dirs.append(sub / "bin")
                dirs.append(rp)  # also try the root itself

    elif sys.platform == "darwin":
        for root in _MACOS_ROOTS:
            rp = Path(root)
            if not rp.exists():
                continue
            if rp.name == "Versions":
                # Postgres.app layout: .../Versions/<major>/bin
                for sub in sorted(rp.iterdir(), reverse=True):
                    dirs.append(sub / "bin")
            else:
                dirs.append(rp / "bin")
                dirs.append(rp)

    else:  # Linux / other UNIX
        # Debian/Ubuntu: /usr/lib/postgresql/<version>/bin
        deb_root = Path("/usr/lib/postgresql")
        if deb_root.is_dir():
            for sub in sorted(deb_root.iterdir(), reverse=True):
                dirs.append(sub / "bin")

        # RHEL/CentOS/Rocky: /usr/pgsql-<version>/bin
        for p in sorted(glob.glob("/usr/pgsql-*/bin"), reverse=True):
            dirs.append(Path(p))

        for root in _LINUX_ROOTS:
            rp = Path(root)
            if rp.is_dir():
                dirs.append(rp)

    return dirs


def _find_binary(name: str) -> Optional[Path]:
    """Return the absolute Path to *name*, or None if nowhere to be found."""
    # 1. Honour whatever is on PATH first
    found = shutil.which(_exe(name))
    if found:
        return Path(found)

    # 2. Walk common install locations
    for d in _candidate_dirs():
        candidate = d / _exe(name)
        if candidate.is_file():
            return candidate

    return None


# ---------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------

def find(binary: str) -> Optional[Path]:
    """
    Return the resolved Path for *binary*, or None.
    The result is cached; call clear_cache() to force a re-scan.
    """
    if binary not in _cache:
        _cache[binary] = _find_binary(binary)
    return _cache[binary]


def set_override(binary: str, path: Optional[str]) -> None:
    """
    Persist a user-chosen path for *binary* into the cache.
    Pass None or an empty string to remove the override.
    """
    if path:
        _cache[binary] = Path(path)
    else:
        _cache.pop(binary, None)


def clear_cache() -> None:
    """Discard all cached results so the next find() re-scans from scratch."""
    _cache.clear()


def resolve(binary: str) -> str:
    """
    Return the string path to use when launching *binary* via QProcess.
    Falls back to the bare name (e.g. 'pg_dump') so the OS gets one last
    chance via PATH.  Never raises.
    """
    p = find(binary)
    return str(p) if p else _exe(binary)


def status() -> Dict[str, Optional[str]]:
    """Return {binary_name: path_string_or_None} for every tracked binary."""
    return {b: (str(find(b)) if find(b) else None) for b in BINARIES}