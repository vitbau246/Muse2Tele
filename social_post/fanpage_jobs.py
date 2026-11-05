# -*- coding: utf-8 -*-
"""Trang thai job dang fanpage (rut gon tu foxprofile\\fb_common.py, bo phan phu thuoc thu muc Videos cu).

1 job = 1 Trang: dang anh -> (cho video_delay_hours) -> dang video -> (cho comment_delay_minutes) -> comment.
File ke hoach (jobs JSON) la danh sach job, moi job co cac khoa:
  page, photo_files, photo_caption ({video_time}/{video_date}), video_file, video_caption,
  [video_cover], [video_delay_hours=2], [due], [comment_text], [comment_delay_minutes=5]
Script tu ghi them: photo_status, video_at, video_status, comment_status, comment_at, retry_at, *_attempts, error.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent      # social_post/
ROOT_DIR = BASE_DIR.parent                      # Muse2Tele/
DATA_DIR = BASE_DIR / "data"                    # cache danh sach Trang theo profile
LOG_DIR = BASE_DIR / "logs"                     # anh chup chan doan

COMMENT_DELAY_MIN = 5       # mac dinh: comment sau gio dang video bay nhieu phut
COMMENT_RETRY_MIN = 10      # nghi giua 2 lan thu comment cua cung 1 job
COMMENT_MAX_AGE_H = 48      # qua han bay nhieu gio thi bo, khong comment bu nua
COMMENT_MAX_ATTEMPTS = 8
RETRY_BACKOFF_MIN = 10      # sau moi lan loi cua 1 buoc (anh/video): nghi attempts*10 phut roi tu thu lai
RETRY_BACKOFF_MAX = 45


def load_env() -> None:
    """Doc Muse2Tele\\.env (FOXPROFILE_URL, FOXPROFILE_API_TOKEN...) neu co python-dotenv."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT_DIR / ".env")
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")


def pages_cache(profile: str) -> Path:
    """Cache danh sach Trang cua 1 profile: social_post\\data\\fb_pages_<profile>.json."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in profile)
    return DATA_DIR / f"fb_pages_{safe}.json"


def job_complete(j: dict) -> bool:
    """Xong han (thanh cong hoac bo qua sau qua nhieu lan loi): anh va video deu khong con viec."""
    return j.get("photo_status") in ("done", "failed") and j.get("video_status") in ("done", "failed")


def job_due(j: dict, now: datetime) -> bool:
    """Job con viec toi han: anh toi gio 'due' (khong co 'due' = ngay), hoac anh da dang va toi gio 'video_at'."""
    if job_complete(j):
        return False
    if j.get("retry_at") and datetime.fromisoformat(j["retry_at"]) > now:  # dang nghi giua 2 lan thu lai
        return False
    if j.get("photo_status") != "done":
        return not j.get("due") or datetime.fromisoformat(j["due"]) <= now
    at = j.get("video_at") or j.get("due")
    return j.get("video_status") != "done" and (not at or datetime.fromisoformat(at) <= now)


def comment_due(job: dict, now: datetime) -> bool:
    """Job da dang video xong, toi gio comment, chua comment, khong qua han, khong vua thu xong."""
    if job.get("video_status") != "done" or job.get("comment_status") in ("done", "failed"):
        return False
    at = job.get("comment_at")
    if not at:
        return False
    at = datetime.fromisoformat(at)
    if not at <= now < at + timedelta(hours=COMMENT_MAX_AGE_H):
        return False
    last = job.get("comment_try_at")
    return not (last and now - datetime.fromisoformat(last) < timedelta(minutes=COMMENT_RETRY_MIN))
