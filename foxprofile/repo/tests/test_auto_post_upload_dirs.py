"""Auto-post ticks on a profile and the upload folders saved to .env (Muse2Tele)."""

import json
import os

import pytest

from src.core import upload_dirs


@pytest.fixture()
def pm(tmp_path, monkeypatch):
    import src.services.profile.manager as mgr_mod

    monkeypatch.setattr(mgr_mod, "DATA_DIR", str(tmp_path / "camoufox_data"))
    monkeypatch.setattr(mgr_mod, "PROFILES_FILE", str(tmp_path / "profiles.json"))
    return mgr_mod.ProfileManager()


def test_auto_post_is_saved_reloaded_and_cloned(pm, tmp_path):
    import src.services.profile.manager as mgr_mod

    pm.add_profile("p1", "", "windows")
    assert not pm.profiles["p1"].auto_post_fanpage
    assert pm.set_auto_post("p1", fanpage=True, tiktok=None)
    assert pm.set_auto_post("p1", tiktok=True)
    saved = json.loads((tmp_path / "profiles.json").read_text(encoding="utf-8"))["p1"]
    assert saved["auto_post_fanpage"] is True and saved["auto_post_tiktok"] is True

    again = mgr_mod.ProfileManager()
    assert again.profiles["p1"].auto_post_fanpage and again.profiles["p1"].auto_post_tiktok

    ok, _ = pm.clone_profile("p1", "p2", include_data=False, new_fingerprint=False)
    assert ok and pm.profiles["p2"].auto_post_tiktok
    assert not pm.set_auto_post("missing", fanpage=True)


@pytest.fixture()
def muse_root(tmp_path, monkeypatch):
    """A Muse2Tele-like folder: .env at the root, muse_telebot/, FoxProfile running in foxprofile/data."""
    (tmp_path / "muse_telebot").mkdir()
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=x\n# comment\nMUSE_UPLOAD_DIR=old\n", encoding="utf-8")
    cwd = tmp_path / "foxprofile" / "data"
    cwd.mkdir(parents=True)
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("FOXPROFILE_ENV_FILE", raising=False)
    monkeypatch.delenv(upload_dirs.UPLOAD_DIRS_KEY, raising=False)
    monkeypatch.delenv(upload_dirs.MUSE_DIR_KEY, raising=False)
    return tmp_path


def test_env_file_is_found_above_the_working_directory(muse_root):
    assert upload_dirs.env_file() == (muse_root / ".env").resolve()


def test_save_writes_env_and_environment(muse_root):
    up = muse_root / "Videos" / "downloads"
    muse = up / "bot"
    result = upload_dirs.save([str(up), str(up)], str(muse))
    text = (muse_root / ".env").read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_TOKEN=x" in text and "# comment" in text
    assert f"{upload_dirs.UPLOAD_DIRS_KEY}={up.resolve().as_posix()}" in text
    assert f"{upload_dirs.MUSE_DIR_KEY}={muse.resolve().as_posix()}" in text
    assert text.count(upload_dirs.MUSE_DIR_KEY) == 1
    assert os.environ[upload_dirs.UPLOAD_DIRS_KEY] == up.resolve().as_posix()
    assert result.muse_inside and result.muse_custom and len(result.upload_dirs) == 1
    assert muse.is_dir()


def test_muse_folder_outside_upload_folders_is_refused(muse_root):
    with pytest.raises(upload_dirs.UploadDirsError):
        upload_dirs.save([str(muse_root / "a")], str(muse_root / "b"))
    with pytest.raises(upload_dirs.UploadDirsError):
        upload_dirs.save([], None)
    with pytest.raises(upload_dirs.UploadDirsError):
        upload_dirs.save(["relative/dir"], None)


def test_empty_muse_folder_restores_the_default(muse_root):
    up = muse_root / "Videos" / "downloads"
    result = upload_dirs.save([str(up)], "")
    text = (muse_root / ".env").read_text(encoding="utf-8")
    assert upload_dirs.MUSE_DIR_KEY not in text
    assert not result.muse_custom and result.muse_inside


def test_api_profile_auto_post_and_upload_dirs(pm, muse_root):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api.dependencies import get_browser_launcher, get_event_bus, get_profile_manager
    from src.api.routes.profiles import router as profiles_router
    from src.api.routes.settings import router as settings_router
    from src.core.events import EventBus

    class _Launcher:
        def is_running(self, _name):
            return False

    app = FastAPI()
    app.include_router(profiles_router)
    app.include_router(settings_router)
    app.dependency_overrides[get_profile_manager] = lambda: pm
    app.dependency_overrides[get_browser_launcher] = lambda: _Launcher()
    app.dependency_overrides[get_event_bus] = EventBus
    client = TestClient(app)

    r = client.post("/profiles", json={"name": "fb1", "auto_post_fanpage": True})
    assert r.status_code == 201
    assert r.json()["auto_post_fanpage"] is True and r.json()["auto_post_tiktok"] is False
    r = client.patch("/profiles/fb1", json={"auto_post_tiktok": True})
    assert r.json()["auto_post_fanpage"] is True and r.json()["auto_post_tiktok"] is True

    up = muse_root / "Videos" / "downloads"
    r = client.put("/settings/upload-dirs", json={"upload_dirs": [str(up)], "muse_upload_dir": ""})
    assert r.status_code == 200 and r.json()["muse_inside"] is True
    r = client.put("/settings/upload-dirs", json={"upload_dirs": [], "muse_upload_dir": ""})
    assert r.status_code == 400
    assert client.get("/settings/upload-dirs").json()["bot_installed"] is True
