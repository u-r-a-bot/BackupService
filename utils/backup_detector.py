"""
utils/backup_detector.py
────────────────────────
Inspects a file path and figures out whether it is a logical backup
(pg_dump custom-format) or a physical backup (pg_basebackup tar/gzip).

Returns a BackupInfo dataclass so callers don't have to think about
the difference at all.
"""

from __future__ import annotations

import os
import struct
import tarfile
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Optional


class BackupKind(Enum):
    LOGICAL  = auto()   # pg_dump custom format (.dump / .backup / .pgdump)
    PHYSICAL = auto()   # pg_basebackup tar/gzip archive
    UNKNOWN  = auto()


@dataclass
class BackupInfo:
    kind:        BackupKind
    path:        Path
    label:       str          # short human-readable label
    description: str          # one-sentence explanation for the UI
    # Physical-only extras
    needs_data_dir: bool = False

    @property
    def is_logical(self) -> bool:
        return self.kind == BackupKind.LOGICAL

    @property
    def is_physical(self) -> bool:
        return self.kind == BackupKind.PHYSICAL


# pg_dump custom-format magic bytes: "PGDMP" in ASCII
_PGDUMP_MAGIC = b"PGDMP"

# tar magic at offset 257: "ustar"
_TAR_MAGIC_OFFSET = 257
_TAR_MAGIC        = b"ustar"

# gzip magic
_GZIP_MAGIC = b"\x1f\x8b"


def _read_bytes(path: Path, offset: int, length: int) -> bytes:
    try:
        with open(path, "rb") as fh:
            fh.seek(offset)
            return fh.read(length)
    except OSError:
        return b""


def _is_pgdump_custom(path: Path) -> bool:
    """Check for pg_dump custom-format magic ('PGDMP' at byte 0)."""
    return _read_bytes(path, 0, 5) == _PGDUMP_MAGIC


def _is_gzip(path: Path) -> bool:
    return _read_bytes(path, 0, 2) == _GZIP_MAGIC


def _gzip_contains_pg_basebackup(path: Path) -> bool:
    """
    A pg_basebackup tar.gz contains 'base.tar' or 'pg_wal.tar' as a member name,
    or has a member called 'PG_VERSION'.
    We open it as a tar to check without fully extracting.
    """
    try:
        with tarfile.open(path, "r:gz") as tar:
            names = tar.getnames()
            pg_hints = ("PG_VERSION", "global/pg_control", "base.tar", "pg_wal.tar")
            return any(any(h in n for h in pg_hints) for n in names)
    except Exception:
        return False


def _is_plain_tar(path: Path) -> bool:
    return _read_bytes(path, _TAR_MAGIC_OFFSET, 5) == _TAR_MAGIC


def detect(path: str | Path) -> BackupInfo:
    """
    Inspect *path* and return a BackupInfo describing what was found.
    Never raises; returns UNKNOWN on any failure.
    """
    p = Path(path)

    if not p.exists():
        return BackupInfo(
            kind=BackupKind.UNKNOWN,
            path=p,
            label="File not found",
            description="The selected file does not exist.",
        )

    # ── 1. pg_dump custom format ──────────────────────────────────────────
    if _is_pgdump_custom(p):
        return BackupInfo(
            kind=BackupKind.LOGICAL,
            path=p,
            label="Logical backup",
            description=(
                "This is a pg_dump backup. "
                "It can be restored into any existing database."
            ),
            needs_data_dir=False,
        )

    # ── 2. gzip — could be pg_basebackup .tar.gz ─────────────────────────
    if _is_gzip(p):
        if _gzip_contains_pg_basebackup(p):
            return BackupInfo(
                kind=BackupKind.PHYSICAL,
                path=p,
                label="Physical backup",
                description=(
                    "This is a pg_basebackup archive. "
                    "It will be extracted into your PostgreSQL data directory."
                ),
                needs_data_dir=True,
            )
        # gzip but not a known physical backup — could be a compressed pg_dump
        return BackupInfo(
            kind=BackupKind.LOGICAL,
            path=p,
            label="Compressed backup (assumed logical)",
            description=(
                "This looks like a compressed backup. "
                "It will be treated as a pg_dump backup."
            ),
            needs_data_dir=False,
        )

    # ── 3. plain .tar ─────────────────────────────────────────────────────
    if _is_plain_tar(p):
        return BackupInfo(
            kind=BackupKind.PHYSICAL,
            path=p,
            label="Physical backup (plain tar)",
            description=(
                "This is an uncompressed pg_basebackup archive. "
                "It will be extracted into your PostgreSQL data directory."
            ),
            needs_data_dir=True,
        )

    # ── 4. extension hints as a last resort ──────────────────────────────
    suffix = p.suffix.lower()
    if suffix in (".dump", ".backup", ".pgdump", ".sql"):
        return BackupInfo(
            kind=BackupKind.LOGICAL,
            path=p,
            label="Logical backup (by extension)",
            description=(
                "Detected as a pg_dump backup based on the file extension. "
                "It can be restored into any existing database."
            ),
            needs_data_dir=False,
        )

    if suffix in (".tar", ".gz", ".tgz"):
        return BackupInfo(
            kind=BackupKind.PHYSICAL,
            path=p,
            label="Physical backup (by extension)",
            description=(
                "Detected as a pg_basebackup archive based on the file extension. "
                "It will be extracted into your PostgreSQL data directory."
            ),
            needs_data_dir=True,
        )

    return BackupInfo(
        kind=BackupKind.UNKNOWN,
        path=p,
        label="Unknown backup type",
        description=(
            "Could not determine the backup type automatically. "
            "Please select the restore method manually below."
        ),
        needs_data_dir=False,
    )
