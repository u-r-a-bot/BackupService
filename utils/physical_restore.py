"""
utils/physical_restore.py
--------------------------
Restores a pg_basebackup archive (tar / tar.gz / tgz) using Python's
built-in tarfile module -- no external tar binary required.

After extraction, writes a recovery.signal file so PostgreSQL knows to
enter recovery mode on next start.
"""

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal


class PhysicalRestore(QObject):
    output_ready = Signal(str)
    finished = Signal(int)

    def __init__(
        self,
        backup_path: str,
        data_dir: str,
        host: str = "localhost",
        port: int = 5432,
        user: str = "postgres",
    ):
        super().__init__()
        self.backup_path = backup_path
        self.data_dir = data_dir
        self.host = host
        self.port = port
        self.user = user

        self._thread = None
        self._cancelled = threading.Event()

    # ------------------------------------------------------------------
    #  Public
    # ------------------------------------------------------------------

    def restore(self):
        if self._thread and self._thread.is_alive():
            self.output_ready.emit("Error: Restore already in progress")
            return

        self._cancelled.clear()
        self.output_ready.emit(
            f"Extracting  '{self.backup_path}'  ->  '{self.data_dir}'  (Python tarfile) ..."
        )
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self):
        """Signal the extraction thread to stop at the next file boundary."""
        self._cancelled.set()

    # ------------------------------------------------------------------
    #  Worker (runs in background thread)
    # ------------------------------------------------------------------

    def _run(self):
        import tarfile

        backup = Path(self.backup_path)
        dest   = Path(self.data_dir)

        # -- validate --------------------------------------------------
        if not backup.exists():
            self._emit_error(f"Backup file not found: {backup}")
            return

        if not tarfile.is_tarfile(str(backup)):
            self._emit_error(
                f"'{backup.name}' does not look like a tar archive. "
                f"Expected a .tar, .tar.gz, or .tgz file from pg_basebackup."
            )
            return

        try:
            dest.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self._emit_error(f"Cannot create data directory: {e}")
            return

        # -- extract ---------------------------------------------------
        # Use "r:*" so tarfile auto-detects plain tar vs gzip vs bzip2
        try:
            with tarfile.open(str(backup), "r:*") as tf:
                members = tf.getmembers()
                total   = len(members)
                self.output_ready.emit(f"Archive contains {total} entries.")

                for i, member in enumerate(members, 1):
                    if self._cancelled.is_set():
                        self.output_ready.emit("Extraction cancelled.")
                        self.finished.emit(1)
                        return

                    tf.extract(member, path=str(dest), set_attrs=True)

                    # emit progress every 50 files to avoid flooding the log
                    if i % 50 == 0 or i == total:
                        pct = int(i / total * 100)
                        self.output_ready.emit(
                            f"Extracting ... {i}/{total} files ({pct}%)"
                        )

        except tarfile.TarError as e:
            self._emit_error(f"Extraction failed: {e}")
            return
        except OSError as e:
            self._emit_error(f"I/O error during extraction: {e}")
            return

        # -- recovery.signal -------------------------------------------
        self.output_ready.emit("Extraction complete.")
        self._write_recovery_signal(dest)
        self.finished.emit(0)

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------

    def _write_recovery_signal(self, data_dir: Path):
        signal_file = data_dir / "recovery.signal"
        try:
            signal_file.touch()
            self.output_ready.emit(f"recovery.signal written to {data_dir}")
        except OSError as e:
            self.output_ready.emit(f"ERROR: Could not write recovery.signal: {e}")

    def _emit_error(self, msg: str):
        self.output_ready.emit(f"ERROR: {msg}")
        self.finished.emit(1)