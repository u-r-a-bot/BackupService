import tarfile
import tempfile
from pathlib import Path
from typing import Optional, Union

from PySide6.QtCore import QObject, QThread, Signal
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _build_credentials(credentials: Union[str, dict], ) -> service_account.Credentials:
    if isinstance(credentials, dict):
        return service_account.Credentials.from_service_account_info(credentials, scopes=SCOPES)
    return service_account.Credentials.from_service_account_file(str(credentials),scopes = SCOPES)


class _UploadWorker(QObject):
    progress = Signal(int)
    output_ready = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, credentials:Union[str ,dict], source:Union[str, Path], folder_id:Optional[str], is_directory:bool):
        super().__init__()
        self._credentials = credentials
        self._source = Path(source)
        self._folder_id = folder_id
        self._is_directory = is_directory

    def run(self):
        try:
            creds = _build_credentials(self._credentials)
            service = build("drive", "v3", credentials=creds, cache_discovery=False)

            if self._is_directory:
                self.output_ready.emit(f"Compressing directory:- {self._source}")
                upload_path, cleanup = self._pack_directory(self._source)
            else:
                upload_path, cleanup = self._source, False

            file_id = self._upload(service, upload_path)
            if cleanup:
                upload_path.unlink(missing_ok=True)
            self.finished.emit(file_id)

        except Exception as exc:
            self.error.emit(f"ERROR: {exc}")

    def _pack_directory(self, src: Path) -> tuple[Path, bool]:
        tmp = tempfile.NamedTemporaryFile(
            suffix=".tar.gz", delete=False,
            prefix=f"{src.name}_"
        )
        tmp.close()
        out_path = Path(tmp.name)

        with tarfile.open(out_path, "w:gz") as tar:
            tar.add(src, arcname=src.name)

        self.output_ready.emit(
            f"Compressed to {out_path.stat().st_size / 1024 / 1024:.1f} MB"
        )
        return out_path, True

    def _upload(self, service, file_path:Path):
        file_name = file_path.name
        mime = ("application/gzip" if file_path.suffix in (".gz", ".tar")  else "application/octet-stream" )
        metadata = {"name": file_name}
        if self._folder_id:
            metadata["parents"] = [self._folder_id]
        self.output_ready.emit(f"Uploading {file_name} to Google Drive …")
        media = MediaFileUpload(str(file_path), mimetype=mime, resumable=True, chunksize=8 * 1024 * 1024,)
        request = service.files().create(body=metadata, media_body=media, fields="id")
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                self.progress.emit(pct)
                self.output_ready.emit(f"Upload progress: {pct}%")
        file_id = response.get("id")
        self.output_ready.emit(
            f"Upload complete. Drive file ID: {file_id}"
        )
        return file_id

class CloudBackup(QObject):
    output_ready = Signal(str)
    progress =Signal(int)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, source:Union[str, Path], credentials:Union[str,dict], folder_id:Optional[str]=None):
        super().__init__()
        self._source = Path(source)
        self._credentials = credentials
        self._folder_id = folder_id

        self._thread: Optional[QThread] = None
        self._worker: Optional[_UploadWorker] = None

    def upload(self):
        if self._thread and self._thread.isRunning():
            self.output_ready.emit("ERROR: Upload is already in Progress")
            return

        if not self._source.exists():
            self.output_ready.emit(f"ERROR: Source not found:- {self._source}")
            return
        is_directory = self._source.is_dir()
        self._thread = QThread()
        self._worker = _UploadWorker(
            credentials=self._credentials,
            source=self._source,
            folder_id=self._folder_id,
            is_directory=is_directory
        )
        self._thread.started.connect(self._worker.run)
        self._worker.output_ready.connect(self.output_ready)
        self._worker.progress.connect(self.progress)
        self._worker.finished.connect(self._on_success)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def cancel(self):
        if self._thread and self._thread.isRunning():
            self._thread.requestInterruption()
            self._thread.quit()
            self.output_ready.emit("Upload Cancelled")

    def _on_success(self, file_id: str):
        self.finished.emit(file_id)

    def _on_error(self, message:str):
        self.error.emit(message)
        self.output_ready.emit(message)





