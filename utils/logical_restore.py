import sys
from PySide6.QtCore import QProcess, QObject, Signal


class LogicalRestore(QObject):
    output_ready = Signal(str)
    finished = Signal(int)

    def __init__(self, db_name: str, input_path: str):
        super().__init__()
        self.os = sys.platform
        self.db_name = db_name
        self.input_path = input_path
        self.host = "localhost"
        self.port = 5432
        self.user = "postgres"
        self.process = QProcess(self)

        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self.finished.emit)

    def restore(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.output_ready.emit("Error: Restore Already in Progress")
            return

        command = "pg_restore"
        args = [
            "-h", self.host,
            "-p", str(self.port),
            "-U", self.user,
            "-d", self.db_name,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "-v",
            self.input_path,
        ]
        self.process.start(command, args)
        if not self.process.waitForStarted(3000):
            self.output_ready.emit("Failed to start")
            return

    def _handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode()
        self.output_ready.emit(data)

    def _handle_stderr(self):
        data = self.process.readAllStandardError().data().decode()
        if any(kw in data.lower() for kw in ("error", "fatal", "could not", "failed")):
            self.output_ready.emit(f"ERROR: {data}")
        else:
            self.output_ready.emit(data)
