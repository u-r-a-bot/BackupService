import sys
from PySide6.QtCore import QProcess, QObject, Signal, QProcessEnvironment

from utils.pg_finder import resolve


class LogicalRestore(QObject):
    output_ready = Signal(str)
    finished = Signal(int)

    def __init__(self, db_name: str, input_path: str):
        super().__init__()
        self.db_name = db_name
        self.input_path = input_path
        self.host = "localhost"
        self.port = 5432
        self.user = "postgres"
        self.password = ""

        self.process = QProcess(self)
        self.process.setProcessEnvironment(QProcessEnvironment.systemEnvironment())
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._on_finished)

    def restore(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.output_ready.emit("Error: Restore already in progress")
            return

        command = resolve("pg_restore")
        self.output_ready.emit(f"Using pg_restore: {command}")

        env = QProcessEnvironment.systemEnvironment()
        if self.password:
            env.insert("PGPASSWORD", self.password)
        self.process.setProcessEnvironment(env)

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
        self.output_ready.emit(f"Running: {command} {' '.join(args)}")
        self.process.start(command, args)

        if not self.process.waitForStarted(5000):
            self.output_ready.emit(
                f"ERROR: Failed to start pg_restore.\n"
                f"  Tried: {command}\n"
                f"  OS error: {self.process.errorString()}\n"
                f"  Make sure PostgreSQL is installed and the binary path is set in Settings."
            )
            self.finished.emit(1)

    def _on_finished(self, exit_code: int, _exit_status):
        self.output_ready.emit(f"pg_restore exited with code {exit_code}")
        self.finished.emit(exit_code)

    def _handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode(errors="replace")
        if data.strip():
            self.output_ready.emit(data)

    def _handle_stderr(self):
        # pg_restore writes ALL verbose/progress output to stderr — pass everything through
        data = self.process.readAllStandardError().data().decode(errors="replace")
        if data.strip():
            self.output_ready.emit(data)
