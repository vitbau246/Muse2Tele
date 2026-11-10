"""Muse team settings: full team reset and the role-specific context templates."""

import json

import pytest

from src.api.routes.settings import reset_muse_team
from src.api.schemas.settings import MuseTeamReset
from src.core import muse_team


@pytest.fixture()
def bot_dir(tmp_path, monkeypatch):
    folder = tmp_path / "muse_telebot"
    folder.mkdir()
    monkeypatch.setattr(muse_team, "config_file", lambda: folder / muse_team.FILE_NAME)
    return folder


def bot_ran(folder, reset_id, topics=("chief1", "muse_a")):
    (folder / muse_team.BOT_STATE_FILE).write_text(
        json.dumps({"team_reset": reset_id, "topics": {n: i for i, n in enumerate(topics)}}),
        encoding="utf-8",
    )


def configured():
    muse_team.save(
        "chief",
        "chief1",
        "auto",
        {"muse_a": "video"},
        ["muse_b"],
        {"pass_score": 9, "one_video": False},
        False,
        {"chief1": {"lang": "vi", "context": "lead"}, "muse_a": {"lang": "en", "context": "make"}},
        "en",
        "auto",
        "muse_a",
    )


def test_reset_puts_every_setting_back_and_asks_for_a_full_wipe(bot_dir):
    configured()
    cfg = muse_team.reset(["chief1", "muse_a"])
    assert (cfg.mode, cfg.chief, cfg.approval, cfg.task_lang) == ("solo", "", "manual", "")
    assert (cfg.post_mode, cfg.post_profile) == ("ask", "")
    assert cfg.roles == {} and cfg.excluded == [] and cfg.setup == {}
    assert cfg.pass_score == muse_team.DEFAULTS["pass_score"] and cfg.one_video is True
    assert cfg.reset_full and cfg.reset_targets == ["chief1", "muse_a"]
    assert cfg.reset_id and cfg.reset_pending


def test_saving_again_keeps_a_full_reset_the_bot_has_not_run(bot_dir):
    first = muse_team.reset(["chief1", "muse_a"])
    # the owner sets the team up again at once, with "wipe on save" ticked for the whole team
    muse_team.save("chief", "chief1", "manual", {}, [], {}, True)
    cfg = muse_team.current()
    assert cfg.reset_id != first.reset_id
    assert cfg.reset_full and cfg.reset_targets == []  # [] = chief + whole team, covers the old list
    # once the bot ran it, a later wipe on save is a plain wipe again
    bot_ran(bot_dir, cfg.reset_id)
    assert not muse_team.current().reset_pending
    muse_team.save("chief", "chief1", "manual", {}, [], {}, True)
    cfg = muse_team.current()
    assert not cfg.reset_full and cfg.reset_targets == []


def test_plain_save_keeps_the_reset_fields(bot_dir):
    first = muse_team.reset(["chief1"])
    muse_team.save("chief", "chief1", "manual", {}, [], {}, False)
    cfg = muse_team.current()
    assert (cfg.reset_id, cfg.reset_full, cfg.reset_targets) == (first.reset_id, True, ["chief1"])


def test_second_reset_keeps_muses_of_a_pending_one(bot_dir):
    muse_team.reset(["chief1", "muse_a"])
    cfg = muse_team.reset(["muse_c"])
    assert cfg.reset_targets == ["muse_c", "chief1", "muse_a"]


def test_muse_profiles_come_from_the_bot_state(bot_dir):
    assert muse_team.current().muse_profiles == []
    bot_ran(bot_dir, "", topics=("muse_a", "chief1"))
    assert muse_team.current().muse_profiles == ["chief1", "muse_a"]


def test_reset_route(bot_dir):
    class PM:
        def list_profiles(self):
            return []

    out = reset_muse_team(MuseTeamReset(profiles=["chief1", " ", "chief1"]), PM())
    assert out.mode == "solo" and out.reset_full and out.reset_targets == ["chief1"]


def test_reset_needs_the_bot_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(muse_team, "config_file", lambda: tmp_path / "missing" / muse_team.FILE_NAME)
    with pytest.raises(muse_team.MuseTeamError):
        muse_team.reset(["chief1"])


def test_template_fills_the_whole_team():
    for tpl in muse_team.TEMPLATES:
        assert {"id", "label", "chief", "member", "member_role"} <= set(tpl)
        for text in (tpl["chief"], tpl["member"]):
            assert len(text) <= muse_team.MAX_CONTEXT
            if tpl["id"].startswith("family"):
                assert "Mẹ, 23 tuổi" in text  # same family on both sides
    family = muse_team.TEMPLATES[0]
    # chief: research, analysis, detailed scripts; members: characters + videos from the script
    assert all(w in family["chief"] for w in ("NGHIÊN CỨU", "PHÂN TÍCH", "KỊCH BẢN CHI TIẾT"))
    assert "không tự làm ảnh hay video" in family["chief"]
    assert all(w in family["member"] for w in ("XÂY DỰNG NHÂN VẬT", "SẢN XUẤT VIDEO THEO KỊCH BẢN"))
    assert "không viết hay sửa kịch bản" in family["member"]


def test_wipe_only_the_muses_whose_context_changed(bot_dir):
    muse_team.save("chief", "chief1", "manual", {}, [], {}, True, None, None, None, None, ["muse_a"])
    cfg = muse_team.current()
    assert cfg.reset_targets == ["muse_a"] and not cfg.reset_full
    # saved again before the bot ran it: both lists are wiped, a template switch adds the team data
    muse_team.save("chief", "chief1", "manual", {}, [], {}, True, None, None, None, None, ["muse_b"], True)
    cfg = muse_team.current()
    assert cfg.reset_targets == ["muse_b", "muse_a"] and cfg.reset_full
    # an empty list means the chief and the whole team, which covers any list
    muse_team.save("chief", "chief1", "manual", {}, [], {}, True)
    assert muse_team.current().reset_targets == []
    bot_ran(bot_dir, muse_team.current().reset_id)
    muse_team.save("chief", "chief1", "manual", {}, [], {}, True, None, None, None, None, ["muse_c"])
    cfg = muse_team.current()
    assert cfg.reset_targets == ["muse_c"] and not cfg.reset_full


def test_every_template_fits_and_wordless_ones_say_so():
    ids = [t["id"] for t in muse_team.TEMPLATES]
    assert len(ids) == len(set(ids))
    for tpl in muse_team.TEMPLATES[1:]:
        for text in (tpl["chief"], tpl["member"]):
            assert len(text) <= muse_team.MAX_CONTEXT and "KHÔNG LỜI" in text


class _PM:
    def __init__(self, *names):
        self.names = names

    def list_profiles(self):
        return [type("P", (), {"name": n})() for n in self.names]


def test_detach_leaves_the_member_out_and_drops_its_role_and_setup(bot_dir):
    configured()
    cfg = muse_team.detach("muse_a")
    assert "muse_a" in cfg.excluded and "muse_b" in cfg.excluded
    assert "muse_a" not in cfg.roles and "muse_a" not in cfg.setup and "chief1" in cfg.setup
    assert cfg.detached["muse_a"]["id"] and cfg.detached["muse_a"]["wipe"] is False
    assert not cfg.reset_pending and cfg.reset_id == ""  # no wipe asked
    assert (cfg.mode, cfg.chief, cfg.pass_score, cfg.post_mode) == ("chief", "chief1", 9, "auto")


def test_detach_with_wipe_asks_the_bot_to_wipe_only_that_muse(bot_dir):
    configured()
    cfg = muse_team.detach("muse_c", wipe=True)
    assert cfg.reset_pending and cfg.reset_targets == ["muse_c"] and not cfg.reset_full
    assert cfg.detached["muse_c"]["wipe"] is True


def test_ticking_a_detached_member_back_drops_the_entry(bot_dir):
    configured()
    first = muse_team.detach("muse_a").detached["muse_a"]["id"]
    muse_team.save("chief", "chief1", "auto", {}, ["muse_b", "muse_a"], {}, False)
    assert muse_team.current().detached["muse_a"]["id"] == first  # plain save keeps it
    muse_team.save("chief", "chief1", "auto", {}, ["muse_b"], {}, False)
    assert muse_team.current().detached == {}


def test_detach_refuses_the_chief_outsiders_and_solo_mode(bot_dir):
    configured()
    for name in ("chief1", "muse_b", " "):
        with pytest.raises(muse_team.MuseTeamError):
            muse_team.detach(name)
    muse_team.save("solo", "chief1", "manual", {}, [], {}, False)
    with pytest.raises(muse_team.MuseTeamError):
        muse_team.detach("muse_a")


def test_detach_route(bot_dir):
    from fastapi import HTTPException

    from src.api.routes.settings import detach_muse_team_member
    from src.api.schemas.settings import MuseTeamDetach

    configured()
    pm = _PM("chief1", "muse_a", "muse_b", "muse_c")
    out = detach_muse_team_member(MuseTeamDetach(profile="muse_c", wipe=True), pm)
    assert "muse_c" in out.excluded and out.detached["muse_c"]["wipe"] and out.reset_targets == ["muse_c"]
    with pytest.raises(HTTPException) as e:  # muse_a is the last member left
        detach_muse_team_member(MuseTeamDetach(profile="muse_a"), pm)
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        detach_muse_team_member(MuseTeamDetach(profile="nobody"), pm)
    assert e.value.status_code == 404
