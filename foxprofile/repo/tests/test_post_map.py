"""Posting map (profile -> Facebook Page IDs + TikTok account + YouTube channel) and the Muse team
task language."""

import json

import pytest
from fastapi import HTTPException

from src.core import muse_team, post_map


@pytest.fixture()
def root(tmp_path, monkeypatch):
    data = tmp_path / "social_post" / "data"
    data.mkdir(parents=True)
    (tmp_path / "muse_telebot").mkdir()
    monkeypatch.setattr(post_map, "data_dir", lambda: data)
    monkeypatch.setattr(post_map, "config_file", lambda: data / post_map.FILE_NAME)
    monkeypatch.setattr(muse_team, "config_file", lambda: tmp_path / "muse_telebot" / muse_team.FILE_NAME)
    return tmp_path


@pytest.fixture()
def pm(tmp_path, monkeypatch):
    import src.services.profile.manager as mgr_mod

    monkeypatch.setattr(mgr_mod, "DATA_DIR", str(tmp_path / "camoufox_data"))
    monkeypatch.setattr(mgr_mod, "PROFILES_FILE", str(tmp_path / "profiles.json"))
    m = mgr_mod.ProfileManager()
    m.add_profile("p1", "", "windows")
    m.add_profile("p2", "", "windows")
    m.set_auto_post("p1", fanpage=True, tiktok=True, youtube=True)
    return m


def test_save_reads_ids_links_and_names(root):
    (root / "social_post" / "data" / "fb_pages_p1.json").write_text(
        json.dumps([{"name": "Trang A", "asset_id": "123456"}]), encoding="utf-8"
    )
    cfg = post_map.save({
        "p1": {"fanpages": "123456, https://www.facebook.com/profile.php?id=7654321",
               "tiktok": "https://www.tiktok.com/@Abc.Def?lang=vi",
               "youtube": "https://www.youtube.com/@LongTamHoRong/videos"},
        "p2": {"fanpages": "", "tiktok": ""},
    })
    assert cfg.profiles == {"p1": {"fanpages": [{"id": "123456", "name": "Trang A"},
                                                {"id": "7654321", "name": ""}], "tiktok": "abc.def",
                                   "youtube": "LongTamHoRong", "max_per_day": 0, "hours": "", "caption_lang": ""}}


@pytest.mark.parametrize("bad", [
    {"p1": {"fanpages": "123456"}, "p2": {"fanpages": "123456"}},
    {"p1": {"tiktok": "@abc"}, "p2": {"tiktok": "ABC"}},
    {"p1": {"youtube": "@LongTamHoRong"}, "p2": {"youtube": "https://youtube.com/@longtamhorong"}},
    {"p1": {"youtube": "ab"}},
    {"p1": {"youtube": "has space"}},
    {"p1": {"youtube": "@" + "x" * 31}},
    {"p1": {"fanpages": "my page"}},
])
def test_save_refuses_shared_or_bad_targets(root, bad):
    with pytest.raises(post_map.PostMapError):
        post_map.save(bad)
    assert post_map.current().profiles == {}


@pytest.mark.parametrize("raw", [
    "@LongTamHoRong", "LongTamHoRong", " LongTamHoRong ", "https://www.youtube.com/@LongTamHoRong",
    "https://youtube.com/@LongTamHoRong/videos", "youtube.com/@LongTamHoRong?si=x",
])
def test_youtube_handle_keeps_case(raw):
    assert post_map.youtube_handle(raw) == "LongTamHoRong"
    assert post_map.YOUTUBE_RE.match(post_map.youtube_handle(raw))


def test_youtube_handle_rules():
    assert post_map.youtube_handle("") == ""
    assert post_map.youtube_handle(None) == ""
    for ok in ("abc", "a.b_c-d", "x" * 30, "tên", "QuỳnhCosmos"):
        assert post_map.YOUTUBE_RE.match(post_map.youtube_handle(ok))
    # decomposed accents and percent-encoded links come out as the same NFC handle
    assert post_map.youtube_handle("Quỳnh") == "Quỳnh"
    assert post_map.youtube_handle("https://www.youtube.com/@Qu%E1%BB%B3nh") == "Quỳnh"
    for bad in ("ab", "x" * 31, "bad handle", "a/b", "a@b"):
        assert not post_map.YOUTUBE_RE.match(post_map.youtube_handle(bad))


def test_youtube_only_profile_is_kept_and_bad_file_value_dropped(root):
    cfg = post_map.save({"p1": {"youtube": "@ChanA"}})
    assert cfg.profiles["p1"]["youtube"] == "ChanA" and cfg.profiles["p1"]["fanpages"] == []
    saved = json.loads(post_map.config_file().read_text(encoding="utf-8"))
    assert saved["profiles"]["p1"]["youtube"] == "ChanA"
    post_map.config_file().write_text(json.dumps({"profiles": {
        "p1": {"youtube": "bad handle!", "tiktok": "abc"}, "p2": {"youtube": "https://www.youtube.com/@ChanB"},
    }}), encoding="utf-8")
    profiles = post_map.current().profiles
    assert profiles["p1"]["youtube"] == "" and profiles["p2"]["youtube"] == "ChanB"


def test_api_round_trip(root, pm):
    from src.api.routes import settings as routes
    from src.api.schemas.settings import PostMapUpdate

    out = routes.update_post_map(PostMapUpdate(profiles={
        "p1": {"fanpages": ["123456"], "tiktok": "@abc", "youtube": "https://www.youtube.com/@ChanA"},
    }), pm)
    assert out.profiles["p1"].tiktok == "abc" and out.profiles["p1"].youtube == "ChanA"
    row = next(r for r in routes.get_post_map(pm).rows if r.name == "p1")
    assert row.auto_post_fanpage and row.auto_post_tiktok and row.auto_post_youtube
    assert not next(r for r in routes.get_post_map(pm).rows if r.name == "p2").auto_post_youtube
    with pytest.raises(HTTPException):
        routes.update_post_map(PostMapUpdate(profiles={"p1": {"youtube": "a"}}), pm)
    with pytest.raises(HTTPException):
        routes.update_post_map(PostMapUpdate(profiles={"nobody": {"fanpages": "123456"}}), pm)


def test_limits_hours_and_caption_language(root):
    cfg = post_map.save({"p1": {"fanpages": "123456", "max_per_day": "3", "hours": "11-13,22 - 2",
                                "caption_lang": "en"}})
    entry = cfg.profiles["p1"]
    assert (entry["max_per_day"], entry["hours"], entry["caption_lang"]) == (3, "11-13, 22-2", "en")
    for bad in ({"hours": "25-3"}, {"hours": "morning"}, {"max_per_day": 101}, {"caption_lang": "xx"}):
        with pytest.raises(post_map.PostMapError):
            post_map.save({"p1": {"fanpages": "123456", **bad}})


def test_account_check_result_and_summary(root, monkeypatch):
    from src.ui.dialogs.post_map import check_lines

    assert post_map.check_result("p1") is None
    post_map.check_file("p1").write_text(json.dumps({"running": True, "started": 0}), encoding="utf-8")
    assert post_map.check_result("p1")["running"] is False  # never finished: stale
    post_map.check_file("p1").write_text(json.dumps({
        "running": False, "at": "2026-11-06 10:00",
        "fanpage": {"status": "mismatch", "missing": ["999999"], "mapped": ["999999"], "found": []},
        "tiktok": {"status": "mismatch", "account": "other", "expected": "abc"},
    }), encoding="utf-8")
    lines = check_lines(post_map.check_result("p1"))
    assert [ok for ok, _ in lines] == [True, False, False]
    assert "999999" in lines[1][1] and "@other" in lines[2][1]


def test_team_posting_options(root):
    muse_team.save("chief", "a", "manual", {}, [], {}, False, None, None, "auto", "p1")
    cfg = muse_team.current()
    assert (cfg.post_mode, cfg.post_profile) == ("auto", "p1")
    with pytest.raises(muse_team.MuseTeamError):
        muse_team.save("chief", "a", "manual", {}, [], {}, False, None, None, "later")


def test_team_task_language_is_kept_and_checked(root):
    muse_team.save("chief", "a", "manual", {}, [], {}, False, None, "en")
    assert muse_team.current().task_lang == "en"
    muse_team.save("chief", "a", "manual", {}, [], {}, False)  # None keeps it
    assert muse_team.current().task_lang == "en"
    with pytest.raises(muse_team.MuseTeamError):
        muse_team.save("chief", "a", "manual", {}, [], {}, False, None, "xx")


def test_known_tiktok_and_youtube_come_from_the_account_check(root):
    data = root / "social_post" / "data"
    assert post_map.known_tiktok("Muse 9") == "" and post_map.known_youtube("Muse 9") == []
    (data / "tt_account_Muse_9.json").write_text(json.dumps({"at": "x", "account": "@Abc.Def"}), encoding="utf-8")
    (data / "yt_channels_Muse_9.json").write_text(json.dumps({"channels": [
        {"name": "Long Tâm", "handle": "LongTamHoRong"}, {"name": "bad", "handle": "x"}, "junk"]}), encoding="utf-8")
    assert post_map.known_tiktok("Muse 9") == "abc.def"
    assert post_map.known_youtube("Muse 9") == [{"name": "Long Tâm", "handle": "LongTamHoRong"}]
    (data / "yt_channels_Muse_9.json").write_text("not json", encoding="utf-8")
    assert post_map.known_youtube("Muse 9") == []
