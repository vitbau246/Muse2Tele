# Muse2tele — Dùng Muse ngay trên Telegram

![Muse2tele — Dùng Muse AI ngay trên Telegram](docs/promo.svg)

> ❤️ **Ủng hộ dự án:** nếu Muse2tele giúp ích cho bạn, hãy ghé **[sanhdieu247.xyz](https://sanhdieu247.xyz)** để ủng
> hộ và theo dõi các bản cập nhật mới.

Muse2tele nối các tài khoản **Muse (muse.ai)** của bạn với **một nhóm Telegram**:

- Mỗi profile trong FoxProfile (mỗi tài khoản Muse) có **một topic riêng** trong nhóm.
- Bạn nhắn tin, gửi ảnh/video/file vào topic, bot gõ vào Muse giúp bạn.
- Câu trả lời của Muse (chữ, ảnh, video, file, nút bấm) tự hiện lại trong topic đó.
- Tạo profile mới và đăng nhập Muse xong là **bot tự tạo topic**, bạn không phải làm gì thêm.

> ⚠️ **Không dùng Muse bằng IP Việt Nam.** Muse có thể chặn hoặc khoá tài khoản. Mỗi profile trong FoxProfile
> cần gắn một **proxy nước ngoài** (Mỹ, Singapore, Nhật...). Bot tự kiểm tra và cảnh báo nếu một profile đang dùng
> IP Việt Nam.

---

## Bạn cần chuẩn bị

- Máy tính **Windows 10/11**, luôn bật và có Internet trong lúc dùng bot.
- Ứng dụng **Telegram** (trên điện thoại hoặc máy tính).
- Tài khoản **Muse** và **proxy nước ngoài** cho mỗi tài khoản.

---

## Bước 1 — Cài Python (làm 1 lần)

1. Vào <https://www.python.org/downloads/>, bấm nút vàng **Download Python**.
2. Mở file vừa tải. **Tick ô "Add python.exe to PATH"** ở dưới cùng, rồi bấm **Install Now**.
3. Chờ cài xong, bấm **Close**.

## Bước 2 — Cài Muse2tele (làm 1 lần)

1. Giải nén thư mục `Muse2tele` vào ổ đĩa, ví dụ `D:\Muse2tele`.
2. Mở thư mục, **bấm đúp vào `setup.bat`**.
3. Một cửa sổ đen hiện ra và tự cài mọi thứ (5–15 phút tuỳ mạng). Khi thấy chữ **CAI DAT XONG**, bấm phím bất kỳ
   để đóng.

## Bước 3 — Tạo bot Telegram (làm 1 lần)

1. Trên Telegram, tìm **@BotFather** (có dấu tích xanh) và bấm **Start**.
2. Gửi `/newbot`.
3. BotFather hỏi tên bot: gõ tên bất kỳ, ví dụ `Muse của tôi`.
4. BotFather hỏi username: gõ tên **kết thúc bằng `bot`**, ví dụ `museminh_bot`.
5. BotFather gửi lại một dòng **token** dạng `123456789:AAH...`. Bấm vào để sao chép.
6. Trong thư mục Muse2tele, mở file **`.env`** bằng Notepad (chuột phải → Open with → Notepad).
   Nếu chưa thấy file `.env`, cứ làm tiếp bước 4 — bot sẽ tự tạo và mở file này cho bạn.
7. Dán token vào sau dấu `=` ở dòng đầu, ví dụ:

   ```
   TELEGRAM_BOT_TOKEN=123456789:AAH...
   ```

8. Bấm **Ctrl + S** để lưu, rồi đóng Notepad.

> 🔒 Token giống như mật khẩu của bot. Không gửi token cho người khác.

## Bước 4 — Chạy chương trình

**Bấm đúp vào `start_all.bat`.** Hai cửa sổ sẽ mở:

- **FoxProfile**: ứng dụng quản lý trình duyệt / tài khoản Muse.
- **Muse2tele_Bot**: cửa sổ đen của bot. **Để nguyên cửa sổ này**, đóng là bot dừng.

Nếu cửa sổ bot báo **CHUA CO TOKEN** hoặc **TOKEN SAI**, làm lại Bước 3 rồi chạy lại `start_all.bat`.

## Bước 5 — Nhận quyền chủ bot

1. Trên Telegram, tìm bot vừa tạo (theo username ở Bước 3) và bấm **Start**.
2. Bot trả lời *"Bạn đã là chủ của bot này"* và gửi **bảng trạng thái** gồm các dấu ✅ / ❌, kèm
   **việc cần làm tiếp**. Cứ làm theo bảng đó; gõ `/start` bất cứ lúc nào để xem lại.

> Người đầu tiên bấm Start sẽ là chủ bot. Hãy tự làm bước này ngay sau khi tạo bot.

## Bước 6 — Tạo nhóm Telegram có Topic

1. Trên Telegram, tạo **Nhóm mới** (New Group), thêm bot của bạn vào nhóm.
2. Bấm vào tên nhóm → **✏️ Sửa (Edit)** → bật **Chủ đề (Topics)** → Lưu.
3. Vẫn trong phần sửa nhóm: **Quản trị viên (Administrators)** → **Thêm quản trị viên** → chọn bot →
   bật quyền **Quản lý chủ đề (Manage topics)** và **Xoá tin nhắn (Delete messages)** → Lưu.
   (Quyền xoá tin nhắn dùng cho lệnh `/reset`, để bot xoá sạch topic của profile.)
4. Vào nhóm, gõ **`/setup`** và gửi. Bot trả lời ✅ là xong.

## Bước 7 — Thêm tài khoản Muse

Làm bước này cho **mỗi** tài khoản Muse:

1. Trong FoxProfile, bấm **tạo profile mới**. Đặt tên dễ nhớ (tên này sẽ là tên topic).
2. Ở ô **Proxy**, dán proxy **nước ngoài** của bạn. Bấm kiểm tra proxy nếu có nút kiểm tra, rồi lưu.
3. Bấm **mở (Launch)** profile. Một trình duyệt hiện ra.
4. Vào **muse.ai** và đăng nhập tài khoản Muse.
5. Chờ khoảng **1 phút**: trong nhóm Telegram tự xuất hiện **topic cùng tên profile** kèm lời chào. Xong!

Nếu topic chưa hiện sau vài phút, kiểm tra profile vẫn đang mở và đã vào được ô chat của Muse, rồi gõ `/start`
trong chat riêng với bot để xem bot đang chờ gì.

---

## Dùng hằng ngày

1. Bật máy, bấm đúp `start_all.bat`.
2. Trong FoxProfile, **mở các profile** bạn muốn dùng. Profile đang tắt thì bot không đọc được Muse của nó; mở lại
   thì bot tự gửi bù những tin Muse viết trong lúc đó.
3. Vào **topic** của profile và nhắn tin như chat bình thường.

Ý nghĩa biểu tượng trên tin của bạn:

| Biểu tượng | Ý nghĩa |
|---|---|
| 👀 | Bot đã nhận tin |
| 👍 | Đã gửi vào Muse |
| 👌 | Muse đã trả lời xong |
| 👎 | Lỗi, bot sẽ trả lời kèm lý do |

Mẹo:

- Gửi nhiều ảnh/video cùng lúc (album) sẽ thành **1 tin** trong Muse.
- **Trả lời (Reply)** một tin thì Muse biết bạn đang nói về tin nào.
- Muse đưa ra lựa chọn thì bot hiện **nút bấm**; bấm nút là gửi lựa chọn cho Muse.
- Bạn gõ trực tiếp trên web Muse thì câu trả lời vẫn hiện trong topic.
- Telegram chỉ cho bot nhận file **tối đa 20 MB** và gửi file **tối đa 50 MB**.

## Các lệnh của bot

Bot tự khai báo menu lệnh (gõ `/` để xem) và lời giới thiệu với Telegram mỗi khi khởi động, nên **không cần** 
vào BotFather để đặt `/setcommands`, `/setdescription` hay `/setabouttext`.

| Lệnh | Gõ ở đâu | Tác dụng |
|---|---|---|
| `/start`, `/help` | Chat riêng với bot | Xem trạng thái cấu hình và việc cần làm tiếp |
| `/setup` | Trong nhóm | Gắn nhóm này với bot |
| `/gan` | Trong topic | Gán topic này với một profile: tên topic trùng tên profile thì gán luôn, không thì bot hiện nút chọn profile. `/gan tên_profile` để gán thẳng. Gán lại thì thay liên kết cũ (mỗi profile 1 topic) |
| `/kiemtra` | Chat riêng hoặc nhóm | Kiểm tra IP từng profile, cảnh báo IP Việt Nam |
| `/tiendo` | Chat riêng hoặc nhóm | Xem bảng việc của đội Muse (chế độ có chỉ huy) |
| `/ketqua T8` | Chat riêng hoặc nhóm | Xem ngay ảnh/video kết quả của 1 việc trong đội Muse (kể cả khi chưa đạt) |
| `/allow_on`, `/allow_off` | Chat riêng hoặc nhóm | Bật / tắt việc bot tự bấm **Allow** khi Muse xin quyền (mặc định bật) |
| `/reset` | Trong topic của profile (hoặc `/reset tên_profile` ở chat riêng) | **Xoá vĩnh viễn** toàn bộ dữ liệu Muse của profile và toàn bộ tin trong topic, sau khi bạn bấm nút xác nhận. Xong bot đặt tên agent Muse = tên profile |

Chỉ chủ bot dùng được `/setup`, `/gan`, `/kiemtra`, `/allow_on`, `/allow_off`, `/reset`. Mọi người trong nhóm đều nhắn được cho Muse
trong các topic, nên **chỉ thêm người bạn tin tưởng** vào nhóm.

## Đội Muse: 1 Muse làm chỉ huy

Mặc định mỗi Muse tự làm trong topic của mình (**Độc lập**). Muốn 1 Muse điều phối cả đội:

1. Trên dashboard FoxProfile bấm **Đội Muse** ở thanh bên, chọn **Có chỉ huy**.
2. Chọn **Muse chỉ huy**. Nên chọn Muse không dùng cho việc khác, vì khung chat của nó dùng để điều phối.
3. Chọn cách **gửi việc**:
   - **Duyệt tay**: mỗi việc chỉ huy giao hiện trong mục General kèm nút ✅ Gửi / ❌ Bỏ.
   - **Tự động**: việc được gửi đi ngay.
4. Ở mục **Thành viên và vai trò**: bỏ tick Muse nào không muốn cho vào đội (chỉ huy sẽ không giao việc cho Muse
   đó; profile mới tạo tự vào đội), và ghi **vai trò** từng Muse (vd *viết kịch bản*, *làm ảnh*) để chỉ huy biết giao
   việc cho ai.
5. Mục **Duyệt kết quả**: **điểm tối thiểu để đạt** (/10, mặc định 8), số lần làm lại tối đa (3), số phút im lặng
   trước khi bot nhắc Muse (3), báo quá hạn sau (30 phút), số việc mới mỗi giờ (20); **Video nộp từng cái một**
   (mặc định bật); **Gửi cả ảnh/video chưa đạt lên Telegram** (mặc định tắt).
6. Ô **Xoá dữ liệu Muse khi lưu** (mặc định tick, khuyến nghị): bot xoá sạch dữ liệu Muse (lịch sử chat, file,
   artifact) của chỉ huy và các Muse trong đội, kèm tin trong topic của chúng, để cả đội bắt đầu sạch không lẫn thông
   tin cũ. Không hoàn tác; dashboard hỏi xác nhận. Bỏ tick thì chỉ lưu cài đặt, không xoá gì.
7. Bấm **Lưu**: bot áp dụng ngay, không cần khởi động lại.

Sau đó bạn nhắn yêu cầu vào **mục General** của nhóm. Chỉ huy sẽ chia việc và giao cho các Muse. Mỗi việc có mã
T1, T2...; việc giao đi hiện cả trong topic của Muse nhận việc. Muse làm xong thì bot gửi kết quả (cả ảnh/video) cho
chỉ huy chấm. Gõ `/tiendo` để xem bảng việc.

- **Duyệt tự động theo điểm:** từ điểm tối thiểu trở lên là đạt; dưới mức đó bot tự gửi điểm và nhận xét cho Muse làm
  lại. Làm lại quá số lần tối đa mà vẫn chưa đạt: bot dừng việc và báo bạn.
- **Video từng cái một:** chỉ huy giao `[[giao: Muse3 | mô tả | 5 video]]` thì Muse làm và nộp đúng 1 video, chỉ huy
  chấm đạt bot mới cho làm video tiếp.
- **Việc chưa đạt chỉ báo bằng chữ:** Telegram chỉ nhận kết quả chữ và số lần chưa đạt; ảnh/video được bot giữ lại gửi
  chỉ huy chấm, đạt mới gửi vào topic của Muse đó. Muốn xem sớm: `/ketqua T8`.
- **Trang tổng hợp video:** chỉ huy luôn giữ 1 trang artifact "Tổng hợp video" (mã việc, Muse tạo, link tải video,
  caption, hashtag, điểm, trạng thái, chỉ đạo tiếp) và dựa vào đó để chỉ đạo làm lại hay làm tiếp. Muse làm video phải
  ghi 3 dòng `Link tải:`, `Caption:`, `Hashtag:` khi nộp; bot trích ra thành "dòng chuẩn" gửi kèm báo cáo để chỉ huy
  chép đúng vào trang.
- **Chống lệch thông tin:** chỉ huy nhắc mã việc đã đạt (vd "dùng bộ nhân vật T5") thì bot tự đính kèm ảnh/video và mô
  tả đã duyệt của T5 cho Muse làm, không để chỉ huy tả lại theo trí nhớ. Bot báo cho Muse điểm các việc trước của nó,
  nhắc Muse 1 lần trước khi báo cáo khi Muse im lặng chưa ghi xong, và bỏ qua điểm chấm trùng.

Muốn dừng ngay: đổi về **Độc lập** trên dashboard.

## Cập nhật phiên bản mới

- Khi trên GitHub có bản mới, dashboard FoxProfile hiện dải **"Đã có phiên bản mới của Muse2Tele"** và bot nhắn
  riêng cho chủ bot (mỗi bản 1 lần). Muốn kiểm tra ngay: bấm **Kiểm tra cập nhật** ở thanh bên.
- Bấm **Xem thay đổi & cập nhật** → **Cập nhật ngay**. Chương trình tự: tải bản mới → tắt các profile đang chạy,
  FoxProfile, bot, AutoPost → thay code → cài thêm thư viện nếu cần → mở lại tất cả (1–3 phút) và mở lại các profile
  đang chạy lúc trước.
- **Dữ liệu giữ nguyên:** `.env`, `foxprofile\data\` (profile, cookie, đăng nhập, fingerprint), `Videos\`,
  `social_post\data\`, trạng thái bot. File code bạn đã sửa tay được sao lưu ở `.update\backup\` trước khi thay.
- Bản tải ZIP: lần đầu dashboard luôn báo có bản mới (chưa biết bản đang cài), cập nhật 1 lần là đồng bộ.
  Bản `git clone`: cập nhật bằng `git pull` tự động; có file sửa chưa commit thì từ chối để không mất thay đổi.
- Nhật ký: `.update\update.log`. Chạy tay: `python updater.py check` / `python updater.py apply`.

---

## Gặp sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| Bấm `setup.bat` báo **CHUA CAI PYTHON** | Làm lại Bước 1, nhớ tick **Add python.exe to PATH**. |
| Cửa sổ bot báo **CHUA CO TOKEN / TOKEN SAI** | Làm lại Bước 3, kiểm tra không thừa dấu cách trong `.env`. |
| Bot báo **Conflict 409** | Bot đang chạy ở máy/cửa sổ khác cùng token. Chỉ chạy **một** bot. |
| Bot cảnh báo 🚫 **IP Việt Nam** | Mở FoxProfile, sửa profile đó, gắn proxy nước ngoài, tắt rồi mở lại profile, gõ `/kiemtra`. |
| Không tự tạo topic | Gõ `/start` ở chat riêng với bot, làm theo dòng ❌ đầu tiên. Profile phải **đang mở** và **đã đăng nhập** Muse. |
| Lỡ xoá topic của profile | Bot tự tạo lại topic mới trong vài phút. |
| Muse không trả lời / báo lỗi | Bot tự tải lại trang và thử lại; trình duyệt treo thì bot tự khởi động lại profile. Tin gửi lúc Muse lỗi được xếp hàng và tự gửi lại. |

Nhật ký chi tiết của bot nằm ở `muse_telebot\muse_telebot.log` — gửi file này cho người hỗ trợ khi cần.

---

## ❤️ Ủng hộ dự án

Muse2tele được phát triển và chia sẻ miễn phí. Nếu bạn thấy hữu ích, hãy ủng hộ tại
**[sanhdieu247.xyz](https://sanhdieu247.xyz)** — mỗi sự ủng hộ giúp dự án tiếp tục được duy trì và cải tiến.

---

## Dành cho người kỹ thuật

```
Muse2tele\
  .env                      cấu hình cục bộ (token) — không chia sẻ / commit
  setup.bat                 cài .venv, thư viện, trình duyệt Camoufox
  start_all.bat             mở FoxProfile, chờ API, mở bot
  start_foxprofile.bat      chỉ mở FoxProfile (app + API http://127.0.0.1:8090)
  start_bot.bat             chỉ mở bot
  muse_telebot\
    muse_telebot.py         bot: topic ⇄ main chat Muse, tự tạo topic, hướng dẫn cấu hình, cảnh báo IP VN
    muse_sync.py            thao tác muse.ai qua REST của FoxProfile (gửi tin, đọc trả lời, tải media, ip-check)
    muse_auto.py            tự bấm Allow trên muse.ai
    muse_telebot_state.json chủ bot, nhóm, map profile → topic, id tin đã chuyển (bot tự tạo)
  foxprofile\
    foxprofile_client.py    client REST
    repo\                   ứng dụng FoxProfile
    data\                   dữ liệu profile (cookie, đăng nhập) — không chia sẻ / commit
```

- **Tạo topic:** mỗi 30 giây bot đọc danh sách profile của FoxProfile. Profile chưa có topic, đang chạy và hiện
  ô chat của `https://muse.ai/` (đã đăng nhập) thì bot tạo topic tên = tên profile. Bot không tự mở profile đang
  tắt. Profile bị xoá khỏi FoxProfile thì bot bỏ map; topic bị xoá trên Telegram thì bot tạo lại.
- **Đồng bộ:** mỗi profile có hàng đợi riêng; tin trong cùng topic vẫn gửi tuần tự, còn các profile khác nhau có thể
  xử lý đồng thời. Lỗi thì refresh, thử lại, khởi động lại trình duyệt; Muse lỗi kéo dài thì xếp hàng gửi lại mỗi
  60 giây, tối đa 30 phút. Trả lời được đọc ngay sau khi gửi (relay); bộ theo dõi web quét mỗi 5 giây, tối đa 4
  profile cùng lúc. Mỗi tin chỉ chuyển một lần. Việc đọc Muse vẫn dựa vào giao diện web qua FoxProfile nên thời
  gian trả lời và trạng thái hình ảnh/phim phụ thuộc tải trang, chưa tương đương webhook/API sự kiện.
- **IP Việt Nam:** bot gọi `GET /api/v1/profiles/{name}/ip-check` của FoxProfile (đi qua proxy của profile) lúc
  khởi động, khi tạo topic, mỗi 6 giờ và khi gõ `/kiemtra`; quốc gia là VN thì cảnh báo trong topic và chat riêng.
- **Reset:** `/reset` → nút *Xoá Muse của …*. Bot xếp việc vào hàng đợi của profile, mở muse.ai và làm
  Settings → Data controls → Reset <tên agent> → tự gõ tên agent đọc trên dòng đó → Reset, rồi kiểm tra tin cũ đã
  hết. Xong thì xoá topic cũ (xoá luôn mọi tin trong đó), tạo topic mới cùng tên và gửi Muse
  `Change your name to <profile>`. Thiếu quyền xoá tin thì bot báo, giữ topic cũ. Selector dựa trên giao diện tiếng
  Anh của Muse (profile để locale en-US).
- **Đội Muse (`muse_team.py`, cài ở `muse_telebot\muse_team.json`):** chế độ có chỉ huy thì tin trong General
  đi vào Muse chỉ huy. Bot gửi cho chỉ huy bảng giới thiệu đội và cú pháp lệnh (lần đầu và mỗi khi đội / vai trò
  đổi). Chỉ huy ra lệnh bằng dòng `[[giao: Muse2 | việc]]`, `[[nhan: T3 | nội dung]]`, `[[lamlai: T3 | cần sửa gì]]`,
  `[[danhgia: T3 | 8/10 | nhận xét]]`; Muse làm việc kết thúc bằng `[[xong: T3]]` hoặc `[[vuong: T3 | lý do]]`. Bot
  thực hiện lệnh và ẩn các dòng này khỏi Telegram. Mỗi Muse làm 1 việc một lúc. Muse không ghi `[[xong]]` mà đã rảnh
  và im lặng `quiet_minutes` phút thì bot nhắc 1 lần, vẫn im thì báo cáo. Bảng việc lưu trong `muse_telebot_state.json`
  (`tasks`); file kết quả ở `<MUSE_UPLOAD_DIR>/team/<mã việc>/p<video>r<lần>/` (vòng chưa đạt xoá khi việc đóng, cả
  thư mục xoá sau 7 ngày). Dashboard lưu `reset_id` mới khi chủ tick "Xoá dữ liệu Muse": bot reset Muse của chỉ huy +
  đội đúng 1 lần cho mỗi mã đó.
- **Tên agent:** khi tự tạo topic hoặc `/gan`, nếu agent Muse còn tên mặc định `Muse` thì bot gửi
  `Change your name to <profile>` để tên agent trùng tên profile / topic. Agent đã có tên riêng thì giữ nguyên.
- `MUSE_UPLOAD_DIR` phải nằm trong `FOXPROFILE_UPLOAD_DIRS`. Không chạy hai bot cùng token (Telegram báo 409).
- **Tự động đăng fanpage / TikTok (`social_post\`):**
  1. Trên dashboard FoxProfile, sửa profile → tick **Tự động đăng lên fanpage Facebook** và/hoặc **TikTok**.
     Mở profile và đăng nhập Facebook / TikTok trong trình duyệt của profile đó.
  2. `start_all.bat` mở thêm cửa sổ **Muse2tele_AutoPost** (hoặc chạy `start_autopost.bat`). Nó tạo thư mục
     `Videos\downloads\social_queue\<tên profile>\` cho mỗi profile đã tick.
  3. Bỏ file vào thư mục đó: video → TikTok + fanpage, ảnh → fanpage. Caption lấy từ file `.txt` cùng tên
     (vd `clip1.mp4` + `clip1.txt`), không có thì dùng tên file. `pages.txt` (mỗi dòng 1 tên Trang) để chỉ đăng lên
     một số Trang; không có thì đăng lên mọi Trang tài khoản quản lý.
  4. Đăng xong file chuyển sang `done\`, lỗi 3 lần thì sang `failed\`. Chưa đăng nhập thì 30 phút thử lại.
     Nhật ký: `social_post\logs\auto_post.log`. Thử không bấm Đăng: `python auto_post.py --dry-run`.
  Script lẻ: `fanpage_post.py --profile P --list-pages | --plan jobs.json` (định dạng: `fanpage_jobs.py`),
  `tiktok_post.py --profile P --folder D --file F [--caption "..."]`. Script làm việc trên một tab riêng, không
  đụng tab Muse của bot. Thư mục hàng đợi phải nằm trong `FOXPROFILE_UPLOAD_DIRS` (đổi ở dashboard → Thư mục upload).
