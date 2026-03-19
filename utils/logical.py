import sys
from PySide6.QtCore import QProcess, QObject, Signal


class LogicalBackup(QObject):
    output_ready = Signal(str) # Signal to communicate with UI
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
        #Connect process signals to internal methods
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self.finished.emit)


    def backup(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.output_ready.emit("Error: Backup Already in Progress")
            return
        command = "pg_dump"
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
            "-v",  # verbose so output_ready gets meaningful progress lines
        ]
        self.process.start(command, args) #Start the process the PysideWay
        if not self.process.waitForStarted(3000):
            self.output_ready.emit("Failed to start")
            return

    def _handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode()
        self.output_ready.emit(data)

    def _handle_stderr(self):
        data = self.process.readAllStandardError().data().decode()
        # pg_dump sends verbose progress to stderr — only tag real errors
        if any(kw in data.lower() for kw in ("error", "fatal", "could not", "failed")):
            self.output_ready.emit(f"ERROR: {data}")
        else:
            self.output_ready.emit(data)



