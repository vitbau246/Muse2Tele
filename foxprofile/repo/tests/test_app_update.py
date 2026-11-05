"""Muse2Tele self-update wrapper: off outside Muse2Tele, cached check, apply refuses while busy."""

import json
import time

import pytest

from src.core import app_update


def test_not_supported_outside_muse2tele(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert app_update.root() is None
    assert app_update.status() == {"supported": False, "available": False}
    with pytest.raises(RuntimeError):
        app_update.apply()


@pytest.fixture()
def fake_root(tmp_path, monkeypatch):
    (tmp_path / "start_all.bat").write_text("@echo off\n")
    (tmp_path / "updater.py").write_text(
        "CALLS = []\n"
        "def check(root):\n"
        "    CALLS.append(1)\n"
        "    return {'available': True, 'remote': {'sha': 'abc', 'date': '2026-01-02T03:04:05Z', 'message': 'm'}}\n"
    )
    data = tmp_path / "foxprofile" / "data"
    data.mkdir(parents=True)
    monkeypatch.chdir(data)
    monkeypatch.setattr(app_update, "_cache", None)
    return tmp_path


def test_status_uses_updater_and_reports_last_run(fake_root):
    assert app_update.root() == fake_root.resolve()
    st = app_update.status()
    assert st["supported"] and st["available"] and st["remote"]["sha"] == "abc"
    assert st["last_update"] is None and st["busy"] is False

    (fake_root / ".update").mkdir()
    (fake_root / ".update" / "status.json").write_text(
        json.dumps({"state": "applying", "message": "x", "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    )
    assert app_update.busy()
    with pytest.raises(RuntimeError):
        app_update.apply()

    old = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 3600))
    (fake_root / ".update" / "status.json").write_text(json.dumps({"state": "applying", "at": old}))
    assert not app_update.busy()  # a run that died long ago no longer blocks


def test_update_routes(fake_root):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api.routes.update import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    r = client.get("/update")
    assert r.status_code == 200 and r.json()["available"] is True
