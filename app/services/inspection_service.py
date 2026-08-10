import os
import uuid

from fastapi import HTTPException, UploadFile

ALLOWED_VIDEO_CONTENT_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
}

MAX_VIDEO_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB

STORAGE_DIR = "storage/videos"


def save_inspection_video(file: UploadFile) -> str:
    if file.content_type not in ALLOWED_VIDEO_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video type: {file.content_type}",
        )

    os.makedirs(STORAGE_DIR, exist_ok=True)

    extension = os.path.splitext(file.filename)[1]
    safe_filename = f"{uuid.uuid4()}{extension}"
    destination_path = os.path.join(STORAGE_DIR, safe_filename)

    total_bytes_written = 0
    with open(destination_path, "wb") as buffer:
        while chunk := file.file.read(1024 * 1024):
            total_bytes_written += len(chunk)
            if total_bytes_written > MAX_VIDEO_SIZE_BYTES:
                buffer.close()
                os.remove(destination_path)
                raise HTTPException(
                    status_code=413,
                    detail="Video exceeds the maximum allowed size (100MB)",
                )
            buffer.write(chunk)

    return destination_path
