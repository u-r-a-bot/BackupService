import os
import tempfile

from PySide6.QtCore import QProcess, QObject, Signal, QProcessEnvironment

from utils.pg_finder import resolve


class PhysicalBackup(QObject):
    output_ready = Signal(str)
    finished = Signal(int)

    def __init__(
        self,
        output_path: str,
        host: str = "localhost",
        port: int = 5432,
        user: str = "postgres",
    ):
        super().__init__()
        self.output_path = output_path
        self.host = host
        self.port = port
        self.user = user
        self.password = ""

        self._pgpass_file: str | None = None  # path to temp pgpass, cleaned up on finish

        self.process = QProcess(self)
        self.process.setProcessEnvironment(QProcessEnvironment.systemEnvironment())
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._on_finished)

    # ── public ───────────────────────────────────────────────

    def backup(self):
        command = resolve("pg_basebackup")
        self.output_ready.emit(f"Using pg_basebackup: {command}")

        env = QProcessEnvironment.systemEnvironment()

        # pg_basebackup does not accept a connection URI, so we use a temporary
        # .pgpass file pointed to by PGPASSFILE — the most reliable method on Windows.
        if self.password:
            self._pgpass_file = self._write_pgpass()
            if self._pgpass_file:
                env.insert("PGPASSFILE", self._pgpass_file)
                self.output_ready.emit(f"Password file written to: {self._pgpass_file}")

        self.process.setProcessEnvironment(env)

        args = [
            "-h", self.host,
            "-p", str(self.port),
            "-U", self.user,
            "-D", self.output_path,
            "-Ft",   # tar format
            "-z",    # gzip compression
            "-Xs",   # stream WAL
            "-P",    # show progress
            "-v",    # verbose
        ]

        self.output_ready.emit(f"Running: {command} {' '.join(args)}")
        self.process.start(command, args)

        if not self.process.waitForStarted(5000):
            self.output_ready.emit(
                f"ERROR: Failed to start pg_basebackup.\n"
                f"  Tried:    {command}\n"
                f"  OS error: {self.process.errorString()}\n"
                f"  Make sure PostgreSQL is installed and the binary path is set in Settings."
            )
            self._cleanup_pgpass()
            self.finished.emit(1)

    # ── private helpers ──────────────────────────────────────

    def _write_pgpass(self) -> str | None:
        """
        Write a temporary pgpass file with the connection credentials.
        Returns the file path, or None on failure.

        pgpass format:  hostname:port:database:username:password
        Using '*' for database matches any database.
        """
        try:
            fd, path = tempfile.mkstemp(suffix=".pgpass", prefix="pgsafe_")
            with os.fdopen(fd, "w") as f:
                f.write(f"{self.host}:{self.port}:*:{self.user}:{self.password}\n")

            # On Unix, pgpass files must not be world/group readable
            if os.name != "nt":
                os.chmod(path, 0o600)

            return path
        except OSError as e:
            self.output_ready.emit(f"WARNING: Could not write pgpass file: {e}")
            return None

    def _cleanup_pgpass(self):
        if self._pgpass_file and os.path.exists(self._pgpass_file):
            try:
                os.unlink(self._pgpass_file)
            except OSError:
                pass
        self._pgpass_file = None

    def _on_finished(self, exit_code: int, _exit_status):
        self._cleanup_pgpass()
        self.output_ready.emit(f"pg_basebackup exited with code {exit_code}")
        self.finished.emit(exit_code)

    def _handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode(errors="replace")
        if data.strip():
            self.output_ready.emit(data)

    def _handle_stderr(self):
        # pg_basebackup writes ALL progress output to stderr — pass everything through
        data = self.process.readAllStandardError().data().decode(errors="replace")
        if data.strip():
            self.output_ready.emit(data)