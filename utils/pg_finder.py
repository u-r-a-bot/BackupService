"""
utils/pg_finder.py
------------------
Locates PostgreSQL binaries (pg_dump, pg_restore, pg_basebackup) and the
PostgreSQL data directory on the current machine.

Strategy for binaries (in order):
  1. Check PATH via shutil.which -- if found, done.
  2. Scan a hard-coded list of common install locations per OS.
  3. Return None so the caller (Settings panel) can ask the user to browse.

Strategy for data directory:
  1. Ask the running server via "pg_config --pkgdatadir" hint paths.
  2. Walk the same version-sorted install roots and look for a "data" sub-folder
     that contains PG_VERSION (the canonical marker of a live data dir).
  3. Fall back to well-known default paths per OS.
  4. Return None if nothing is found.

All binary results are cached in memory for the lifetime of the process.
"""

from __future__ import annotations

import glob
import shutil
import subprocess
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
    "/Applications/Postgres.app/Contents/Versions",
    "/usr/local/opt/postgresql",
    "/opt/homebrew/opt/postgresql",
    "/usr/local/bin",
    "/usr/bin",
]

_LINUX_ROOTS: List[str] = [
    "/usr/lib/postgresql",
    "/usr/bin",
    "/usr/local/bin",
    "/opt/postgresql",
    "/opt/pgsql",
]

# Every binary this module tracks
BINARIES = ("pg_dump", "pg_restore", "pg_basebackup")

_cache: Dict[str, Optional[Path]] = {}


# ---------------------------------------------------------------
#  Internal helpers — binaries
# ---------------------------------------------------------------

def _exe(name: str) -> str:
    return name + ".exe" if sys.platform == "win32" else name


def _candidate_dirs() -> List[Path]:
    """Return an ordered list of bin directories to probe for binaries."""
    dirs: List[Path] = []

    if sys.platform == "win32":
        for root in _WINDOWS_PG_ROOTS:
            rp = Path(root)
            if rp.is_dir():
                for sub in sorted(rp.iterdir(), reverse=True):
                    dirs.append(sub / "bin")
                dirs.append(rp)

    elif sys.platform == "darwin":
        for root in _MACOS_ROOTS:
            rp = Path(root)
            if not rp.exists():
                continue
            if rp.name == "Versions":
                for sub in sorted(rp.iterdir(), reverse=True):
                    dirs.append(sub / "bin")
            else:
                dirs.append(rp / "bin")
                dirs.append(rp)

    else:
        deb_root = Path("/usr/lib/postgresql")
        if deb_root.is_dir():
            for sub in sorted(deb_root.iterdir(), reverse=True):
                dirs.append(sub / "bin")
        for p in sorted(glob.glob("/usr/pgsql-*/bin"), reverse=True):
            dirs.append(Path(p))
        for root in _LINUX_ROOTS:
            rp = Path(root)
            if rp.is_dir():
                dirs.append(rp)

    return dirs


def _find_binary(name: str) -> Optional[Path]:
    found = shutil.which(_exe(name))
    if found:
        return Path(found)
    for d in _candidate_dirs():
        candidate = d / _exe(name)
        if candidate.is_file():
            return candidate
    return None


# ---------------------------------------------------------------
#  Internal helpers — data directory
# ---------------------------------------------------------------

def _is_data_dir(path: Path) -> bool:
    """A valid PostgreSQL data directory always contains a PG_VERSION file."""
    return (path / "PG_VERSION").exists()


def _candidate_data_dirs() -> List[Path]:
    """
    Return an ordered list of candidate data directories, newest version first.
    Covers Windows, macOS (Postgres.app + Homebrew), and Linux (Debian/RHEL).
    """
    candidates: List[Path] = []

    if sys.platform == "win32":
        for root in _WINDOWS_PG_ROOTS:
            rp = Path(root)
            if not rp.is_dir():
                continue
            # e.g. C:\Program Files\PostgreSQL\16\data
            for ver_dir in sorted(rp.iterdir(), reverse=True):
                candidates.append(ver_dir / "data")

    elif sys.platform == "darwin":
        # Postgres.app
        versions_root = Path("/Applications/Postgres.app/Contents/Versions")
        if versions_root.is_dir():
            for ver_dir in sorted(versions_root.iterdir(), reverse=True):
                candidates.append(ver_dir / "var-postgresql")  # Postgres.app layout
                candidates.append(ver_dir / "data")

        # Homebrew Intel / Apple Silicon
        for brew_prefix in ("/usr/local", "/opt/homebrew"):
            # versioned: /opt/homebrew/var/postgresql@16
            for p in sorted(glob.glob(f"{brew_prefix}/var/postgresql@*"), reverse=True):
                candidates.append(Path(p))
            # unversioned
            candidates.append(Path(f"{brew_prefix}/var/postgresql"))
            candidates.append(Path(f"{brew_prefix}/var/postgres"))

    else:
        # Debian/Ubuntu: /var/lib/postgresql/<version>/main
        pg_root = Path("/var/lib/postgresql")
        if pg_root.is_dir():
            for ver_dir in sorted(pg_root.iterdir(), reverse=True):
                candidates.append(ver_dir / "main")
                candidates.append(ver_dir / "data")

        # RHEL/CentOS/Rocky: /var/lib/pgsql/<version>/data
        for p in sorted(glob.glob("/var/lib/pgsql/*/data"), reverse=True):
            candidates.append(Path(p))
        candidates.append(Path("/var/lib/pgsql/data"))

        # Generic fallbacks
        candidates.append(Path("/var/lib/postgresql/data"))
        candidates.append(Path("/opt/postgresql/data"))

    return candidates


def _ask_running_server() -> Optional[Path]:
    """
    Try to ask the *running* PostgreSQL server for its data_directory via
    a quick psql one-liner.  Returns None if psql isn't available or the
    server isn't running.
    """
    psql = shutil.which("psql") or shutil.which("psql.exe")
    if not psql:
        # Try finding psql next to pg_dump
        pg_dump_path = find("pg_dump")
        if pg_dump_path:
            candidate = pg_dump_path.parent / _exe("psql")
            if candidate.is_file():
                psql = str(candidate)

    if not psql:
        return None

    try:
        result = subprocess.run(
            [psql, "-U", "postgres", "-h", "localhost",
             "-tAc", "SHOW data_directory;"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        out = result.stdout.strip()
        if out:
            p = Path(out)
            if _is_data_dir(p):
                return p
    except Exception:
        pass

    return None


# ---------------------------------------------------------------
#  Public API — binaries
# ---------------------------------------------------------------

def find(binary: str) -> Optional[Path]:
    """Return the resolved Path for *binary*, or None. Result is cached."""
    if binary not in _cache:
        _cache[binary] = _find_binary(binary)
    return _cache[binary]


def set_override(binary: str, path: Optional[str]) -> None:
    if path:
        _cache[binary] = Path(path)
    else:
        _cache.pop(binary, None)


def clear_cache() -> None:
    _cache.clear()


def resolve(binary: str) -> str:
    """Return string path for QProcess. Falls back to bare name so OS PATH gets a last try."""
    p = find(binary)
    return str(p) if p else _exe(binary)


def status() -> Dict[str, Optional[str]]:
    return {b: (str(find(b)) if find(b) else None) for b in BINARIES}


# ---------------------------------------------------------------
#  Public API — data directory
# ---------------------------------------------------------------

def find_data_directory() -> Optional[Path]:
    """
    Return the most likely PostgreSQL data directory on this machine, or None.

    Strategy (in order of reliability):
      1. Ask the running server via psql SHOW data_directory  ← most accurate
      2. Walk versioned install roots looking for a dir with PG_VERSION
      3. Return None — caller should prompt the user to browse
    """
    # 1. Ask the live server first — guaranteed correct if it's running
    live = _ask_running_server()
    if live:
        return live

    # 2. Walk candidate paths and return the first one that looks like a real data dir
    for candidate in _candidate_data_dirs():
        if _is_data_dir(candidate):
            return candidate

    return None