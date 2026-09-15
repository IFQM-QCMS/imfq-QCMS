# QCMS Local Disk Storage Provider
import os
import mimetypes
import logging
import tempfile
from typing import Optional, Tuple, Any, Dict
from datetime import datetime, timezone
from werkzeug.utils import secure_filename

from app.infrastructure.storage.providers.base import BaseStorageProvider
from app.infrastructure.storage.exceptions import (
    StorageUploadError, StorageDownloadError, StorageDeleteError
)

logger = logging.getLogger("QCMS.Storage.Local")
FALLBACK_UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), "qcms_uploads")

class LocalStorageProvider(BaseStorageProvider):
    """
    Local filesystem storage provider (used for local testing and Hostinger/VPS disk fallback).
    """

    def __init__(self, upload_folder: Optional[str] = None):
        default_uploads = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "uploads"))
        self.upload_folder = upload_folder or os.getenv("UPLOAD_FOLDER", default_uploads)
        try:
            os.makedirs(self.upload_folder, exist_ok=True)
        except Exception as e:
            logger.warning(f"[LocalStorageProvider] Could not create upload folder {self.upload_folder}: {e}")

    def save_file(
        self,
        file_data: Any,
        filename: Optional[str] = None,
        subfolder: str = "",
        content_type: Optional[str] = None,
        acl: str = "private"
    ) -> Dict[str, Any]:
        if hasattr(file_data, "filename") and not filename:
            filename = file_data.filename

        if not filename:
            filename = f"file_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.bin"

        safe_name = secure_filename(filename)
        if not safe_name:
            safe_name = f"upload_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.dat"

        if not safe_name.startswith("20") and "_" not in safe_name[:16]:
            final_filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{safe_name}"
        else:
            final_filename = safe_name

        clean_sub = subfolder.strip("/\\")
        blob_path = f"{clean_sub}/{final_filename}" if clean_sub else final_filename

        if hasattr(file_data, "read"):
            file_bytes = file_data.read()
            if hasattr(file_data, "seek"):
                try:
                    file_data.seek(0)
                except Exception:
                    pass
        elif isinstance(file_data, (bytes, bytearray)):
            file_bytes = bytes(file_data)
        else:
            file_bytes = str(file_data).encode("utf-8")

        if not content_type:
            if hasattr(file_data, "content_type") and file_data.content_type:
                content_type = file_data.content_type
            else:
                guessed_type, _ = mimetypes.guess_type(final_filename)
                content_type = guessed_type or "application/octet-stream"

        file_size = len(file_bytes)

        target_dir = os.path.join(self.upload_folder, clean_sub) if clean_sub else self.upload_folder
        try:
            os.makedirs(target_dir, exist_ok=True)
            local_file_path = os.path.join(target_dir, final_filename)
            with open(local_file_path, "wb") as f:
                f.write(file_bytes)
        except (PermissionError, OSError) as pe:
            logger.warning(
                f"[LocalStorageProvider] Primary upload directory '{target_dir}' not writable ({pe}). "
                f"Attempting fallback directory '{FALLBACK_UPLOAD_FOLDER}'."
            )
            try:
                fallback_target = os.path.join(FALLBACK_UPLOAD_FOLDER, clean_sub) if clean_sub else FALLBACK_UPLOAD_FOLDER
                os.makedirs(fallback_target, exist_ok=True)
                local_file_path = os.path.join(fallback_target, final_filename)
                with open(local_file_path, "wb") as f:
                    f.write(file_bytes)
            except Exception as fe:
                logger.error(f"[LocalStorageProvider] Fallback write also failed for {blob_path}: {fe}")
                raise StorageUploadError(f"Local storage write failed: {str(fe)}", original_error=fe)
        except Exception as e:
            logger.error(f"[LocalStorageProvider] Failed to write file {blob_path}: {e}")
            raise StorageUploadError(f"Local storage write failed: {str(e)}", original_error=e)

        return {
            "filename": final_filename,
            "path": blob_path,
            "local_path": local_file_path,
            "url": f"/uploads/{blob_path}",
            "backend": "local",
            "size_bytes": file_size,
            "content_type": content_type
        }

    def get_file_bytes(self, filename_or_path: str, subfolder: str = "") -> Tuple[Optional[bytes], Optional[str]]:
        clean_sub = subfolder.strip("/\\")
        target_path = f"{clean_sub}/{filename_or_path}" if clean_sub and not filename_or_path.startswith(clean_sub) else filename_or_path
        local_path = os.path.join(self.upload_folder, target_path)

        candidates = [local_path, os.path.join(FALLBACK_UPLOAD_FOLDER, target_path)]
        for cand in candidates:
            if os.path.exists(cand):
                try:
                    guessed_type, _ = mimetypes.guess_type(cand)
                    with open(cand, "rb") as f:
                        return f.read(), (guessed_type or "application/octet-stream")
                except Exception as e:
                    logger.error(f"[LocalStorageProvider] Error reading local file {cand}: {e}")
                    raise StorageDownloadError(f"Failed to read local file: {str(e)}", original_error=e)

        return None, None

    def generate_signed_url(self, blob_path: str, expiry_minutes: int = 15) -> Optional[str]:
        # Local filesystem serves files via authenticated proxy download endpoint
        clean_path = blob_path.lstrip("/\\")
        return f"/api/storage/download/{clean_path}"

    def delete_file(self, filename_or_path: str, subfolder: str = "") -> bool:
        clean_sub = subfolder.strip("/\\")
        target_path = f"{clean_sub}/{filename_or_path}" if clean_sub and not filename_or_path.startswith(clean_sub) else filename_or_path
        candidates = [os.path.join(self.upload_folder, target_path), os.path.join(FALLBACK_UPLOAD_FOLDER, target_path)]

        deleted = False
        for cand in candidates:
            if os.path.exists(cand):
                try:
                    os.remove(cand)
                    deleted = True
                except Exception as e:
                    logger.warning(f"[LocalStorageProvider] Failed to remove local file {cand}: {e}")
                    raise StorageDeleteError(f"Failed to delete local file: {str(e)}", original_error=e)
        return deleted

    def exists(self, filename_or_path: str, subfolder: str = "") -> bool:
        clean_sub = subfolder.strip("/\\")
        target_path = f"{clean_sub}/{filename_or_path}" if clean_sub and not filename_or_path.startswith(clean_sub) else filename_or_path
        return os.path.exists(os.path.join(self.upload_folder, target_path)) or os.path.exists(os.path.join(FALLBACK_UPLOAD_FOLDER, target_path))

    def get_info(self) -> Dict[str, Any]:
        return {
            "backend": "local",
            "upload_folder": self.upload_folder,
            "connected": True
        }
