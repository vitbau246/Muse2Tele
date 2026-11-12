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
    for tpl in muse_team.skills():
        assert {"id", "label", "chief", "member", "member_role", "features", "settings"} <= set(tpl)
        for text in (tpl["chief"], tpl["member"]):
            assert len(text) <= muse_team.MAX_CONTEXT
            if tpl["id"].startswith("family"):
                assert "Mẹ, 23 tuổi" in text  # same family on both sides
    family = muse_team.skill("family")
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
    assert {"family", "family_silent", "solo_physical", "animal_3d", "cat_life", "general"} <= set(ids)
    for tpl in muse_team.TEMPLATES:
        if tpl["id"] in ("family", "general"):
            continue
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


# ---------- several teams (one Telegram group each) and skill packs ----------


def test_single_team_file_is_read_as_the_default_team(bot_dir):
    (bot_dir / muse_team.FILE_NAME).write_text(
        json.dumps({"mode": "chief", "chief": "chief1", "one_video": False, "post_mode": "auto"}), encoding="utf-8"
    )
    cfg = muse_team.current()
    assert (cfg.id, cfg.is_default, cfg.profiles) == (muse_team.DEFAULT_TEAM, True, None)
    assert (cfg.mode, cfg.chief, cfg.one_video, cfg.post_mode) == ("chief", "chief1", False, "auto")
    assert cfg.features == ["video"]  # the single-team bot always ran the video workflow
    muse_team.save("chief", "chief1", "manual", {}, [], {}, False)
    saved = json.loads((bot_dir / muse_team.FILE_NAME).read_text(encoding="utf-8"))
    assert saved["version"] == 2 and [t["id"] for t in saved["teams"]] == [muse_team.DEFAULT_TEAM]


def test_bot_state_of_the_single_group_bot_belongs_to_the_default_team(bot_dir):
    bot_ran(bot_dir, "r1", topics=("muse_a",))
    cfg = muse_team.current()
    assert cfg.muse_profiles == ["muse_a"]
    (bot_dir / muse_team.BOT_STATE_FILE).write_text(json.dumps({"teams": {
        "default": {"topics": {"muse_a": 1}, "group": -100, "group_title": "Nhom 1"},
        "t2": {"topics": {"muse_b": 2}, "group": -200, "team_reset": "x"}}}), encoding="utf-8")
    team2 = muse_team.create_team("Second", ["muse_b"])
    assert muse_team.current().group_title == "Nhom 1"
    assert muse_team.current(team2.id).muse_profiles == []  # state of another id


def test_teams_split_the_profiles(bot_dir):
    second = muse_team.create_team("Đội 2", ["muse_b", "muse_c"])
    assert second.profiles == ["muse_b", "muse_c"] and not second.is_default
    default = muse_team.current()
    assert default.assigned == {"muse_b": second.id, "muse_c": second.id}
    names = ["chief1", "muse_a", "muse_b", "muse_c", "muse_d"]
    assert muse_team.team_profiles(default, names) == ["chief1", "muse_a", "muse_d"]
    assert muse_team.team_profiles(muse_team.current(second.id), names) == ["muse_b", "muse_c"]
    # a profile is in one team only, and cannot lead a team it is not in
    with pytest.raises(muse_team.MuseTeamError):
        muse_team.create_team("Đội 3", ["muse_b"])
    with pytest.raises(muse_team.MuseTeamError):
        muse_team.save("chief", "muse_b", "manual", {}, [], {}, False)
    # the chief joins its team's group
    cfg = muse_team.save("chief", "muse_d", "auto", {}, [], {}, False, team_id=second.id, name="Video",
                         profiles=["muse_b"])
    assert cfg.profiles == ["muse_b", "muse_d"] and cfg.name == "Video" and cfg.chief == "muse_d"
    assert "muse_c" not in muse_team.current().assigned  # unticked: back to the default team
    # teams keep their own settings
    assert muse_team.current().mode == "solo"
    removed = muse_team.delete_team(second.id)
    assert removed.is_default and [t["id"] for t in removed.teams] == [muse_team.DEFAULT_TEAM]
    with pytest.raises(muse_team.MuseTeamError):
        muse_team.delete_team(muse_team.DEFAULT_TEAM)


def test_unknown_team_is_an_error(bot_dir):
    with pytest.raises(muse_team.MuseTeamError):
        muse_team.current("nope")


def test_skill_pack_sets_the_video_settings(bot_dir):
    cfg = muse_team.save("chief", "chief1", "manual", {}, [], {}, False, skill_id="general")
    assert cfg.skill == "general" and cfg.features == []
    assert (cfg.one_video, cfg.show_failed_media, cfg.post_mode) == (False, True, "off")
    cfg = muse_team.save("chief", "chief1", "manual", {}, [], {}, False, skill_id="family")
    assert cfg.features == ["video"] and (cfg.one_video, cfg.show_failed_media, cfg.post_mode) == (True, False, "ask")
    # the owner's own choice wins over the pack's settings, and a plain save keeps them
    cfg = muse_team.save("chief", "chief1", "manual", {}, [], {"one_video": False}, False, post_mode="auto")
    assert (cfg.skill, cfg.one_video, cfg.post_mode) == ("family", False, "auto")
    with pytest.raises(muse_team.MuseTeamError):
        muse_team.save("chief", "chief1", "manual", {}, [], {}, False, skill_id="missing")


def test_install_and_remove_a_skill_pack(bot_dir):
    pack = {"id": "shop_review", "label": "Review sản phẩm", "chief": "lead", "member": "make",
            "features": ["video", "bogus"], "settings": {"post_mode": "auto", "x": 1}, "license": "paid"}
    got = muse_team.install_skill(pack)
    assert got["source"] == "user" and got["features"] == ["video"]
    assert got["settings"] == {"one_video": True, "show_failed_media": False, "post_mode": "auto"}
    assert (bot_dir / "skills" / "shop_review.json").is_file()
    assert muse_team.skill("shop_review")["license"] == "paid"
    with pytest.raises(muse_team.MuseTeamError):  # built-in ids are taken
        muse_team.install_skill({**pack, "id": "family"})
    with pytest.raises(muse_team.MuseTeamError):
        muse_team.install_skill({**pack, "chief": ""})
    with pytest.raises(muse_team.MuseTeamError):
        muse_team.remove_skill("family")
    muse_team.remove_skill("shop_review")
    assert muse_team.skill("shop_review") is None


def test_team_routes(bot_dir):
    from src.api.routes.settings import create_muse_team, get_muse_team, update_muse_team
    from src.api.schemas.settings import MuseTeamCreate, MuseTeamUpdate

    pm = _PM("chief1", "muse_a", "muse_b")
    made = create_muse_team(MuseTeamCreate(name="Đội ảnh", team_profiles=["muse_b"]), pm)
    assert made.name == "Đội ảnh" and made.group_profiles == ["muse_b"] and len(made.teams) == 2
    out = update_muse_team(MuseTeamUpdate(mode="solo", team_profiles=["muse_a", "muse_b"], skill="general"), pm,
                           made.id)
    assert out.team_profiles == ["muse_a", "muse_b"] and out.skill == "general"
    default = get_muse_team(pm)
    assert default.group_profiles == ["chief1"] and default.assigned == {"muse_a": made.id, "muse_b": made.id}
