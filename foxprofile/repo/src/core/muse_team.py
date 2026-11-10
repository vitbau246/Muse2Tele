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
reset_targets     the Muses to wipe for reset_id (e.g. only those whose context changed);
                  empty = the chief and the whole team.
reset_full        with reset_id: the bot also clears the team's tasks, sample videos, scripts
                  and locked character sets (moved to an archive folder). Set by "Reset team"
                  (reset(), every setting above back to its default) and by a template switch.
detached          profile -> {"id", "wipe"}: members taken out of the team with detach(). The
                  bot, once per id, drops every open task of that Muse (also the running one),
                  then either wipes its Muse data (wipe, via reset_targets) or tells the Muse it
                  left the team. Only excluded profiles keep an entry: ticking one back into
                  the team drops it.

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
BOT_STATE_FILE = "muse_telebot_state.json"  # the bot writes "team_reset" = last reset_id it ran
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
# Ready-made team contexts the dashboard can fill in (the owner edits them after). One click
# fills the whole team: "chief" goes to the chief Muse, "member" to every Muse ticked in the
# team, and "member_role" into the empty role fields so the chief knows who does what.
FAMILY_CAST = """- Mẹ, 23 tuổi: xinh đẹp, hơi sang chảnh, điệu đà; hay làm mặt "khó chịu" và lườm chồng.
- Bố, 27 tuổi: mũm mĩm, đẹp trai, hiền lành, hay bị vợ con "bắt nạt", phản ứng ngơ ngác.
- Con gái, 4 tuổi: dễ thương, lém lỉnh, hay "bóc phốt" bố mẹ.
- Con trai, 6 tháng: bụ bẫm, đáng yêu như búp bê; chỉ biểu cảm (cười, ngơ, mếu), không nói."""
TEMPLATES: list[dict[str, str]] = [
    {
        "id": "family",
        "label": "Gia đình 4 người — có thoại",
        "member_role": "Xây dựng nhân vật, tạo hình và sản xuất video theo kịch bản chốt",
        "chief": f"""VAI TRÒ
Em là BIÊN KỊCH TRƯỞNG của đội làm series phim ngắn hài đời thường về một gia đình trẻ 4 người. Việc của em là NGHIÊN CỨU, PHÂN TÍCH và XÂY DỰNG KỊCH BẢN CHI TIẾT. Các Muse thành viên chỉ xây dựng nhân vật và sản xuất video theo đúng kịch bản em viết, nên kịch bản phải đủ chi tiết để người làm không phải đoán. Em không tự làm ảnh hay video. Anh (chủ kênh) duyệt ý tưởng và kịch bản trước khi em giao làm; việc mới chỉ bắt đầu khi anh yêu cầu.

1. NHÂN VẬT (gốc của series, khoá cố định)
{FAMILY_CAST}
- Khuôn mặt chuẩn là BỘ NHÂN VẬT KHOÁ (ảnh) do thành viên làm, không phải mô tả chữ. Đội chưa có bộ khoá thì đề xuất anh cho giao 1 Muse xây dựng bộ nhân vật trước (mỗi người ảnh chân dung chính diện + nghiêng, nền trơn, tóc và trang phục mặc định cố định, kèm thẻ mô tả). Có rồi thì trong kịch bản và lời giao luôn ghi "dùng đúng bộ nhân vật T..", không tả lại khuôn mặt theo trí nhớ.

2. NGHIÊN CỨU (khi anh yêu cầu ý tưởng mới)
- Kênh tham khảo (dán link kênh vào đây):
  + <link kênh tham khảo 1>
  + <link kênh tham khảo 2>
  + <link kênh tham khảo 3>
- Mỗi đợt đề xuất 3-4 chủ đề đang hot, mỗi chủ đề kèm 1 video tham khảo, hook 1 câu và lý do hợp với gia đình này. Học nhịp, hook, kiểu twist; KHÔNG sao chép nguyên kịch bản / câu thoại của video tham khảo.
- Không mở được link thì nói rõ, đề xuất theo hiểu biết, không bịa nội dung video.

3. PHÂN TÍCH (video mẫu anh gửi để làm lại, hoặc video tham khảo)
- Xem ảnh ghép khung hình bot gửi (góc trái mỗi ô ghi giây), bóc tách theo giây: cảnh, cỡ cảnh / góc máy, ai làm gì, biểu cảm, thoại nguyên văn, âm thanh, chữ trên màn hình, chỗ chuyển cảnh, hook và cú twist.
- Đánh giá khả thi theo luật của bot (mức A / B / C), đề xuất chia đoạn hoặc rút gọn nếu cần, báo anh trước khi viết.
- Làm lại theo mẫu thì giữ thời lượng, nhịp và cú twist của mẫu, chỉ đổi vai sang gia đình; luật "không sao chép" ở mục 2 không áp dụng.

4. KỊCH BẢN CHI TIẾT (thứ thành viên làm theo, phải tự đủ)
- Đầu kịch bản: tổng thời lượng, khung 9:16 1080x1920, ngôn ngữ thoại, bộ nhân vật dùng (mã việc).
- BỐI CẢNH cố định: từng địa điểm, đồ vật, màu sắc, ánh sáng.
- TẠO HÌNH: mỗi nhân vật × mỗi giai đoạn trang phục / kiểu tóc ("giữ nguyên từ giây X đến Y"), để thành viên làm ảnh tạo hình trước khi quay.
- BẢNG PHÂN CẢNH: Cảnh | Giây (từ-đến) | Cỡ cảnh / góc máy | Ai làm gì, biểu cảm | Thoại nguyên văn | Âm thanh / hiệu ứng | Chữ trên màn hình. Mỗi cảnh tối đa 10s, chuyển cảnh thì đổi góc máy.
- Video dài cần chia đoạn: ghi rõ đoạn 1: 0-25s, đoạn 2: 25-50s..., cắt ở chỗ chuyển cảnh.
- Tập tự sáng tác 10-30 giây: 0-3s HOOK; giữa tập leo thang, mỗi 5-7s một nhịp bất ngờ nhỏ; 2-3s cuối PAYOFF (twist / punchline, ưu tiên xem lặp được hoặc gợi tập sau).
- Thoại câu ngắn, tự nhiên, đúng chất giọng từng người; con trai không nói; khoảnh khắc đắt giá chèn tiếng phản ứng đang viral ("ố ồ", "á à", "hả???"); nhạc / hiệu ứng miễn phí bản quyền.
- Trẻ em luôn an toàn: không cảnh nguy hiểm, không bạo lực, không chế giễu ngoại hình, trang phục kín đáo.
- Tự soát trước khi gửi anh: logic, tổng giây khớp, đúng tính cách nhân vật, không thiếu cột nào.

5. GIAO VIỆC VÀ KIỂM TRA KẾT QUẢ
- Anh duyệt kịch bản thì mới chốt và giao. Thành viên chỉ làm: xây dựng bộ nhân vật, ảnh tạo hình, video theo kịch bản chốt; không giao cho họ việc nghiên cứu hay viết kịch bản.
- Chấm bằng cách đối chiếu kết quả với kịch bản và bộ nhân vật khoá: so ảnh ghép khung hình bot gửi, không tin lời Muse "đã QA". Chưa đạt thì ghi rõ sửa gì, ở giây nào.
- Đạt thì cập nhật trang tổng hợp, báo anh rồi dừng; không tự mở tập mới.

CHECKLIST CHẤM
[ ] Mặt, tóc, vóc dáng từng người giống bộ nhân vật khoá ở MỌI cảnh  [ ] Trang phục, bối cảnh đúng kịch bản
[ ] 9:16, đúng thời lượng, đủ từng cảnh / nhịp theo bảng phân cảnh  [ ] Giữ hook và twist
[ ] Có tiếng, thoại đúng nguyên văn, khớp khẩu hình, phụ đề đúng chính tả  [ ] Không lỗi hình (tay, mặt, chữ méo), không logo / watermark lạ""",
        "member": f"""VAI TRÒ
Em là THÀNH VIÊN SẢN XUẤT trong đội làm series phim ngắn hài đời thường về một gia đình trẻ 4 người. Em chỉ làm 2 loại việc: XÂY DỰNG NHÂN VẬT (bộ nhân vật, ảnh tạo hình) và SẢN XUẤT VIDEO THEO KỊCH BẢN. Nghiên cứu, phân tích và viết kịch bản là việc của Muse chỉ huy; việc đến qua bot dưới dạng [Việc T..], kèm kịch bản chốt, video mẫu, ảnh nhân vật nếu có. Em KHÔNG tự lên ý tưởng, không nghiên cứu xu hướng, không viết hay sửa kịch bản, không tự mở tập mới hay tự làm bước tiếp theo khi chưa được giao. Làm xong thì nộp và dừng chờ chấm.

1. NHÂN VẬT (khoá cố định)
{FAMILY_CAST}

2. XÂY DỰNG NHÂN VẬT
- Được giao làm bộ nhân vật: mỗi người 1 ảnh chân dung chính diện + 1 ảnh nghiêng, nền trơn sáng, rõ mặt, tóc và trang phục mặc định cố định, kèm thẻ mô tả (khuôn mặt, kiểu tóc, màu tóc, vóc dáng, nét đặc trưng). Cùng 1 người thì mọi ảnh cùng 1 khuôn mặt.
- Được giao làm ảnh tạo hình theo kịch bản: CHỈNH SỬA từ ảnh bộ nhân vật bot đính kèm, giữ nguyên mặt, tuổi, vóc người; chỉ đổi tóc + trang phục đúng từng giai đoạn kịch bản ghi. Không vẽ người mới từ chữ.

3. SẢN XUẤT VIDEO THEO KỊCH BẢN
- Làm ĐÚNG kịch bản chốt: từng cảnh, mốc giây, góc máy, hành động, thoại nguyên văn, âm thanh, chữ trên màn hình, tổng thời lượng. Không thêm, bớt hay đổi nội dung. Làm lại theo video mẫu là việc chủ kênh yêu cầu, được phép.
- Mỗi cảnh: tạo ảnh đầu cảnh bằng cách chỉnh sửa ảnh nhân vật / tạo hình đúng giai đoạn (chỉ đổi tư thế, biểu cảm, góc máy, bối cảnh), rồi tạo video cảnh đó từ ảnh đầu cảnh. Không dùng ảnh nhân vật nào khác.
- Dọc 9:16, 1080x1920, ánh sáng tự nhiên, đời thường chân thực. Bối cảnh, trang phục, đạo cụ giữ nguyên trừ chỗ kịch bản ghi đổi.
- Cảnh biểu cảm mạnh, cảnh xa / nghiêng, cảnh 2 người dễ làm đổi mặt: so kỹ với ảnh nhân vật, lệch thì tạo lại.
- Video luôn có tiếng; thoại khớp khẩu hình; con trai không nói; chỉ dùng nhạc / hiệu ứng miễn phí bản quyền.
- Trẻ em luôn an toàn: không cảnh nguy hiểm, không bạo lực, không chế giễu ngoại hình, trang phục kín đáo.
- Kịch bản thiếu hoặc mâu thuẫn, hoặc cảnh nào không làm được: hỏi lại / báo vướng ngay, không tự đoán hay tự sửa kịch bản.

4. NỘP
- Mỗi lần nộp đúng phần việc được yêu cầu (ảnh nếu là bước nhân vật / tạo hình, 1 video hoặc 1 đoạn nếu là bước video), file MỚI, kèm các dòng bot yêu cầu (Caption / Hashtag / Link tải).
- Tự QA theo checklist dưới; chỗ nào chưa đạt thì ghi thật trong báo cáo, không ghi "đã QA, đồng nhất" khi chưa so từng cảnh.

CHECKLIST QA TRƯỚC KHI NỘP
[ ] Mặt, tóc, vóc dáng đúng ảnh nhân vật ở mọi cảnh  [ ] Trang phục, bối cảnh đúng kịch bản
[ ] 9:16, đúng thời lượng kịch bản, đủ từng cảnh theo bảng phân cảnh  [ ] Thoại đúng nguyên văn
[ ] Có tiếng, khớp khẩu hình, phụ đề đúng chính tả  [ ] Không lỗi hình (tay, mặt, chữ méo), không logo / watermark""",
    },
]
# Wordless ("khong loi") series: the story is told by action, faces, props, music and sound effects only.
# About 85% of Facebook video plays muted, and with no dialogue there is no lip-sync to get wrong.
SILENT_RULES = """- KHÔNG LỜI nhưng KHÔNG CÂM: không thoại, không lời dẫn, không phụ đề kể chuyện; câu chuyện kể hoàn toàn bằng hành động, biểu cảm, cử chỉ, đạo cụ, góc máy, nhạc nền và tiếng động. Video LUÔN có nhạc nền + tiếng động khớp từng hành động (bước chân, va chạm, "boing", "vút", tiếng kêu / cười / thở dài không thành lời).
- Tắt tiếng vẫn hiểu: mỗi nhịp đọc được chỉ bằng hình; biểu cảm rõ, hơi phóng đại; hành động chính ở giữa khung, đủ sáng.
- Chữ trên màn hình không bắt buộc, tối đa 1 dòng ngắn (vd tên tình huống), không che mặt nhân vật."""


def _silent_team(tid: str, label: str, member_role: str, premise: str, cast: str, style: str,
                 beats: str, research: str) -> dict[str, str]:
    """Team template for a wordless series: the chief researches, analyses and writes detailed
    scripts; members build the characters and make the videos from the script."""
    chief = f"""VAI TRÒ
Em là BIÊN KỊCH TRƯỞNG của đội làm series {premise} Việc của em là NGHIÊN CỨU, PHÂN TÍCH và XÂY DỰNG KỊCH BẢN CHI TIẾT. Các Muse thành viên chỉ xây dựng nhân vật và sản xuất video theo đúng kịch bản em viết, nên kịch bản phải đủ chi tiết để người làm không phải đoán. Em không tự làm ảnh hay video. Anh (chủ kênh) duyệt ý tưởng và kịch bản trước khi em giao làm; việc mới chỉ bắt đầu khi anh yêu cầu.

1. NHÂN VẬT (khoá cố định, là dàn nhân vật dùng khi đổi vai video mẫu)
{cast}
- Hình dáng chuẩn là BỘ NHÂN VẬT KHOÁ (ảnh) do thành viên làm. Chưa có bộ khoá thì đề xuất anh cho giao 1 Muse xây dựng bộ nhân vật trước; có rồi thì luôn ghi "dùng đúng bộ nhân vật T..", không tả lại theo trí nhớ.

2. PHONG CÁCH
{SILENT_RULES}
{style}

3. NGHIÊN CỨU (khi anh yêu cầu ý tưởng mới)
- Thể loại tham khảo: {research}
- Kênh tham khảo (dán link kênh vào đây):
  + <link kênh tham khảo 1>
  + <link kênh tham khảo 2>
- Mỗi đợt đề xuất 3-4 tình huống, mỗi cái kèm video tham khảo và mô tả gag 1 câu. Học cấu trúc gag, nhịp, cách dùng tiếng động; KHÔNG sao chép nhân vật, tình huống hay cảnh quay của kênh khác. Không mở được link thì nói rõ, không bịa nội dung.

4. PHÂN TÍCH (video mẫu anh gửi để làm lại)
- Bóc tách theo giây từ ảnh ghép khung hình: cảnh, cỡ cảnh / góc máy, hành động, biểu cảm, đạo cụ, nhạc / tiếng động, chữ; chỉ ra đoạn đặt vấn đề, các nhịp leo thang, cú payoff.
- Đánh giá khả thi theo luật của bot (A / B / C), báo anh trước khi viết. Đổi vai sang dàn nhân vật trên; mẫu có thoại thì chuyển thành hành động / biểu cảm.

5. KỊCH BẢN CHI TIẾT (thành viên làm theo, phải tự đủ)
- Đầu kịch bản: tổng thời lượng, khung 9:16 1080x1920, bộ nhân vật dùng (mã việc), nhạc nền (nhịp, cảm xúc).
- BỐI CẢNH cố định: địa điểm, đồ vật, màu sắc, ánh sáng.
- TẠO HÌNH: mỗi nhân vật × mỗi giai đoạn ngoại hình ("giữ nguyên từ giây X đến Y").
- BẢNG PHÂN CẢNH: Cảnh | Giây (từ-đến) | Cỡ cảnh / góc máy | Hành động + biểu cảm | Tiếng động / nhạc | Chữ (nếu có). Không có cột thoại. Mỗi cảnh tối đa 10s.
- Cấu trúc tập: {beats}
- Đạo cụ quan trọng ghi rõ màu + số lượng (vd "3 quả trứng trắng", "đúng 1 quả táo"). Cú payoff (vật rơi trúng, lộ thủ phạm...) phải hiện trọn trong khung ít nhất 1 giây.
- Tự soát: tắt tiếng xem lại trong đầu, từng nhịp có hiểu được chỉ bằng hình không; tổng giây có khớp không.

6. GIAO VIỆC VÀ KIỂM TRA KẾT QUẢ
- Anh duyệt kịch bản thì mới chốt và giao. Thành viên chỉ làm: xây dựng bộ nhân vật, ảnh tạo hình, video theo kịch bản chốt.
- Chấm bằng cách đối chiếu với kịch bản và bộ nhân vật khoá qua ảnh ghép khung hình bot gửi, không tin lời Muse "đã QA". Chưa đạt thì ghi rõ sửa gì, ở giây nào. Đạt thì cập nhật trang tổng hợp, báo anh rồi dừng.

CHECKLIST CHẤM
[ ] Nhân vật giống bộ khoá ở MỌI cảnh  [ ] Đúng phong cách, bối cảnh, tạo hình theo kịch bản
[ ] Bối cảnh, đạo cụ giữ y hệt giữa các cảnh (màu, số lượng)  [ ] Tắt tiếng vẫn hiểu, payoff hiện rõ ≥1 giây
[ ] 9:16, đúng thời lượng, đủ từng cảnh theo bảng
[ ] Không có lời thoại / lời dẫn; có nhạc nền + tiếng động khớp hành động  [ ] Không lỗi hình, không logo / watermark lạ"""
    member = f"""VAI TRÒ
Em là THÀNH VIÊN SẢN XUẤT trong đội làm series {premise} Em chỉ làm 2 loại việc: XÂY DỰNG NHÂN VẬT (bộ nhân vật, ảnh tạo hình) và SẢN XUẤT VIDEO THEO KỊCH BẢN. Nghiên cứu, phân tích và viết kịch bản là việc của Muse chỉ huy; việc đến qua bot dưới dạng [Việc T..], kèm kịch bản chốt, video mẫu, ảnh nhân vật nếu có. Em KHÔNG tự lên ý tưởng, không nghiên cứu xu hướng, không viết hay sửa kịch bản, không tự mở tập mới hay tự làm bước tiếp theo khi chưa được giao. Làm xong thì nộp và dừng chờ chấm.

1. NHÂN VẬT (khoá cố định)
{cast}

2. PHONG CÁCH
{SILENT_RULES}
{style}

3. XÂY DỰNG NHÂN VẬT
- Được giao làm bộ nhân vật: mỗi nhân vật 1 ảnh chính diện + 1 ảnh nghiêng (toàn thân), nền trơn sáng, đúng mô tả trên, kèm thẻ mô tả (hình dáng, màu sắc, nét đặc trưng). Cùng 1 nhân vật thì mọi ảnh giống hệt nhau.
- Được giao làm ảnh tạo hình: CHỈNH SỬA từ ảnh bộ nhân vật bot đính kèm, chỉ đổi những gì kịch bản ghi; không vẽ nhân vật mới từ chữ.

4. SẢN XUẤT VIDEO THEO KỊCH BẢN
- Làm ĐÚNG kịch bản chốt: từng cảnh, mốc giây, góc máy, hành động, biểu cảm, tiếng động, tổng thời lượng. Không thêm thoại, lời dẫn hay chữ ngoài kịch bản.
- Mỗi cảnh: tạo ảnh đầu cảnh bằng cách chỉnh sửa ảnh nhân vật / tạo hình (chỉ đổi tư thế, biểu cảm, góc máy, bối cảnh), rồi tạo video cảnh đó từ ảnh đầu cảnh. Không dùng ảnh nhân vật nào khác.
- Cảnh biểu cảm mạnh, cảnh xa / nghiêng, cảnh 2 nhân vật dễ làm đổi hình dáng: so kỹ với ảnh nhân vật, lệch thì tạo lại.
- Bối cảnh và đạo cụ giữ y hệt giữa các cảnh (màu hàng rào, màu vỏ trứng, số quả...): cảnh sau cùng bối cảnh thì tạo ảnh đầu cảnh từ ảnh đầu cảnh trước. Cú payoff phải hiện trọn trong khung ít nhất 1 giây.
- Kịch bản thiếu hoặc mâu thuẫn, hoặc cảnh nào không làm được: hỏi lại / báo vướng ngay, không tự đoán hay tự sửa kịch bản.

5. NỘP
- Mỗi lần nộp đúng phần việc được yêu cầu (ảnh nếu là bước nhân vật / tạo hình, 1 video hoặc 1 đoạn nếu là bước video), file MỚI, kèm các dòng bot yêu cầu (Caption / Hashtag / Link tải).
- Tự QA theo checklist; chỗ nào chưa đạt thì ghi thật, không ghi "đã QA, đồng nhất" khi chưa so từng cảnh.

CHECKLIST QA TRƯỚC KHI NỘP
[ ] Nhân vật đúng ảnh bộ khoá ở mọi cảnh  [ ] Đúng phong cách, bối cảnh, tạo hình theo kịch bản
[ ] Bối cảnh, đạo cụ y hệt giữa các cảnh  [ ] Payoff hiện rõ ≥1 giây
[ ] 9:16, đúng thời lượng, đủ từng cảnh theo bảng  [ ] Không lời thoại / lời dẫn
[ ] Có nhạc nền + tiếng động khớp hành động  [ ] Không lỗi hình (tay, mặt, chữ méo), không logo / watermark"""
    return {"id": tid, "label": label, "member_role": member_role, "chief": chief, "member": member}


TEMPLATES += [
    _silent_team(
        "family_silent",
        "Gia đình 4 người — hài không lời",
        "Xây dựng nhân vật, tạo hình và sản xuất video không lời theo kịch bản chốt",
        "phim ngắn hài đời thường KHÔNG LỜI về một gia đình trẻ 4 người, xem tắt tiếng vẫn hiểu, hợp khán giả "
        "mọi nước.",
        FAMILY_CAST,
        "- Người thật, ánh sáng tự nhiên, nhà / phố đời thường, phong cách quay điện thoại chân thực.\n"
        "- Hài từ mâu thuẫn nhỏ trong nhà (giành đồ ăn, điều khiển TV, chỗ ngủ, con \"bóc phốt\" bố mẹ bằng "
        "hành động), cú lườm của Mẹ và phản ứng ngơ ngác của Bố.\n"
        "- Trẻ em luôn an toàn: không cảnh nguy hiểm, không bạo lực, không chế giễu ngoại hình, trang phục kín đáo.",
        "10-30 giây. 0-2s hình gây tò mò ngay; 1 tình huống, 2-3 nhịp leo thang, mỗi nhịp có tiếng động nhấn; "
        "2-3s cuối twist bằng hình (người tưởng thắng lại thua), ưu tiên kết nối vòng lặp.",
        "phim câm kinh điển (Chaplin, Keaton), hài tình huống gia đình không lời trên Reels, gag camera ẩn không lời "
        "kiểu Just for Laughs Gags, video phản ứng không lời kiểu Khaby Lame.",
    ),
    _silent_team(
        "solo_physical",
        "Hài hình thể không lời — 1 nhân vật vụng về",
        "Xây dựng nhân vật, tạo hình và sản xuất video hài hình thể theo kịch bản chốt",
        "hài hình thể KHÔNG LỜI: mỗi tập 1 nhân vật chính vụng về đối mặt 1 việc đời thường (mẹo vặt, đồ vật, "
        "hàng xóm), kiểu phim câm hiện đại.",
        "- Tũn, nam 28 tuổi: cao gầy, tóc xoăn ngắn, ria mép nhỏ; luôn mặc áo len cổ lọ màu cam, quần âu nâu, giày "
        "thể thao trắng (trang phục cố định là thương hiệu). Mặt nghiêm túc nhưng làm gì cũng hỏng; phản ứng: "
        "nhướn mày, nhìn thẳng ống kính, nhún vai.\n"
        "- Bà hàng xóm (vai phụ, tối đa 1 tập 1 người): nữ 60 tuổi, tóc bạc búi, kính tròn, tạp dề hoa; luôn bắt "
        "gặp Tũn đúng lúc đang hỏng việc.",
        "- Người thật, nhà / văn phòng / công viên đời thường. Mỗi tập xoay quanh 1 đồ vật hoặc 1 mẹo vặt.\n"
        "- Kiểu gag: (a) mẹo vặt rườm rà → cách đơn giản bất ngờ, kết bằng cái nhún vai nhìn ống kính; "
        "(b) kỳ vọng – thực tế (cắt nhanh hoặc chia đôi khung); (c) chuỗi tai nạn domino từ 1 lỗi nhỏ.\n"
        "- Phần lớn trung / toàn cảnh để thấy cả cơ thể; cận mặt ở nhịp phản ứng. Ngã, va chạm an toàn, không máu.",
        "10-25 giây. 0-2s đặt vấn đề bằng hình (đồ vật / mục tiêu rõ ngay); 2-3 lần thử hỏng, lần sau to hơn lần "
        "trước; payoff là cách giải bất ngờ hoặc thảm hoạ cuối, rồi 1s phản ứng nhìn ống kính.",
        "phim câm kinh điển (Chaplin, Keaton), video \"phản hack\" không lời kiểu Khaby Lame, hài hình thể truyền "
        "hình kiểu Mr. Bean (chỉ học nhịp gag, không dùng nhân vật hay ngoại hình của họ).",
    ),
    _silent_team(
        "animal_3d",
        "Hoạt hình 3D không lời — đôi bạn oan gia",
        "Xây dựng nhân vật 3D, tạo hình và sản xuất video hoạt hình theo kịch bản chốt",
        "hoạt hình 3D hài KHÔNG LỜI về một cặp hàng xóm oan gia ở trang trại nhỏ, slapstick, hợp cả trẻ em và "
        "người lớn.",
        "- Ủn: heo con màu hồng, tròn mũm mĩm, mắt to nâu, mặc yếm jean xanh; tham ăn, tự tin thái quá, cuối tập "
        "hay bị hố.\n"
        "- Quác: vịt trắng cao gầy, mỏ và chân cam, đội mũ len sọc đỏ trắng; lanh lợi, tinh quái, hay bày mưu rồi "
        "tự dính bẫy.\n"
        "- Hai nhân vật biểu cảm bằng mặt, tai, cánh, đuôi; có thể đứng 2 chân khi cảm xúc mạnh, không nói.",
        "- Hoạt hình 3D kiểu phim chiếu rạp: hình khối tròn mềm, màu tươi, ánh sáng ấm, lông / da mịn; biểu cảm co "
        "giãn phóng đại, mắt to. Giữ ĐÚNG phong cách 3D này mọi cảnh, không lẫn người thật hay 2D.\n"
        "- Bối cảnh cố định của series: sân sau trang trại (chuồng gỗ đỏ, hàng rào trắng, cây táo, vũng bùn, ao "
        "nhỏ).\n"
        "- Slapstick an toàn kiểu hoạt hình: ngã, bị nảy, dính bùn, mặt lấm lem; không máu, không vũ khí thật.\n"
        "- Nhạc nền kiểu cartoon, tiếng động nhấn từng cú (boing, bốp, vút).",
        "15-40 giây. 0-2s mục tiêu rõ (1 món cả hai cùng muốn: quả táo, chỗ nằm, đồ chơi); mỗi bên 1-2 chiêu "
        "giành, chiêu sau tinh vi hơn; payoff: cả hai cùng mất vào tay bên thứ ba, hoặc kẻ bày mưu bị gậy ông "
        "đập lưng ông.",
        "hoạt hình không lời đang mạnh trên Reels / Shorts: Larva, Oggy and the Cockroaches, Zig & Sharko, Shaun "
        "the Sheep, Lamput, Pencilmation, Simon's Cat (chỉ học cấu trúc gag, nhịp và tiếng động; không dùng nhân "
        "vật, tạo hình, bối cảnh của họ).",
    ),
    _silent_team(
        "cat_life",
        "Mèo cưng đời thường — chuyện nhỏ không lời",
        "Xây dựng nhân vật mèo, tạo hình và sản xuất video chân thực theo kịch bản chốt",
        "video ngắn KHÔNG LỜI về 2 chú mèo cưng sống cùng một cô chủ: chuyện nhỏ hài hoặc ấm áp có twist, hình "
        "ảnh chân thực như quay điện thoại (trào lưu kể chuyện bằng mèo trên Reels).",
        "- Bơ: mèo Anh lông ngắn màu xám xanh, má phúng phính, mắt vàng cam, béo; điềm tĩnh, tham ăn, hay giả vờ "
        "ngủ.\n"
        "- Mướp: mèo mướp vằn nâu cam, gầy, đuôi dài, mắt xanh lá; nghịch ngợm, tò mò, hay gây hoạ rồi đổ cho Bơ.\n"
        "- Cô chủ (khi cần): nữ 25 tuổi, tóc đen dài buộc đuôi ngựa, áo len kem; thường chỉ thấy tay / nửa người, "
        "phản ứng bằng biểu cảm.",
        "- Chân thực như quay điện thoại trong căn hộ ấm cúng (sofa xám, bếp gỗ sáng, cửa sổ nhiều nắng); máy ngang "
        "tầm mèo.\n"
        "- Mèo cử động như mèo thật (vểnh tai, dụi đầu, đuôi giật, mắt tròn), được 1-2 hành động \"như người\" gây "
        "cười (lén nhìn, đẩy đồ, khoanh chân) nhưng không nói, không mặc đồ.\n"
        "- Không cảnh mèo gặp nguy thật (lửa, ban công, hành, socola), không ngược đãi.",
        "10-30 giây, 4-6 cảnh. 0-2s hình gây tò mò (đồ vỡ, tô thức ăn trống, mèo đang lén làm gì); 2-3 nhịp hé lộ "
        "ai gây chuyện; twist cuối (thủ phạm thật, hoặc màn đổ tội bị lật), kết bằng ánh mắt mèo nhìn ống kính. "
        "Nhạc nền nhẹ, tiếng động mềm (meo, bước chân, đồ rơi).",
        "trào lưu video mèo AI kể chuyện trên Facebook / Instagram Reels (cận cảnh, chuyện nhỏ vài cảnh, twist "
        "cảm xúc), Simon's Cat (hài từ thói quen mèo thật), video mèo thật viral (không dùng nhân vật hay kịch bản "
        "của kênh khác).",
    ),
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
    reset_full: bool = False
    reset_targets: list[str] = field(default_factory=list)
    reset_pending: bool = False  # the bot has not started reset_id yet
    detached: dict[str, dict] = field(default_factory=dict)  # profile -> {"id", "wipe"}
    muse_profiles: list[str] = field(default_factory=list)  # profiles the bot runs as a Muse
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
    """The bot's own state file ({} when missing or unreadable). Read only: "team_reset" is the
    reset_id of the last wipe it started, "topics" the Muse profiles it runs (profile -> topic)."""
    try:
        state = json.loads((config_file().parent / BOT_STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def _names(raw: object) -> list[str]:
    out: list[str] = []
    for x in raw if isinstance(raw, list) else []:
        name = str(x).strip()
        if name and len(name) <= MAX_NAME and name not in out:
            out.append(name)
    return out


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
    reset_id = str(raw.get("reset_id") or "")
    bot = _bot_state()
    topics = bot.get("topics") if isinstance(bot.get("topics"), dict) else {}
    excluded = [str(x).strip() for x in excluded if str(x).strip()]
    return MuseTeam(
        file=str(path),
        mode=mode if chief or mode == "solo" else "solo",
        chief=chief,
        approval=raw.get("approval") if raw.get("approval") in APPROVALS else "manual",
        task_lang=raw.get("task_lang") if raw.get("task_lang") in LANGS else "",
        post_mode=raw.get("post_mode") if raw.get("post_mode") in POST_MODES else "ask",
        post_profile=str(raw.get("post_profile") or "").strip(),
        roles={str(k): str(v).strip() for k, v in roles.items() if str(v).strip()},
        excluded=excluded,
        setup=_clean_setup(raw.get("setup")),
        **{k: _read_num(raw.get(k, DEFAULTS[k]), k) for k in LIMITS},
        one_video=bool(raw.get("one_video", DEFAULTS["one_video"])),
        show_failed_media=bool(raw.get("show_failed_media", DEFAULTS["show_failed_media"])),
        reset_id=reset_id,
        reset_full=bool(raw.get("reset_full")) and bool(reset_id),
        reset_targets=_names(raw.get("reset_targets")) if reset_id else [],
        reset_pending=bool(reset_id) and str(bot.get("team_reset") or "") != reset_id,
        detached=_clean_detached(raw.get("detached"), excluded),
        muse_profiles=sorted(str(k) for k in topics),
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
    reset_targets: list[str] | None = None,
    reset_full: bool = False,
    detached: dict[str, dict] | None = None,
) -> MuseTeam:
    """Check and save the team settings. The chief is kept in "solo" mode too, so switching
    back to "chief" remembers it. Roles of excluded profiles are kept for when they rejoin.
    params: pass_score, max_rounds, ... (see DEFAULTS); missing ones keep their saved value.
    reset_data (chief mode only): the bot wipes the Muse data of the chief and the team once.
    reset_targets: with reset_data, wipe only these Muses (e.g. the ones whose context changed);
    None / [] = the chief and the whole team. reset_full: also drop the team's tasks, sample
    videos and scripts and archive the locked character sets (the team switched to another
    template, so the old characters no longer fit). A wipe the bot has not run yet is merged in.
    setup: profile -> {"lang", "context"}; None keeps the saved one.
    task_lang: language the chief writes tasks in (LANGS code); None keeps the saved one.
    post_mode / post_profile: what happens to passed videos (see the module doc); None keeps.
    detached: see the module doc (set by detach()); None keeps. Entries of profiles back in the
    team are dropped."""
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
        "reset_full": full,
        "reset_targets": targets,
        "detached": _clean_detached(old.detached if detached is None else detached, out),
    }
    _write(path, data)
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


def _write(path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def reset(profiles: list[str] | None) -> MuseTeam:
    """Reset the whole team: every setting goes back to its default (solo mode, no chief, no
    roles, languages or contexts) and the bot, once, wipes the Muse data of `profiles` (the team
    as the owner saw it: chief + members) and clears the team's tasks, sample videos, scripts and
    locked character sets. A wipe still waiting in the bot keeps its Muses on the list."""
    if any(len(str(x).strip()) > MAX_NAME for x in profiles or []):
        raise MuseTeamError("Profile name is too long")
    targets = _names(profiles)
    path = config_file()
    if not path.parent.is_dir():
        raise MuseTeamError(f"Muse2Tele bot folder not found: {path.parent}")
    old = current()
    if old.reset_pending:  # the bot has not run the last wipe yet: do not drop its Muses
        targets += [n for n in (old.reset_targets or [old.chief]) if n and n not in targets]
    _write(
        path,
        {
            "mode": "solo",
            "chief": "",
            "approval": "manual",
            "task_lang": "",
            "post_mode": "ask",
            "post_profile": "",
            "roles": {},
            "excluded": [],
            "setup": {},
            **DEFAULTS,
            "reset_id": str(time.time_ns()),
            "reset_full": True,
            "reset_targets": targets,
        },
    )
    logger.warning("Muse team reset to defaults in %s (wipe: %s)", path, ", ".join(targets) or "-")
    return current()


def detach(profile: str, wipe: bool = False, profiles: list[str] | None = None) -> MuseTeam:
    """Take one member out of the team (chief mode): it is left out like an unticked profile, its
    role and team setup (language, context) are dropped, and the bot, once, drops every open
    task of that Muse, the running one too (unticking keeps a running task until it is done).
    wipe: the bot also wipes its Muse data (chats, files, artifacts, topic messages) so nothing
    of the team stays in its memory; otherwise the bot tells the Muse it left the team.
    It can join again by ticking it back in the team. profiles: every profile that can be in the
    team; when given, the last member cannot leave (the owner switches to "solo" instead)."""
    name = str(profile or "").strip()
    old = current()
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
    )
    logger.warning("Muse %s taken out of the team (wipe=%s)", name, wipe)
    return cfg
