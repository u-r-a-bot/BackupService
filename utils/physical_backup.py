import sys
from PySide6.QtCore import QProcess, QObject, Signal

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
        command = "pg_basebackup"
        args = [
            "-h", self.host,
            "-p", str(self.port),
            "-U", self.user,
            "-D", self.output_path,  # destination directory
            "-Ft",  # tar format (one .tar per tablespace)
            "-z",  # gzip compression
            "-Xs",  # stream WAL during backup
            "-P",  # show progress
            "-v",  # verbose so output_ready gets meaningful lines
        ]
        self.process.start(command, args)  # Start the process the PySide way

    def _handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode()
        self.output_ready.emit(data)

    def _handle_stderr(self):
        data = self.process.readAllStandardError().data().decode()

        if any(kw in data.lower() for kw in ("error", "fatal", "could not", "failed")):
            self.output_ready.emit(f"ERROR: {data}")
        else:
            self.output_ready.emit(data)

