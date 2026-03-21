import sys
from PySide6.QtCore import QProcess, QObject, Signal

from utils.pg_finder import resolve


class LogicalBackup(QObject):
    output_ready = Signal(str)
    finished = Signal(int)

    def __init__(self, db_name, output_path):
        super().__init__()
        self.os = sys.platform
        self.pgdump_path = None
        self.db_name: str = db_name
        self.output_path = output_path
        self.process = QProcess(self)
        self.host = "localhost"
        self.port = 5432
        self.user = "postgres"
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self.finished.emit)

    def backup(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.output_ready.emit("Error: Backup Already in Progress")
            return

        command = resolve("pg_dump")
        self.output_ready.emit(f"Using pg_dump: {command}")

        args = [
            "-h", self.host,
            "-p", str(self.port),
            "-U", self.user,
            "-d", self.db_name,
            "-f", self.output_path,
            "-Fc",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "-v",
        ]
        self.process.start(command, args)
        if not self.process.waitForStarted(3000):
            self.output_ready.emit(
                f"ERROR: Failed to start pg_dump.\n"
                f"  Tried: {command}\n"
                f"  Make sure PostgreSQL is installed and the binary path is set in Settings."
            )
            self.finished.emit(1)

    def _handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode()
        self.output_ready.emit(data)

    def _handle_stderr(self):
        data = self.process.readAllStandardError().data().decode()
        if any(kw in data.lower() for kw in ("error", "fatal", "could not", "failed")):
            self.output_ready.emit(f"ERROR: {data}")
        else:
            self.output_ready.emit(data)