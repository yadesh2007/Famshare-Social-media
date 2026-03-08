import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app

def detect_media_type(filename):
    ext = filename.rsplit(".", 1)[1].lower()
    if ext in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        return "image"
    if ext in current_app.config["ALLOWED_VIDEO_EXTENSIONS"]:
        return "video"
    return ""

def save_post_media(file_storage):
    if not file_storage or not file_storage.filename:
        return "", ""

    filename = secure_filename(file_storage.filename)
    if "." not in filename:
        return "", ""

    ext = filename.rsplit(".", 1)[1].lower()
    allowed = current_app.config["ALLOWED_IMAGE_EXTENSIONS"] | current_app.config["ALLOWED_VIDEO_EXTENSIONS"]

    if ext not in allowed:
        return "", ""

    unique_name = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(current_app.config["UPLOAD_FOLDER_POSTS"], unique_name)
    file_storage.save(save_path)

    return unique_name, detect_media_type(unique_name)

def save_profile_media(file_storage):
    if not file_storage or not file_storage.filename:
        return ""

    filename = secure_filename(file_storage.filename)
    if "." not in filename:
        return ""

    ext = filename.rsplit(".", 1)[1].lower()
    if ext not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        return ""

    unique_name = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(current_app.config["UPLOAD_FOLDER_PROFILES"], unique_name)
    file_storage.save(save_path)
    return unique_name