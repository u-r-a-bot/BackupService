import sys
from PySide6.QtCore import QProcess, QObject, Signal

from utils.pg_finder import resolve


class PhysicalBackup(QObject):
    output_ready = Signal(str)
    finished = Signal(int)

    def __init__(self, output_path: str, host: str = "localhost", port: int = 5432, user: str = "postgres"):
        super().__init__()
        self.os = sys.platform
        self.output_path = output_path
        self.host = host
        self.port = port
        self.user = user
        self.process = QProcess(self)

        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self.finished.emit)

    def backup(self):
        command = resolve("pg_basebackup")
        self.output_ready.emit(f"Using pg_basebackup: {command}")

        args = [
            "-h", self.host,
            "-p", str(self.port),
            "-U", self.user,
            "-D", self.output_path,
            "-Ft",
            "-z",
            "-Xs",
            "-P",
            "-v",
        ]
        self.process.start(command, args)
        if not self.process.waitForStarted(3000):
            self.output_ready.emit(
                f"ERROR: Failed to start pg_basebackup.\n"
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