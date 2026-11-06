"""Muse team mode for the Muse2Tele bot, kept in muse_telebot/muse_team.json.

mode      "solo": every Muse works on its own in its topic.
          "chief": one Muse (chief) answers in the group's General topic, hands out tasks to the
          other Muses, follows their progress and rates their work. The bot carries the messages.
chief     profile name of the chief Muse (required in "chief" mode).
task_lang language the chief writes tasks in for the team (code from LANGS, "" = no rule);
          a member with its own language (setup) gets tasks in that language instead.
post_mode "off": passed videos only go to the Muse's topic. "ask": the bot shows a Post button
          per channel of the posting map (social_post/data/post_map.json) in General. "auto": the
          bot queues passed videos for post_profile at once (asks when it has none).
post_profile  default channel: the profile whose posting queue gets passed videos.
approval  "manual": the owner presses Send / Drop in General before each task reaches a Muse.
          "auto": tasks go out as soon as the chief writes them.
roles     profile -> what that Muse is good at; the bot briefs the chief with it.
excluded  profiles left out of the team: the chief is not told about them and cannot give
          them tasks. Every other profile with a topic is in the team (new profiles join).
pass_score        lowest score (out of 10) that passes; below it the bot sends the chief's
                  notes back for a redo on its own.
max_rounds        redo rounds per task (per video for video tasks); then the owner is asked.
max_new_per_hour  new tasks the chief may hand out per hour.
quiet_minutes     a working Muse that is idle and silent this long without saying it is done
                  is reminded once, then reported to the chief.
overdue_minutes   tasks still running after this long are flagged in Telegram.
one_video         video tasks are made and sent to the chief one video at a time; the next
                  video starts only after the previous one passes.
show_failed_media also post images / videos that have not passed yet to Telegram (off: only
                  the text result and fail count until the work passes).
setup     profile -> {"lang": code, "context": text}: language the Muse answers in and the
          long-term context (who it is, the story world, rules) the bot sends it once,
          and again whenever it changes or after a wipe. Chief included.
reset_id          set to a new value when the owner asks to wipe the Muse data of the chief
                  and the team on save; the bot resets each of them once per value.

The bot reads the file on every use, so a change applies at once without restarting it.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

from .logging import get_logger
from .upload_dirs import env_file

logger = get_logger("muse_team")

FILE_NAME = "muse_team.json"
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
# Ready-made contexts the dashboard can fill in (the owner edits them after).
TEMPLATES: list[dict[str, str]] = [
    {
        "id": "family_comedy",
        "label": "Phim ngắn gia đình hài (đạo diễn, 9:16)",
        "text": """VAI TRÒ
Em là đạo diễn kiêm nhà sản xuất phim ngắn chuyên nghiệp, làm series phim ngắn đời thường hài hước về một gia đình trẻ 4 người. Anh giao toàn quyền sáng tạo và quyết định cho em, trong phạm vi các luật dưới đây. Trước khi nộp, em tự đọc lại kịch bản và tự QA đầu ra để không còn lỗi vặt.

1. NHÂN VẬT (khóa cố định, không tự đổi)
- Mẹ, 23 tuổi: xinh đẹp, hơi sang chảnh, điệu đà; hay làm mặt "khó chịu" và lườm chồng.
- Bố, 27 tuổi: mũm mĩm, đẹp trai, hiền lành, hay bị vợ con "bắt nạt", phản ứng ngơ ngác.
- Con gái, 4 tuổi: dễ thương, lém lỉnh, hay "bóc phốt" bố mẹ.
- Con trai, 6 tháng: bụ bẫm, đáng yêu như búp bê; chỉ biểu cảm (cười, ngơ, mếu), không nói.
Tập đầu tiên (hoặc khi anh yêu cầu): làm BỘ NHÂN VẬT CHUẨN gồm tên gọi cố định, ảnh chân dung từng người (chính diện + nghiêng) và thẻ mô tả cố định (khuôn mặt, kiểu tóc, màu tóc, vóc dáng, nét đặc trưng). Mọi tập sau đều tham chiếu đúng bộ này, không tả lại theo trí nhớ.

2. CẤU TRÚC MỖI TẬP (10-30 giây)
- 0-3s HOOK: mở bằng câu nói/hành động gây tò mò hoặc mâu thuẫn ngay khung hình đầu, không giới thiệu dài.
- Giữa tập: đẩy tình huống leo thang (mỗi 5-7s có một nhịp bất ngờ nhỏ) để giữ người xem.
- 2-3s cuối PAYOFF: cú twist / punchline, ưu tiên kết có thể xem lặp (loop) hoặc gợi tập sau.
- Tập dưới 15s: chỉ cần hook + 1 twist. Tập 30s: hook + 2 nhịp leo thang + twist.

3. HÌNH ẢNH
- Khung dọc 9:16, 1080x1920, ánh sáng tự nhiên, phong cách đời thường chân thực.
- Trong 1 tập: bối cảnh, trang phục, đạo cụ giữ nguyên từ đầu đến cuối.
- Mỗi cảnh tối đa 10s. Chuyển cảnh thì đổi góc máy (toàn - trung - cận, hoặc góc khác) và QA khung hình đầu của cảnh mới: đúng nhân vật, đúng trang phục, đúng bối cảnh, không méo mặt/tay.
- Trẻ em luôn an toàn: không cảnh nguy hiểm, không bạo lực, không chế giễu ngoại hình, trang phục kín đáo.

4. ÂM THANH
- Lời thoại tiếng Việt, câu ngắn, tự nhiên, đúng chất giọng từng nhân vật.
- Ở khoảnh khắc đắt giá: chèn tiếng phản ứng đang viral ("ố ồ", "á à", "hả???"...) chọn kiểu hài/phổ biến nhất, kết hợp biểu cảm mặt méo, cười nhạt, đứng hình.
- Không dùng nhạc có bản quyền; dùng nhạc nền/hiệu ứng miễn phí bản quyền.

5. NGHIÊN CỨU XU HƯỚNG
- Tham khảo video viral cùng thể loại từ các kênh sau (dán link kênh tham khảo vào đây):
  + <link kênh tham khảo 1>
  + <link kênh tham khảo 2>
  + <link kênh tham khảo 3>
- Mỗi đợt: chọn 3-4 chủ đề đang hot, mỗi chủ đề lấy 1 video làm cảm hứng; học nhịp, hook, kiểu twist, KHÔNG sao chép nguyên kịch bản/câu thoại.
- Không mở được link (cần đăng nhập...) thì nói rõ, đề xuất chủ đề hot theo hiểu biết của em, không bịa nội dung video.

6. QUY TRÌNH MỖI TẬP
B1. Đề xuất ý tưởng: chủ đề, video tham khảo, hook 1 câu.
B2. Kịch bản phân cảnh dạng bảng: Cảnh | Thời lượng | Góc máy | Hành động | Thoại | Âm thanh/hiệu ứng.
B3. Tự soát lỗi kịch bản (logic, thời lượng, đúng tính cách nhân vật).
B4. Làm video, QA theo checklist bên dưới, sửa xong mới nộp.
B5. Nộp: video + 3 dòng Link tải / Caption / Hashtag.

CHECKLIST QA TRƯỚC KHI NỘP
[ ] Nhân vật đúng bộ chuẩn (mặt, tóc, vóc dáng)  [ ] Trang phục, bối cảnh đồng nhất cả tập
[ ] 9:16, 1080x1920, tổng 10-30s, mỗi cảnh ≤10s  [ ] Có hook trong 3s đầu, có twist cuối
[ ] Thoại tiếng Việt rõ, khớp khẩu hình, không lỗi chính tả phụ đề  [ ] Không lỗi hình (tay, mặt, chữ méo)""",
    },
]
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


class MuseTeamError(ValueError):
    """The requested team settings cannot be used."""


@dataclass
class MuseTeam:
    file: str
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
    reset_id: str = ""
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


def config_file():
    return env_file().parent / "muse_telebot" / FILE_NAME


def current() -> MuseTeam:
    path = config_file()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    roles = raw.get("roles") if isinstance(raw.get("roles"), dict) else {}
    excluded = raw.get("excluded") if isinstance(raw.get("excluded"), list) else []
    chief = str(raw.get("chief") or "").strip()
    mode = raw.get("mode") if raw.get("mode") in MODES else "solo"
    return MuseTeam(
        file=str(path),
        mode=mode if chief or mode == "solo" else "solo",
        chief=chief,
        approval=raw.get("approval") if raw.get("approval") in APPROVALS else "manual",
        task_lang=raw.get("task_lang") if raw.get("task_lang") in LANGS else "",
        post_mode=raw.get("post_mode") if raw.get("post_mode") in POST_MODES else "ask",
        post_profile=str(raw.get("post_profile") or "").strip(),
        roles={str(k): str(v).strip() for k, v in roles.items() if str(v).strip()},
        excluded=[str(x).strip() for x in excluded if str(x).strip()],
        setup=_clean_setup(raw.get("setup")),
        **{k: _read_num(raw.get(k, DEFAULTS[k]), k) for k in LIMITS},
        one_video=bool(raw.get("one_video", DEFAULTS["one_video"])),
        show_failed_media=bool(raw.get("show_failed_media", DEFAULTS["show_failed_media"])),
        reset_id=str(raw.get("reset_id") or ""),
        bot_installed=path.parent.is_dir(),
    )


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
) -> MuseTeam:
    """Check and save the team settings. The chief is kept in "solo" mode too, so switching
    back to "chief" remembers it. Roles of excluded profiles are kept for when they rejoin.
    params: pass_score, max_rounds, ... (see DEFAULTS); missing ones keep their saved value.
    reset_data (chief mode only): the bot wipes the Muse data of the chief and the team once.
    setup: profile -> {"lang", "context"}; None keeps the saved one.
    task_lang: language the chief writes tasks in (LANGS code); None keeps the saved one.
    post_mode / post_profile: what happens to passed videos (see the module doc); None keeps."""
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
    for name, role in (roles or {}).items():
        name, role = str(name).strip(), " ".join(str(role or "").split())
        if not name or not role or name == chief:
            continue
        if len(name) > MAX_NAME or len(role) > MAX_ROLE:
            raise MuseTeamError(f"Role of {name[:40]} is longer than {MAX_ROLE} characters")
        clean[name] = role
    out: list[str] = []
    for name in excluded or []:
        name = str(name).strip()
        if len(name) > MAX_NAME:
            raise MuseTeamError("Profile name is too long")
        if name and name != chief and name not in out:
            out.append(name)
    if post_mode is not None and post_mode not in POST_MODES:
        raise MuseTeamError(f"post_mode must be one of {', '.join(POST_MODES)}")
    if post_profile is not None and len(post_profile) > MAX_NAME:
        raise MuseTeamError("Profile name is too long")
    if task_lang is not None and task_lang not in LANGS:
        raise MuseTeamError(f"Unknown task language: {task_lang}")
    if setup is not None:
        for name, item in setup.items():
            if not isinstance(item, dict):
                raise MuseTeamError(f"Setup of {str(name)[:40]} must be an object")
            if str(item.get("lang") or "") not in LANGS:
                raise MuseTeamError(f"Unknown language for {str(name)[:40]}: {item.get('lang')}")
            if len(str(item.get("context") or "")) > MAX_CONTEXT:
                raise MuseTeamError(f"Context of {str(name)[:40]} is longer than {MAX_CONTEXT} characters")
    path = config_file()
    if not path.parent.is_dir():
        raise MuseTeamError(f"Muse2Tele bot folder not found: {path.parent}")
    old = current()
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
    for key in ("one_video", "show_failed_media"):
        values[key] = bool((params or {}).get(key, getattr(old, key)))
    reset_id = old.reset_id
    if reset_data and mode == "chief":
        reset_id = str(time.time_ns())
    data = {
        "mode": mode,
        "chief": chief,
        "approval": approval,
        "task_lang": old.task_lang if task_lang is None else task_lang,
        "post_mode": old.post_mode if post_mode is None else post_mode,
        "post_profile": old.post_profile if post_profile is None else post_profile.strip(),
        "roles": clean,
        "excluded": out,
        "setup": old.setup if setup is None else _clean_setup(setup),
        **values,
        "reset_id": reset_id,
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    logger.info(
        "Muse team saved to %s (mode=%s, chief=%s, approval=%s, pass=%s, reset=%s)",
        path,
        mode,
        chief,
        approval,
        values["pass_score"],
        reset_id != old.reset_id,
    )
    return current()
