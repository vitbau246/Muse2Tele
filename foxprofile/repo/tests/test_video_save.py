"""Auto-save of Muse videos: MUSE_SAVE_VIDEOS / MUSE_SAVE_VIDEO_DIR in Muse2Tele's .env."""

import pytest

from src.core import video_save


@pytest.fixture()
def muse_root(tmp_path, monkeypatch):
    (tmp_path / "muse_telebot").mkdir()
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=x\n# comment\n", encoding="utf-8")
    cwd = tmp_path / "foxprofile" / "data"
    cwd.mkdir(parents=True)
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("FOXPROFILE_ENV_FILE", raising=False)
    return tmp_path


def test_default_is_on_with_the_default_folder(muse_root):
    cfg = video_save.current()
    assert cfg.enabled and not cfg.custom
    assert cfg.save_dir == cfg.default_dir == video_save.DEFAULT_DIR


def test_save_writes_env_and_keeps_other_lines(muse_root):
    folder = muse_root / "Videos" / "Downloaded"
    cfg = video_save.save(True, str(folder))
    text = (muse_root / ".env").read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_TOKEN=x" in text and "# comment" in text
    assert f"{video_save.ENABLED_KEY}=1" in text
    assert f"{video_save.DIR_KEY}={folder.as_posix()}" in text
    assert cfg.enabled and cfg.custom and folder.is_dir()

    cfg = video_save.save(False, "")
    text = (muse_root / ".env").read_text(encoding="utf-8")
    assert f"{video_save.ENABLED_KEY}=0" in text and video_save.DIR_KEY not in text
    assert not cfg.enabled and cfg.save_dir == video_save.DEFAULT_DIR


def test_relative_folder_is_refused(muse_root):
    with pytest.raises(video_save.VideoSaveError):
        video_save.save(True, "relative/dir")
    with pytest.raises(video_save.VideoSaveError):
        video_save.save(False, "relative/dir")


def test_api_video_save(muse_root):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api.routes.settings import router as settings_router

    app = FastAPI()
    app.include_router(settings_router)
    client = TestClient(app)

    assert client.get("/settings/video-save").json()["enabled"] is True
    folder = muse_root / "out"
    r = client.put("/settings/video-save", json={"enabled": True, "save_dir": str(folder)})
    assert r.status_code == 200 and r.json()["custom"] is True and folder.is_dir()
    r = client.put("/settings/video-save", json={"enabled": True, "save_dir": "nope"})
    assert r.status_code == 400
    r = client.put("/settings/video-save", json={"enabled": False})
    assert r.status_code == 200 and r.json()["enabled"] is False
