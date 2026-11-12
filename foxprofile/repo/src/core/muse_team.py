"""Muse teams for the Muse2Tele bot, kept in muse_telebot/muse_team.json.

The file holds several teams ({"version": 2, "teams": [...]}); each team works in its own
Telegram group (the bot links a group to a team with /setup in that group). A file from the
single-team version (the team settings at the top level) is read as the default team.

id        team id (the default team is "default"; new teams get a short generated id).
name      name shown on the dashboard and in Telegram.
default   exactly one team: it gets every profile no other team lists (new profiles join it).
profiles  profiles in this team's group (each gets a topic there); null on the default team
          (= every profile not listed by another team). A profile is in one team at most.
mode      "solo": every Muse works on its own in its topic.
          "chief": one Muse (chief) answers in the group's General topic, hands out tasks to the
          other Muses, follows their progress and rates their work. The bot carries the messages.
chief     profile name of the chief Muse (required in "chief" mode).
task_lang language the chief writes tasks in for the team (code from LANGS, "" = no rule);
          a member with its own language (setup) gets tasks in that language instead.
approval  "manual": the owner presses Send / Drop in General before each task reaches a Muse.
          "auto": tasks go out as soon as the chief writes them.
roles     profile -> what that Muse is good at; the bot briefs the chief with it.
excluded  profiles of the group left out of the team: they keep their topic, but the chief is
          not told about them and cannot give them tasks.
pass_score / max_rounds / max_new_per_hour / quiet_minutes / overdue_minutes: review settings.
setup     profile -> {"lang": code, "context": text}: language the Muse answers in and the
          long-term context (who it is, the story world, rules) the bot sends it once,
          and again whenever it changes or after a wipe. Chief included.

Skill (skill pack, see SKILLS below): ready-made contexts plus the settings of one kind of work.
skill     id of the skill pack the team was set up from ("" = none / hand-written contexts).
features  bot workflows the team uses: "video" = sample videos, technical video checks, the
          look stage, multi-video / segment tasks, captions and posting of passed videos.
          Without it the bot runs the plain task / review loop only.
one_video, show_failed_media, post_mode, post_profile: video settings, set from the skill pack
          (one_video: one video at a time; show_failed_media: also post work that has not
          passed; post_mode "off" / "ask" (Post buttons) / "auto" (queue for post_profile)).

reset_id / reset_targets / reset_full / detached: one-shot orders for the bot (wipe Muse data,
full team reset, member taken out), each run once per id; see save(), reset(), detach().

The bot reads the file on every use, so a change applies at once without restarting it.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .logging import get_logger
from .upload_dirs import env_file

logger = get_logger("muse_team")

FILE_NAME = "muse_team.json"
FILE_VERSION = 2
BOT_STATE_FILE = "muse_telebot_state.json"  # the bot writes "team_reset" = last reset_id it ran
DEFAULT_TEAM = "default"
DEFAULT_TEAM_NAME = "Đội 1"
MAX_TEAMS = 20
MAX_TEAM_NAME = 60
MODES = ("solo", "chief")
APPROVALS = ("manual", "auto")
POST_MODES = ("off", "ask", "auto")
MAX_NAME = 100
MAX_ROLE = 300
MAX_CONTEXT = 6000
# Language a Muse answers in ("" = no rule, follows the messages it gets).
LANGS = {
    "": "Mặc định (theo tin nhắn)",
    "vi": "Tiếng Việt",
    "en": "English",
    "zh": "中文",
    "ja": "日本語",
    "ko": "한국어",
    "th": "ไทย",
    "id": "Bahasa Indonesia",
}

# ---------- skill packs ----------
# A skill pack = ready-made contexts for one kind of team work plus the settings that go with
# it, as one JSON file (format 1):
#   {"format": 1, "id": "family", "label": "...", "description": "...", "version": "1.0.0",
#    "author": "...", "license": "free" | "paid" | ..., "category": "video" | "general" | ...,
#    "features": ["video"], "settings": {"one_video": true, "show_failed_media": false,
#    "post_mode": "ask"}, "member_role": "...", "chief": "<context for the chief>",
#    "member": "<context for every member>", "order": 10}
# Built-in packs ship in src/core/skills/; packs the owner installs (bought, shared, own) go to
# muse_telebot/skills/ (not tracked by git). One click fills the whole team: "chief" goes to the
# chief Muse, "member" to every member, "member_role" into the empty role fields.
SKILL_FORMAT = 1
FEATURES = ("video",)
VIDEO = "video"
VIDEO_KEYS = ("one_video", "show_failed_media", "post_mode")
VIDEO_DEFAULTS = {"one_video": True, "show_failed_media": False, "post_mode": "ask"}
BUILTIN_SKILLS = Path(__file__).with_name("skills")
USER_SKILLS = "skills"  # folder next to muse_team.json
SKILL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
SKILL_TEXT_MAX = {"label": 80, "description": 600, "version": 20, "author": 80, "license": 30,
                  "category": 30, "homepage": 300, "price": 40}


class MuseTeamError(ValueError):
    """The requested team settings cannot be used."""


def _clean_settings(raw: object) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in (raw.items() if isinstance(raw, dict) else []):
        if key in ("one_video", "show_failed_media"):
            out[key] = bool(value)
        elif key == "post_mode" and value in POST_MODES:
            out[key] = value
    return out


def clean_skill(raw: object, source: str = "user") -> dict:
    """Check a skill pack (dict from its JSON file) and return it with only the known fields.
    Raises MuseTeamError when it cannot be used."""
    if not isinstance(raw, dict):
        raise MuseTeamError("A skill pack must be a JSON object")
    if int(raw.get("format") or SKILL_FORMAT) > SKILL_FORMAT:
        raise MuseTeamError("This skill pack needs a newer Muse2Tele")
    sid = str(raw.get("id") or "").strip()
    if not SKILL_ID_RE.match(sid):
        raise MuseTeamError("Skill id: 1-40 lowercase letters, digits, - or _")
    out: dict = {"format": SKILL_FORMAT, "id": sid, "source": source}
    for key, limit in SKILL_TEXT_MAX.items():
        value = " ".join(str(raw.get(key) or "").split())
        if len(value) > limit:
            raise MuseTeamError(f"Skill {sid}: {key} is longer than {limit} characters")
        out[key] = value
    if not out["label"]:
        raise MuseTeamError(f"Skill {sid}: label is missing")
    for key in ("chief", "member"):
        text = "\n".join(str(raw.get(key) or "").splitlines()).strip()
        if not text:
            raise MuseTeamError(f"Skill {sid}: {key} context is missing")
        if len(text) > MAX_CONTEXT:
            raise MuseTeamError(f"Skill {sid}: {key} context is longer than {MAX_CONTEXT} characters")
        out[key] = text
    role = " ".join(str(raw.get("member_role") or "").split())
    if len(role) > MAX_ROLE:
        raise MuseTeamError(f"Skill {sid}: member_role is longer than {MAX_ROLE} characters")
    out["member_role"] = role
    feats = raw.get("features") if isinstance(raw.get("features"), list) else []
    out["features"] = [f for f in FEATURES if f in feats]
    out["settings"] = {**(VIDEO_DEFAULTS if VIDEO in out["features"] else {}), **_clean_settings(raw.get("settings"))}
    try:
        out["order"] = int(raw.get("order") or 100)
    except (TypeError, ValueError):
        out["order"] = 100
    out["license"] = out["license"] or "free"
    return out


def user_skills_dir() -> Path:
    return config_file().parent / USER_SKILLS


def load_skills() -> list[dict]:
    """Built-in packs, then installed ones (an installed pack cannot take a built-in id)."""
    found: dict[str, dict] = {}
    for folder, source in ((BUILTIN_SKILLS, "builtin"), (user_skills_dir(), "user")):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json")):
            try:
                pack = clean_skill(json.loads(path.read_text(encoding="utf-8")), source)
            except (OSError, ValueError) as e:
                logger.warning("Skill pack %s skipped: %s", path, e)
                continue
            if pack["id"] in found:
                logger.warning("Skill pack %s skipped: id %s is taken", path, pack["id"])
                continue
            found[pack["id"]] = pack
    return sorted(found.values(), key=lambda p: (p["order"], p["label"]))


TEMPLATES: list[dict] = []  # skill packs, refreshed by skills() (kept for the desktop dialog)


def skills() -> list[dict]:
    TEMPLATES[:] = load_skills()
    return TEMPLATES


def skill(skill_id: str) -> dict | None:
    return next((p for p in skills() if p["id"] == skill_id), None) if skill_id else None


def install_skill(raw: object) -> dict:
    """Install a skill pack (bought / shared / own) into muse_telebot/skills/<id>.json. Installing
    a pack with the same id again updates it; built-in ids cannot be replaced."""
    pack = clean_skill(raw, "user")
    old = next((p for p in skills() if p["id"] == pack["id"]), None)
    if old and old["source"] == "builtin":
        raise MuseTeamError(f"Skill id {pack['id']} belongs to a built-in pack: choose another id")
    folder = user_skills_dir()
    if not folder.parent.is_dir():
        raise MuseTeamError(f"Muse2Tele bot folder not found: {folder.parent}")
    folder.mkdir(exist_ok=True)
    data = {k: v for k, v in pack.items() if k != "source"}
    _write(folder / f"{pack['id']}.json", data)
    logger.info("Skill pack %s %s (%s)", pack["id"], "updated" if old else "installed", pack["label"])
    skills()
    return pack


def remove_skill(skill_id: str) -> None:
    pack = next((p for p in skills() if p["id"] == skill_id), None)
    if not pack:
        raise MuseTeamError(f"Skill pack not found: {skill_id}")
    if pack["source"] == "builtin":
        raise MuseTeamError("Built-in skill packs cannot be removed")
    (user_skills_dir() / f"{skill_id}.json").unlink(missing_ok=True)
    logger.info("Skill pack %s removed", skill_id)
    skills()


# Same defaults and limits as muse_telebot/muse_team.py (the bot clamps values it reads too).
DEFAULTS = {
    "pass_score": 8,
    "max_rounds": 3,
    "max_new_per_hour": 20,
    "quiet_minutes": 3,
    "overdue_minutes": 30,
    "one_video": True,
    "show_failed_media": False,
}
LIMITS = {
    "pass_score": (1, 10),
    "max_rounds": (1, 10),
    "max_new_per_hour": (1, 200),
    "quiet_minutes": (1, 60),
    "overdue_minutes": (5, 600),
}
LABELS = {
    "pass_score": "Pass score",
    "max_rounds": "Redo rounds",
    "max_new_per_hour": "New tasks per hour",
    "quiet_minutes": "Quiet minutes",
    "overdue_minutes": "Overdue minutes",
}
_KEEP = object()


@dataclass
class MuseTeam:
    file: str
    id: str = DEFAULT_TEAM
    name: str = DEFAULT_TEAM_NAME
    is_default: bool = True
    profiles: list[str] | None = None  # None: default team (every profile no other team lists)
    mode: str = "solo"
    chief: str = ""
    approval: str = "manual"
    task_lang: str = ""
    post_mode: str = "ask"
    post_profile: str = ""
    roles: dict[str, str] = field(default_factory=dict)
    excluded: list[str] = field(default_factory=list)
    setup: dict[str, dict[str, str]] = field(default_factory=dict)
    pass_score: int = DEFAULTS["pass_score"]
    max_rounds: int = DEFAULTS["max_rounds"]
    max_new_per_hour: int = DEFAULTS["max_new_per_hour"]
    quiet_minutes: int = DEFAULTS["quiet_minutes"]
    overdue_minutes: int = DEFAULTS["overdue_minutes"]
    one_video: bool = DEFAULTS["one_video"]
    show_failed_media: bool = DEFAULTS["show_failed_media"]
    skill: str = ""
    features: list[str] = field(default_factory=list)
    reset_id: str = ""
    reset_full: bool = False
    reset_targets: list[str] = field(default_factory=list)
    reset_pending: bool = False  # the bot has not started reset_id yet
    detached: dict[str, dict] = field(default_factory=dict)  # profile -> {"id", "wipe"}
    muse_profiles: list[str] = field(default_factory=list)  # profiles the bot runs as a Muse in this team
    group: int | None = None  # Telegram group the bot linked to this team
    group_title: str = ""
    teams: list[dict] = field(default_factory=list)  # every team, short: id, name, default, group...
    assigned: dict[str, str] = field(default_factory=dict)  # profile -> id of the team that lists it
    bot_installed: bool = False


def _read_num(raw: object, key: str) -> int:
    lo, hi = LIMITS[key]
    try:
        value = int(float(raw))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return int(DEFAULTS[key])
    return min(hi, max(lo, value))


def _clean_setup(raw: object) -> dict[str, dict[str, str]]:
    """{profile: {"lang", "context"}} with unknown languages dropped and empty entries left out."""
    out: dict[str, dict[str, str]] = {}
    for name, item in (raw.items() if isinstance(raw, dict) else []):
        if not isinstance(item, dict):
            continue
        lang = str(item.get("lang") or "").strip()
        context = "\n".join(str(item.get("context") or "").splitlines()).strip()
        lang = lang if lang in LANGS else ""
        if str(name).strip() and (lang or context):
            out[str(name).strip()] = {"lang": lang, "context": context}
    return out


def _clean_detached(raw: object, excluded: list[str]) -> dict[str, dict]:
    """{profile: {"id", "wipe"}} for profiles still left out of the team."""
    out: dict[str, dict] = {}
    for name, item in (raw.items() if isinstance(raw, dict) else []):
        name = str(name).strip()
        if isinstance(item, dict) and str(item.get("id") or "") and name in excluded:
            out[name] = {"id": str(item["id"]), "wipe": bool(item.get("wipe"))}
    return out


def config_file():
    return env_file().parent / "muse_telebot" / FILE_NAME


def _bot_state() -> dict:
    """The bot's own state file ({} when missing or unreadable). Read only."""
    try:
        state = json.loads((config_file().parent / BOT_STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def _bot_team(state: dict, team_id: str) -> dict:
    """The bot's state of one team: "group", "group_title", "topics" (profile -> topic),
    "team_reset" (reset_id of the last wipe it started). The single-team bot kept them at the
    top level (= the default team)."""
    teams = state.get("teams")
    if isinstance(teams, dict):
        item = teams.get(team_id)
        return item if isinstance(item, dict) else {}
    return state if team_id == DEFAULT_TEAM else {}


def _names(raw: object) -> list[str]:
    out: list[str] = []
    for x in raw if isinstance(raw, list) else []:
        name = str(x).strip()
        if name and len(name) <= MAX_NAME and name not in out:
            out.append(name)
    return out


def _guess_skill(raw: dict) -> str:
    """Skill a single-team file was set up from: the pack whose chief context the chief has."""
    chief = str(raw.get("chief") or "").strip()
    ctx = str(((raw.get("setup") or {}).get(chief) or {}).get("context") or "").strip() if chief else ""
    return next((p["id"] for p in load_skills() if ctx and ctx == p["chief"].strip()), "")


def _raw_teams() -> list[dict]:
    """Teams as saved (the single-team file becomes the default team). Always one default."""
    try:
        raw = json.loads(config_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    if isinstance(raw.get("teams"), list):
        teams = [dict(t) for t in raw["teams"] if isinstance(t, dict) and str(t.get("id") or "").strip()]
    elif raw:
        # single-team file: it ran the video workflow, keep it on
        teams = [{**raw, "id": DEFAULT_TEAM, "name": DEFAULT_TEAM_NAME, "default": True, "profiles": None,
                  "skill": raw.get("skill", _guess_skill(raw)), "features": raw.get("features", [VIDEO])}]
    else:
        teams = []
    unique: dict[str, dict] = {}
    for t in teams:
        unique.setdefault(str(t["id"]).strip(), t)
    teams = list(unique.values())
    if not teams:
        teams = [{"id": DEFAULT_TEAM, "name": DEFAULT_TEAM_NAME, "default": True, "profiles": None}]
    lead = next((t for t in teams if t.get("default")), teams[0])
    for t in teams:
        t["id"] = str(t["id"]).strip()
        t["default"] = t is lead
        if t["default"]:
            t["profiles"] = None
        else:
            t["profiles"] = _names(t.get("profiles"))
    return teams


def _assigned(teams: list[dict]) -> dict[str, str]:
    """profile -> team id, for profiles a (non-default) team lists."""
    out: dict[str, str] = {}
    for t in teams:
        for name in t.get("profiles") or []:
            out.setdefault(name, t["id"])
    return out


def _find(teams: list[dict], team_id: str | None) -> dict:
    if not team_id:
        return next(t for t in teams if t["default"])
    team = next((t for t in teams if t["id"] == team_id), None)
    if team is None:
        raise MuseTeamError(f"Team not found: {team_id}")
    return team


def _summary(t: dict, bot: dict) -> dict:
    mine = _bot_team(bot, t["id"])
    topics = mine.get("topics") if isinstance(mine.get("topics"), dict) else {}
    chief = str(t.get("chief") or "").strip()
    return {
        "id": t["id"],
        "name": str(t.get("name") or t["id"]),
        "default": bool(t["default"]),
        "mode": t.get("mode") if t.get("mode") in MODES and chief else "solo",
        "chief": chief,
        "skill": str(t.get("skill") or ""),
        "profiles": t.get("profiles"),
        "group": mine.get("group"),
        "group_title": str(mine.get("group_title") or ""),
        "muse_profiles": sorted(str(k) for k in topics),
    }


def current(team_id: str | None = None) -> MuseTeam:
    """Settings of one team (the default team when team_id is empty)."""
    path = config_file()
    teams = _raw_teams()
    raw = _find(teams, team_id)
    roles = raw.get("roles") if isinstance(raw.get("roles"), dict) else {}
    excluded = raw.get("excluded") if isinstance(raw.get("excluded"), list) else []
    chief = str(raw.get("chief") or "").strip()
    mode = raw.get("mode") if raw.get("mode") in MODES else "solo"
    reset_id = str(raw.get("reset_id") or "")
    bot = _bot_state()
    mine = _bot_team(bot, raw["id"])
    topics = mine.get("topics") if isinstance(mine.get("topics"), dict) else {}
    excluded = [str(x).strip() for x in excluded if str(x).strip()]
    feats = raw.get("features") if isinstance(raw.get("features"), list) else []
    group = mine.get("group")
    return MuseTeam(
        file=str(path),
        id=raw["id"],
        name=str(raw.get("name") or raw["id"])[:MAX_TEAM_NAME],
        is_default=raw["default"],
        profiles=raw["profiles"],
        mode=mode if chief or mode == "solo" else "solo",
        chief=chief,
        approval=raw.get("approval") if raw.get("approval") in APPROVALS else "manual",
        task_lang=raw.get("task_lang") if raw.get("task_lang") in LANGS else "",
        post_mode=raw.get("post_mode") if raw.get("post_mode") in POST_MODES else VIDEO_DEFAULTS["post_mode"],
        post_profile=str(raw.get("post_profile") or "").strip(),
        roles={str(k): str(v).strip() for k, v in roles.items() if str(v).strip()},
        excluded=excluded,
        setup=_clean_setup(raw.get("setup")),
        **{k: _read_num(raw.get(k, DEFAULTS[k]), k) for k in LIMITS},
        one_video=bool(raw.get("one_video", DEFAULTS["one_video"])),
        # a team without the video workflow posts every result at once (no hold for review)
        show_failed_media=bool(raw.get("show_failed_media", DEFAULTS["show_failed_media"] if VIDEO in feats else True)),
        skill=str(raw.get("skill") or ""),
        features=[f for f in FEATURES if f in feats],
        reset_id=reset_id,
        reset_full=bool(raw.get("reset_full")) and bool(reset_id),
        reset_targets=_names(raw.get("reset_targets")) if reset_id else [],
        reset_pending=bool(reset_id) and str(mine.get("team_reset") or "") != reset_id,
        detached=_clean_detached(raw.get("detached"), excluded),
        muse_profiles=sorted(str(k) for k in topics),
        group=group if isinstance(group, int) else None,
        group_title=str(mine.get("group_title") or ""),
        teams=[_summary(t, bot) for t in teams],
        assigned=_assigned(teams),
        bot_installed=path.parent.is_dir(),
    )


def _write(path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _store(teams: list[dict]) -> None:
    path = config_file()
    if not path.parent.is_dir():
        raise MuseTeamError(f"Muse2Tele bot folder not found: {path.parent}")
    _write(path, {"version": FILE_VERSION, "teams": teams})


def _clean_name(name: object) -> str:
    text = " ".join(str(name or "").split())
    if not text:
        raise MuseTeamError("Give the team a name")
    if len(text) > MAX_TEAM_NAME:
        raise MuseTeamError(f"Team name is longer than {MAX_TEAM_NAME} characters")
    return text


def _check_profiles(teams: list[dict], team: dict, profiles: list[str]) -> list[str]:
    """Profiles a non-default team lists: not listed by another team."""
    if any(len(str(x).strip()) > MAX_NAME for x in profiles):
        raise MuseTeamError("Profile name is too long")
    names = _names(profiles)
    taken = {n: t for t in teams if t["id"] != team["id"] for n in t.get("profiles") or []}
    clash = next((n for n in names if n in taken), None)
    if clash:
        raise MuseTeamError(f"{clash[:40]} is already in team {str(taken[clash].get('name') or '')[:40]}")
    return names


def save(
    mode: str,
    chief: str | None,
    approval: str,
    roles: dict[str, str] | None,
    excluded: list[str] | None = None,
    params: dict[str, object] | None = None,
    reset_data: bool = False,
    setup: dict[str, dict[str, str]] | None = None,
    task_lang: str | None = None,
    post_mode: str | None = None,
    post_profile: str | None = None,
    reset_targets: list[str] | None = None,
    reset_full: bool = False,
    detached: dict[str, dict] | None = None,
    *,
    team_id: str | None = None,
    name: str | None = None,
    profiles: object = _KEEP,
    skill_id: str | None = None,
    features: list[str] | None = None,
) -> MuseTeam:
    """Check and save the settings of one team (the default team when team_id is empty). The
    chief is kept in "solo" mode too, so switching back to "chief" remembers it. Roles of
    excluded profiles are kept for when they rejoin.
    params: pass_score, max_rounds, ..., one_video, show_failed_media; missing ones keep their
    saved value (or take the new skill pack's settings when skill_id changes).
    reset_data (chief mode only): the bot wipes the Muse data of the chief and the team once.
    reset_targets: with reset_data, wipe only these Muses (e.g. the ones whose context changed);
    None / [] = the chief and the whole team. reset_full: also drop the team's tasks, sample
    videos and scripts and archive the locked character sets (the team switched to another
    template, so the old characters no longer fit). A wipe the bot has not run yet is merged in.
    setup: profile -> {"lang", "context"}; None keeps the saved one.
    task_lang: language the chief writes tasks in (LANGS code); None keeps the saved one.
    post_mode / post_profile: what happens to passed videos (see the module doc); None keeps.
    detached: see the module doc (set by detach()); None keeps. Entries of profiles back in the
    team are dropped.
    name: team name; None keeps. profiles: profiles in the team's group (not on the default
    team); left out keeps. skill_id: skill pack id ("" = none); None keeps. features: bot
    workflows (FEATURES); None keeps, or takes the pack's when skill_id changes."""
    if mode not in MODES:
        raise MuseTeamError(f"mode must be one of {', '.join(MODES)}")
    if approval not in APPROVALS:
        raise MuseTeamError(f"approval must be one of {', '.join(APPROVALS)}")
    chief = (chief or "").strip()
    if len(chief) > MAX_NAME:
        raise MuseTeamError("Chief profile name is too long")
    if mode == "chief" and not chief:
        raise MuseTeamError("Choose the profile that leads the team")
    clean: dict[str, str] = {}
    for pname, role in (roles or {}).items():
        pname, role = str(pname).strip(), " ".join(str(role or "").split())
        if not pname or not role or pname == chief:
            continue
        if len(pname) > MAX_NAME or len(role) > MAX_ROLE:
            raise MuseTeamError(f"Role of {pname[:40]} is longer than {MAX_ROLE} characters")
        clean[pname] = role
    out: list[str] = []
    for pname in excluded or []:
        pname = str(pname).strip()
        if len(pname) > MAX_NAME:
            raise MuseTeamError("Profile name is too long")
        if pname and pname != chief and pname not in out:
            out.append(pname)
    if post_mode is not None and post_mode not in POST_MODES:
        raise MuseTeamError(f"post_mode must be one of {', '.join(POST_MODES)}")
    if post_profile is not None and len(post_profile) > MAX_NAME:
        raise MuseTeamError("Profile name is too long")
    if task_lang is not None and task_lang not in LANGS:
        raise MuseTeamError(f"Unknown task language: {task_lang}")
    if setup is not None:
        for pname, item in setup.items():
            if not isinstance(item, dict):
                raise MuseTeamError(f"Setup of {str(pname)[:40]} must be an object")
            if str(item.get("lang") or "") not in LANGS:
                raise MuseTeamError(f"Unknown language for {str(pname)[:40]}: {item.get('lang')}")
            if len(str(item.get("context") or "")) > MAX_CONTEXT:
                raise MuseTeamError(f"Context of {str(pname)[:40]} is longer than {MAX_CONTEXT} characters")
    if features is not None and any(f not in FEATURES for f in features):
        raise MuseTeamError(f"features must be among {', '.join(FEATURES)}")
    path = config_file()
    if not path.parent.is_dir():
        raise MuseTeamError(f"Muse2Tele bot folder not found: {path.parent}")
    teams = _raw_teams()
    team = _find(teams, team_id)
    old = current(team["id"])
    new_name = old.name if name is None else _clean_name(name)
    if profiles is _KEEP or team["default"]:
        members = team["profiles"]
    else:
        members = _check_profiles(teams, team, list(profiles or []))  # type: ignore[call-overload]
    others = _assigned([t for t in teams if t["id"] != team["id"]])
    if chief and chief in others:
        raise MuseTeamError(f"{chief[:40]} is in another team: it cannot lead this one")
    if chief and members is not None and chief not in members:
        members = members + [chief]
    pack = None
    new_skill = old.skill if skill_id is None else str(skill_id).strip()
    if new_skill and new_skill != old.skill:
        pack = skill(new_skill)
        if not pack:
            raise MuseTeamError(f"Skill pack not found: {new_skill}")
    if features is None:
        features = list(pack["features"]) if pack else list(old.features)
    values: dict[str, object] = {}
    for key, (lo, hi) in LIMITS.items():
        raw = (params or {}).get(key, getattr(old, key))
        try:
            num = int(raw)  # type: ignore[call-overload]
        except (TypeError, ValueError):
            raise MuseTeamError(f"{LABELS[key]} must be a whole number") from None
        if not lo <= num <= hi:
            raise MuseTeamError(f"{LABELS[key]} must be between {lo} and {hi}")
        values[key] = num
    preset = pack["settings"] if pack else {}
    for key in ("one_video", "show_failed_media"):
        values[key] = bool((params or {}).get(key, preset.get(key, getattr(old, key))))
    if post_mode is None:
        post_mode = str(preset.get("post_mode") or old.post_mode)
    if any(len(str(x).strip()) > MAX_NAME for x in reset_targets or []):
        raise MuseTeamError("Profile name is too long")
    reset_id, full, targets = old.reset_id, old.reset_full, old.reset_targets
    if reset_data and mode == "chief":
        reset_id = str(time.time_ns())
        full, targets = bool(reset_full), _names(reset_targets)
        if old.reset_pending:  # the bot has not run the last wipe yet: this one must cover it too
            full = full or old.reset_full
            # [] means the whole team, so it wins over any list
            if targets and old.reset_targets:
                targets += [n for n in old.reset_targets if n not in targets]
            else:
                targets = []
    data = {
        "id": team["id"],
        "name": new_name,
        "default": team["default"],
        "profiles": members,
        "mode": mode,
        "chief": chief,
        "approval": approval,
        "task_lang": old.task_lang if task_lang is None else task_lang,
        "post_mode": post_mode,
        "post_profile": old.post_profile if post_profile is None else post_profile.strip(),
        "roles": clean,
        "excluded": out,
        "setup": old.setup if setup is None else _clean_setup(setup),
        **values,
        "skill": new_skill,
        "features": [f for f in FEATURES if f in features],
        "reset_id": reset_id,
        "reset_full": full,
        "reset_targets": targets,
        "detached": _clean_detached(old.detached if detached is None else detached, out),
    }
    teams[teams.index(team)] = data
    _store(teams)
    logger.info(
        "Muse team %s saved to %s (mode=%s, chief=%s, approval=%s, skill=%s, pass=%s, reset=%s)",
        team["id"],
        path,
        mode,
        chief,
        approval,
        new_skill or "-",
        values["pass_score"],
        reset_id != old.reset_id,
    )
    return current(team["id"])


def create_team(name: str, profiles: list[str] | None = None) -> MuseTeam:
    """Add a team (solo, no skill yet). The bot links it to a Telegram group with /setup there."""
    teams = _raw_teams()
    if len(teams) >= MAX_TEAMS:
        raise MuseTeamError(f"At most {MAX_TEAMS} teams")
    tid = "t" + format(time.time_ns() // 1000, "x")[-8:]
    while any(t["id"] == tid for t in teams):
        tid = "t" + format(time.time_ns(), "x")[-8:]
    team = {"id": tid, "name": _clean_name(name), "default": False, "profiles": []}
    team["profiles"] = _check_profiles(teams, team, list(profiles or []))
    teams.append({**team, "mode": "solo", "approval": "manual", **{k: DEFAULTS[k] for k in LIMITS},
                  "skill": "", "features": []})
    _store(teams)
    logger.info("Muse team %s created (%s)", tid, team["name"])
    return current(tid)


def delete_team(team_id: str) -> MuseTeam:
    """Remove a team. Its profiles go back to the default team; the bot stops using its group."""
    teams = _raw_teams()
    team = _find(teams, team_id)
    if team["default"]:
        raise MuseTeamError("The default team cannot be removed")
    teams.remove(team)
    _store(teams)
    logger.warning("Muse team %s (%s) removed", team["id"], team.get("name"))
    return current()


def reset(profiles: list[str] | None, team_id: str | None = None) -> MuseTeam:
    """Reset one team: every setting goes back to its default (solo mode, no chief, no roles,
    languages, contexts or skill pack; its name and profiles stay) and the bot, once, wipes the
    Muse data of `profiles` (the team as the owner saw it: chief + members) and clears the team's
    tasks, sample videos, scripts and locked character sets. A wipe still waiting in the bot keeps
    its Muses on the list."""
    if any(len(str(x).strip()) > MAX_NAME for x in profiles or []):
        raise MuseTeamError("Profile name is too long")
    targets = _names(profiles)
    if not config_file().parent.is_dir():
        raise MuseTeamError(f"Muse2Tele bot folder not found: {config_file().parent}")
    teams = _raw_teams()
    team = _find(teams, team_id)
    old = current(team["id"])
    if old.reset_pending:  # the bot has not run the last wipe yet: do not drop its Muses
        targets += [n for n in (old.reset_targets or [old.chief]) if n and n not in targets]
    teams[teams.index(team)] = {
        "id": team["id"],
        "name": old.name,
        "default": team["default"],
        "profiles": team["profiles"],
        "mode": "solo",
        "chief": "",
        "approval": "manual",
        "task_lang": "",
        "post_mode": VIDEO_DEFAULTS["post_mode"],
        "post_profile": "",
        "roles": {},
        "excluded": [],
        "setup": {},
        **DEFAULTS,
        "skill": "",
        "features": [],
        "reset_id": str(time.time_ns()),
        "reset_full": True,
        "reset_targets": targets,
    }
    _store(teams)
    logger.warning("Muse team %s reset to defaults (wipe: %s)", team["id"], ", ".join(targets) or "-")
    return current(team["id"])


def detach(profile: str, wipe: bool = False, profiles: list[str] | None = None,
           team_id: str | None = None) -> MuseTeam:
    """Take one member out of the team (chief mode): it is left out like an unticked profile, its
    role and team setup (language, context) are dropped, and the bot, once, drops every open
    task of that Muse, the running one too (unticking keeps a running task until it is done).
    wipe: the bot also wipes its Muse data (chats, files, artifacts, topic messages) so nothing
    of the team stays in its memory; otherwise the bot tells the Muse it left the team.
    It can join again by ticking it back in the team. profiles: every profile that can be in the
    team; when given, the last member cannot leave (the owner switches to "solo" instead)."""
    name = str(profile or "").strip()
    old = current(team_id)
    if old.mode != "chief":
        raise MuseTeamError("The team has no chief: there is no team to leave")
    if not name or len(name) > MAX_NAME:
        raise MuseTeamError("Choose the Muse to take out of the team")
    if name == old.chief:
        raise MuseTeamError(f"{name[:40]} is the chief: choose another chief first")
    if name in old.excluded:
        raise MuseTeamError(f"{name[:40]} is not in the team")
    if profiles is not None and not [n for n in profiles if n not in (old.chief, name) and n not in old.excluded]:
        raise MuseTeamError(f"{name[:40]} is the last member: switch the team to Independent instead")
    cfg = save(
        old.mode,
        old.chief,
        old.approval,
        {k: v for k, v in old.roles.items() if k != name},
        old.excluded + [name],
        None,
        wipe,
        {k: v for k, v in old.setup.items() if k != name},
        reset_targets=[name] if wipe else None,
        detached={**old.detached, name: {"id": str(time.time_ns()), "wipe": bool(wipe)}},
        team_id=old.id,
    )
    logger.warning("Muse %s taken out of team %s (wipe=%s)", name, old.id, wipe)
    return cfg


def team_profiles(team: MuseTeam, all_profiles: list[str]) -> list[str]:
    """Profiles in the team's group: its list, or (default team) every profile no other team lists."""
    if team.profiles is not None:
        return [n for n in all_profiles if n in team.profiles] + [
            n for n in team.profiles if n not in all_profiles and n in team.muse_profiles]
    return [n for n in all_profiles if n not in team.assigned]


skills()
