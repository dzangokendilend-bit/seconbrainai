# Фаза 6-M: медиа — голос (Groq Whisper), видео (ffmpeg-кадры), файлы (attachments).
# Всё на stdlib + ffmpeg в PATH (проверяется has_ffmpeg()). Ограничения:
# до 5 вложений на сообщение, каждое ≤ 10 МБ (проверка на фронте и здесь).
import base64
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import uuid

import config

MAX_ATTACHMENT = 10 * 1024 * 1024  # 10 МБ
MAX_FILES = 5
WHISPER_MODEL = "whisper-large-v3"
GROQ_BASE = "https://api.groq.com/openai/v1"

TEXT_EXT = (".md", ".txt", ".markdown", ".json", ".csv", ".log", ".html", ".css",
            ".js", ".py", ".yml", ".yaml", ".ts", ".ini", ".cfg", ".xml")
IMAGE_MIME = ("image/png", "image/jpeg", "image/webp", "image/gif")
AUDIO_MIME = ("audio/", "video/webm")  # голосовые записи браузера — webm-аудио


def has_ffmpeg():
    return shutil.which("ffmpeg") is not None


def attachments_dir(uid):
    d = os.path.join(config.USERS_DIR, uid, "attachments")
    os.makedirs(d, exist_ok=True)
    return d


def save_attachment(uid, name, data_b64):
    """Сохраняет вложение в attachments/ пользователя. Возвращает (путь, bytes)."""
    if "," in data_b64:  # dataURL → чистый base64
        data_b64 = data_b64.split(",", 1)[1]
    raw = base64.b64decode(data_b64)
    if len(raw) > MAX_ATTACHMENT:
        raise ValueError("файл больше 10 МБ")
    safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in (name or "file"))[:80]
    path = os.path.join(attachments_dir(uid), uuid.uuid4().hex[:8] + "-" + safe)
    with open(path, "wb") as f:
        f.write(raw)
    return path, raw


def groq_transcribe(api_key, raw, mime, filename):
    """Multipart POST в Groq Whisper. Возвращает распознанный текст."""
    boundary = "----MonicaForm" + uuid.uuid4().hex
    body = b""
    body += ("--" + boundary + "\r\nContent-Disposition: form-data; "
             "name=\"model\"\r\n\r\n" + WHISPER_MODEL + "\r\n").encode()
    body += ("--" + boundary + "\r\nContent-Disposition: form-data; "
             "name=\"file\"; filename=\"" + (filename or "audio") + "\"\r\n"
             "Content-Type: " + (mime or "audio/webm") + "\r\n\r\n").encode()
    body += raw + b"\r\n"
    body += ("--" + boundary + "--\r\n").encode()
    req = urllib.request.Request(GROQ_BASE + "/audio/transcriptions", data=body, headers={
        "Content-Type": "multipart/form-data; boundary=" + boundary,
        "Authorization": "Bearer " + api_key})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data.get("text", "")


def _video_duration(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path],
            capture_output=True, timeout=30)
        return float(json.loads(r.stdout.decode())["format"]["duration"])
    except Exception:
        return 0.0


def extract_video_frames(raw, n=3):
    """ffmpeg извлекает n JPEG-кадров равномерно по длительности.
    Возвращает список base64-JPEG (пустой, если ffmpeg недоступен)."""
    if not has_ffmpeg():
        return []
    tmp_in = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp_in.write(raw)
    tmp_in.close()
    frames = []
    try:
        dur = _video_duration(tmp_in.name)
        if dur <= 0:
            return []
        for i in range(n):
            at = dur * (i + 0.5) / n
            out = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            out.close()
            r = subprocess.run(
                ["ffmpeg", "-y", "-ss", str(at), "-i", tmp_in.name,
                 "-frames:v", "1", "-q:v", "4", out.name],
                capture_output=True, timeout=60)
            if r.returncode == 0 and os.path.getsize(out.name) > 0:
                with open(out.name, "rb") as f:
                    frames.append(base64.b64encode(f.read()).decode())
            os.unlink(out.name)
    except Exception:
        pass
    finally:
        try:
            os.unlink(tmp_in.name)
        except OSError:
            pass
    return frames


def analyze_files(uid, files, groq_key):
    """Маршрутизатор вложений. Возвращает (vision_parts, prompt_addon, saved, errors):
    vision_parts — image_url-части для vision-модели,
    prompt_addon — текстовое дополнение (транскрипты, тексты файлов),
    saved — имена сохранённых файлов, errors — сообщения об ошибках."""
    vision_parts = []
    addon = []
    saved = []
    errors = []
    for f in (files or [])[:MAX_FILES]:
        name = str(f.get("name") or "file")
        mime = str(f.get("mime") or "")
        data_b64 = str(f.get("data") or "")
        try:
            path, raw = save_attachment(uid, name, data_b64)
            saved.append(os.path.basename(path))
        except Exception as e:
            errors.append(name + ": " + str(e))
            continue
        ext = os.path.splitext(name)[1].lower()
        if mime.startswith(IMAGE_MIME):
            vision_parts.append({"type": "image_url",
                                 "image_url": {"url": "data:" + mime + ";base64," + data_b64}})
        elif mime.startswith(AUDIO_MIME) or mime.startswith("audio"):
            if groq_key:
                try:
                    text = groq_transcribe(groq_key, raw, mime, name)
                    addon.append("[Расшифровка аудио «" + name + "»]: " + text[:8000])
                except Exception as e:
                    errors.append(name + ": расшифровка не удалась — " + str(e)[:120])
            else:
                errors.append(name + ": для расшифровки аудио нужен ключ Groq (настройки → ключи)")
        elif mime.startswith("video") or ext in (".mp4", ".webm", ".mov", ".mkv"):
            frames = extract_video_frames(raw)
            if frames:
                for fr in frames:
                    vision_parts.append({"type": "image_url",
                                         "image_url": {"url": "data:image/jpeg;base64," + fr}})
                addon.append("[Видео «" + name + "»]: приложено " + str(len(frames)) + " кадров.")
            else:
                errors.append(name + ": ffmpeg недоступен — кадры видео не извлечены")
        elif ext in TEXT_EXT or mime.startswith("text/"):
            try:
                text = raw.decode("utf-8", "replace")[:12000]
                addon.append("[Файл «" + name + "»]:\n" + text)
            except Exception:
                errors.append(name + ": не удалось прочитать текст")
        else:
            addon.append("[Вложение «" + name + "»] сохранено в attachments (тип " +
                         (mime or ext or "неизвестный") + ").")
    return vision_parts, "\n\n".join(addon), saved, errors
