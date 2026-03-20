import sys
from PySide6.QtCore import QProcess, QObject, Signal


class PhysicalRestore(QObject):
    output_ready = Signal(str)
    finished = Signal(int)

    def __init__(self, backup_path: str, data_dir: str, host: str = "localhost", port: int = 5432, user: str = "postgres"):
        super().__init__()
        self.os = sys.platform
        self.backup_path = backup_path
        self.data_dir = data_dir
        self.host = host
        self.port = port
        self.user = user
        self.process = QProcess(self)

        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._on_finished)

        self._pending_recovery_signal = False

    def restore(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.output_ready.emit("Error: Restore Already in Progress")
            return

        self.output_ready.emit(f"Extracting backup from {self.backup_path} to {self.data_dir} ...")
        self._extract()

    def _extract(self):
        if sys.platform == "win32":
            command = "tar"
            args = ["-xzf", self.backup_path, "-C", self.data_dir]
        else:
            command = "tar"
            args = ["-xzf", self.backup_path, "-C", self.data_dir]

        self.process.start(command, args)
        if not self.process.waitForStarted(3000):
            self.output_ready.emit("Failed to start extraction")
            return

        self._pending_recovery_signal = True

    def _write_recovery_signal(self):
        import os
        signal_file = os.path.join(self.data_dir, "recovery.signal")
        try:
            open(signal_file, "w").close()
            self.output_ready.emit(f"recovery.signal written to {self.data_dir}")
        except OSError as e:
            self.output_ready.emit(f"ERROR: Could not write recovery.signal: {e}")

    def _on_finished(self, exit_code: int):
        if self._pending_recovery_signal:
            self._pending_recovery_signal = False
            if exit_code == 0:
                self.output_ready.emit("Extraction complete.")
                self._write_recovery_signal()
            else:
                self.output_ready.emit(f"ERROR: Extraction failed with exit code {exit_code}")
        self.finished.emit(exit_code)

    def _handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode()
        self.output_ready.emit(data)

    def _handle_stderr(self):
        data = self.process.readAllStandardError().data().decode()
        if any(kw in data.lower() for kw in ("error", "fatal", "could not", "failed")):
            self.output_ready.emit(f"ERROR: {data}")
        else:
            self.output_ready.emit(data)
