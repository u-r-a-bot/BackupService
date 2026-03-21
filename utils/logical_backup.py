from PySide6.QtCore import QProcess, QObject, Signal, QProcessEnvironment

from utils.pg_finder import resolve


class LogicalBackup(QObject):
    output_ready = Signal(str)
    finished = Signal(int)

    def __init__(self, db_name: str, output_path: str):
        super().__init__()
        self.db_name = db_name
        self.output_path = output_path
        self.host = "localhost"
        self.port = 5432
        self.user = "postgres"
        self.password = ""

        self.process = QProcess(self)
        self.process.setProcessEnvironment(QProcessEnvironment.systemEnvironment())
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._on_finished)

    def backup(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.output_ready.emit("Error: Backup already in progress")
            return

        command = resolve("pg_dump")
        self.output_ready.emit(f"Using pg_dump: {command}")

        # Embed password directly in the connection URI and pass via --dbname.
        # Using --dbname=URI is the correct way to supply a full connection string
        # to pg_dump alongside other flags like -f. A bare positional URI only works
        # when it is the sole non-option argument, which conflicts with -f on Windows.
        pw_part  = f":{self.password}" if self.password else ""
        conn_uri = f"postgresql://{self.user}{pw_part}@{self.host}:{self.port}/{self.db_name}"
        safe_uri = f"postgresql://{self.user}:***@{self.host}:{self.port}/{self.db_name}"

        args = [
            f"--dbname={conn_uri}",
            "-f", self.output_path,
            "-Fc",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "-v",
        ]

        # Log a redacted version so the password never appears in the activity log
        self.output_ready.emit(
            f"Running: {command} --dbname={safe_uri} "
            f"-f {self.output_path} -Fc --clean --if-exists --no-owner --no-privileges -v"
        )

        self.process.start(command, args)

        if not self.process.waitForStarted(5000):
            self.output_ready.emit(
                f"ERROR: Failed to start pg_dump.\n"
                f"  Tried:    {command}\n"
                f"  OS error: {self.process.errorString()}\n"
                f"  Make sure PostgreSQL is installed and the binary path is set in Settings."
            )
            self.finished.emit(1)

    def _on_finished(self, exit_code: int, _exit_status):
        self.output_ready.emit(f"pg_dump exited with code {exit_code}")
        self.finished.emit(exit_code)

    def _handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode(errors="replace")
        if data.strip():
            self.output_ready.emit(data)

    def _handle_stderr(self):
        # pg_dump writes ALL verbose / progress output to stderr — pass everything through
        data = self.process.readAllStandardError().data().decode(errors="replace")
        if data.strip():
            self.output_ready.emit(data)