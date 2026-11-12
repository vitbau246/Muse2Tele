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

Trong lúc Muse làm việc, topic có 1 tin **⚙️ &lt;tên Muse&gt;: &lt;việc đang làm&gt;** (VD `⚙️ Muse8: Uploading video
parts`, `⚙️ Muse9: Connecting...`) — chính là dòng chữ dưới tên Muse trên web. Tin này tự cập nhật khi Muse chuyển
việc (kể cả việc chạy nền), không kêu thông báo, và tự xoá khi Muse xong. Dòng "… is typing" của Telegram cũng đổi
theo việc Muse đang làm (đang gửi ảnh / quay video / gửi file…).

Muse xin duyệt (Allow/Deny) mà bot không tự bấm Allow được trong 20 giây (tự duyệt đang tắt, hoặc nút lạ), bot gửi tin
**🔐 … đang chờ bạn duyệt** (có chuông) kèm nội dung yêu cầu và nút **✅ Cho phép**; bấm là bot bấm Allow trên Muse.

Mẹo:

- Gửi nhiều ảnh/video cùng lúc (album) sẽ thành **1 tin** trong Muse.
- **Trả lời (Reply)** một tin thì Muse biết bạn đang nói về tin nào.
- Muse đưa ra lựa chọn thì bot hiện **nút bấm**; bấm nút là gửi lựa chọn cho Muse.
- Bạn gõ trực tiếp trên web Muse thì câu trả lời vẫn hiện trong topic.
- Telegram chỉ cho bot nhận file **tối đa 20 MB** và gửi file **tối đa 50 MB**.
- Ảnh / video / file của Muse không gửi được về Telegram (Muse báo *not found*, quá 50 MB, Telegram từ chối...): bot
  báo trong topic và **tự nhờ Muse gửi link tải tạm (hạn 3 ngày)**; link hiện trong topic khi Muse trả lời. Mỗi file
  chỉ được nhờ 1 lần trong 6 tiếng, để Muse gửi lại file vẫn lỗi thì bot không hỏi mãi.
- Mặc định mỗi Muse **gửi kèm link tải tạm (hạn 3 ngày) ngay sau mỗi file**. muse.ai không có cài đặt cho việc này,
  nên bot tự gửi quy tắc vào bộ nhớ dài hạn của từng Muse: 1 lần khi Muse rảnh, gửi lại sau khi reset Muse.

## Các lệnh của bot

Bot tự khai báo menu lệnh (gõ `/` để xem) và lời giới thiệu với Telegram mỗi khi khởi động, nên **không cần** 
vào BotFather để đặt `/setcommands`, `/setdescription` hay `/setabouttext`.

| Lệnh | Gõ ở đâu | Tác dụng |
|---|---|---|
| `/start`, `/help` | Chat riêng với bot | Xem trạng thái cấu hình và việc cần làm tiếp |
| `/setup` | Trong nhóm | Gắn nhóm này với bot |
| `/gan` | Trong topic | Gán topic này với một profile: tên topic trùng tên profile thì gán luôn, không thì bot hiện nút chọn profile. `/gan tên_profile` để gán thẳng. Gán lại thì thay liên kết cũ (mỗi profile 1 topic) |
| `/kiemtra` | Chat riêng hoặc nhóm | Kiểm tra IP từng profile, cảnh báo IP Việt Nam |
| `/tach` | Trong topic của 1 Muse thành viên, `/tach tên_profile`, hoặc ở General (bot hiện nút chọn Muse) | **Tách 1 Muse khỏi đội** (chế độ có chỉ huy): chọn *Tách + xoá dữ liệu Muse* hoặc *Tách, giữ dữ liệu*. Bot huỷ mọi việc đang mở của Muse đó (kể cả việc đang làm), bỏ vai trò + ngữ cảnh đội, giới thiệu lại đội cho chỉ huy. Giữ dữ liệu thì bot nhắn Muse bỏ bối cảnh đội khỏi bộ nhớ dài hạn. Không tách được chỉ huy hay thành viên cuối cùng |
| `/tiendo` | Chat riêng hoặc nhóm | Xem bảng việc của đội Muse (chế độ có chỉ huy) |
| `/ketqua T8` | Chat riêng hoặc nhóm | Xem ngay ảnh/video kết quả của 1 việc trong đội Muse (kể cả khi chưa đạt) |
| `/allow_on`, `/allow_off` | Chat riêng hoặc nhóm | Bật / tắt việc bot tự bấm **Allow** khi Muse xin quyền (mặc định bật) |
| `/reset` | Trong topic của profile (hoặc `/reset tên_profile` ở chat riêng) | **Xoá vĩnh viễn** toàn bộ dữ liệu Muse của profile và toàn bộ tin trong topic, sau khi bạn bấm nút xác nhận. Xong bot đặt tên agent Muse = tên profile |
| `/reset` | Ở mục **General** (Muse chỉ huy), hoặc `/reset tên_chỉ_huy` | **Reset cả đội**: chọn 1 mẫu ngữ cảnh (lấy từ dashboard → Đội Muse) hoặc *Giữ ngữ cảnh đang có*, bấm xác nhận. Bot xoá dữ liệu Muse của chỉ huy + mọi thành viên, rồi tự gửi lại ngữ cảnh cho từng Muse và giới thiệu lại đội. Đổi mẫu thì bỏ luôn việc, video mẫu, kịch bản chốt (bộ nhân vật khoá cất vào thư mục lưu trữ). Có nút *Chỉ reset chỉ huy* nếu chỉ cần xoá Muse chỉ huy |
| `/dang` | Trong topic của profile, `/dang tên_profile`, hoặc ở General / chat riêng (tổng quan mọi profile) | **Đăng bài chủ động**: xem hàng đợi đăng (từng video: TikTok / Fanpage / YouTube ✅ ⏳ ❌, bộ đăng bài của Muse), video lỗi, số bài hôm nay, link vừa đăng; nút 🔄 Làm mới · 🔁 Đăng lại ngay · ⏸ Tạm dừng / ▶️ Tiếp tục · ▶️ Bật AutoPost (khi AutoPost không chạy). Gõ thêm: `thulai` (đưa video trong `failed\` về hàng đợi và đăng lại ngay; đích đã đăng được bỏ qua nhờ chống trùng), `dung` / `tiep` (tạm dừng / tiếp tục profile; không tên profile = tất cả), `drive từ khoá` (tìm video trên Google Drive của profile qua trình duyệt của nó, bấm chọn file thì bot tải về hàng đợi, Muse làm bộ đăng bài rồi AutoPost đăng). Mỗi kết quả đăng (xong / lỗi / bỏ) bot báo vào topic của profile |
| `/rebrand` | Trong topic của profile, hoặc `/rebrand tên_profile [định hướng]` | **Đổi nhận diện kênh** sau khi bấm xác nhận: tạm tắt Tự động đăng, **xoá mọi video TikTok** của tài khoản trong Bảng đăng bài (không hoàn tác), nhờ Muse làm bộ nhận diện (khối `BRANDKIT <mã>` + ảnh đại diện, ảnh bìa FB, banner YT). Đủ bộ thì `social_post\rebrand.py` tạo Trang Facebook + kênh YouTube mới (Trang / kênh cũ giữ nguyên), đổi tên / tiểu sử / ảnh TikTok (username mới nếu còn trống), gắn vào Bảng đăng bài, bật lại Tự động đăng. Lỗi giữa chừng: chạy lại lệnh bot báo, bước đã xong không làm lại. TikTok chỉ cho đổi tên 7 ngày/lần, username 30 ngày/lần |
| `/kenhmoi` | Ở đâu cũng được | **Lịch tạo kênh mới định kỳ** cho mọi profile FoxProfile (hoặc các profile đã `chon`): mỗi đợt bot nhờ Muse của từng profile làm bộ nhận diện mới (như `/rebrand`, tên / handle phải khác các kênh đã tạo), đủ bộ thì `social_post\rebrand.py --daily` tạo **Trang Facebook + kênh YouTube mới**. Không tắt Tự động đăng, không đụng TikTok / Bảng đăng bài: kênh đang đăng giữ nguyên. Đợt sau = đợt trước **+24h30ph** (giờ chạy tự dịch 30 phút mỗi ngày: 08:00 → 08:30 → 09:00...). `bat [HH:MM]` (bỏ giờ = chạy ngay), `tat`, `ngay` (chạy 1 đợt ngay, nhịp tính lại từ bây giờ), `chon Muse8 Muse9` / `chon tatca`, `huong <định hướng>` (`-` để xoá); gõ trống = trạng thái. Profile chưa có topic hoặc đang rebrand / tạo kênh dở thì bỏ qua đợt đó. Kết quả từng đợt ghi vào `social_post\data\channels\<profile>.daily.json`, cấu hình kênh trong thư mục bộ nhận diện `Videos\downloads\channels\<profile>\<mã>\channels.json` |

Chỉ chủ bot dùng được `/setup`, `/gan`, `/kiemtra`, `/allow_on`, `/allow_off`, `/reset`, `/tach`, `/rebrand`, `/kenhmoi`, `/dang`. Mọi người trong nhóm đều nhắn được cho Muse
trong các topic, nên **chỉ thêm người bạn tin tưởng** vào nhóm.

## Nhiều đội Muse, mỗi đội 1 nhóm Telegram

Hộp **Đội Muse** trên dashboard có thanh chọn đội ở trên cùng. **Đội 1** là đội mặc định: nhận mọi profile chưa
thuộc đội khác (profile mới cũng vào đây), dùng nhóm Telegram bạn gắn đầu tiên. Thêm đội:

1. Bấm **＋ Thêm đội**, đặt tên. Ở mục **Đội và nhóm Telegram** tick các profile thuộc đội này (mỗi profile chỉ thuộc
   1 đội; bỏ tick thì profile về đội mặc định), bấm **Lưu**.
2. Trên Telegram tạo nhóm mới, bật **Chủ đề (Topics)**, thêm bot làm quản trị viên (quyền *Quản lý chủ đề*), gõ
   `/setup` trong nhóm rồi bấm tên đội. Nút *Tạo đội mới* cũng tạo luôn đội mang tên nhóm.
3. Khoảng 1 phút sau bot tạo topic cho từng profile của đội trong nhóm đó. Profile chuyển đội thì topic ở nhóm cũ
   nhận thông báo và ngừng đồng bộ, nhóm mới có topic mới.

Mỗi đội có chỉ huy, thành viên, skill, ngôn ngữ, ngữ cảnh, thông số chấm, bảng việc (`/tiendo` trong nhóm của đội;
ở chat riêng thì hiện mọi đội) và thư mục dữ liệu riêng (`Videos\downloads\muse_telebot\doi\<mã đội>\`; đội mặc
định giữ đường dẫn cũ). Mã việc T1, T2... và video mẫu M1... đánh số riêng từng đội.

## Skill: mẫu ngữ cảnh + thiết lập cho từng kiểu việc

Skill là gói mẫu cho 1 kiểu việc: ngữ cảnh cho chỉ huy, ngữ cảnh cho thành viên, vai trò và thiết lập đi kèm. Các
thiết lập làm video (video mẫu, đo kỹ thuật video nộp, bước tạo hình, việc nhiều video / chia đoạn, caption, đăng
video đạt, nộp từng video, giữ ảnh/video chưa đạt) không còn là thiết lập chung của đội mà nằm trong skill: skill
video bật **Quy trình làm video**; skill *Đội việc chung* (nghiên cứu, viết, làm ảnh) tắt nó, bot chỉ chạy vòng giao
việc / chấm. Bấm **Áp dụng** trên 1 skill để điền cho cả đội đang tick, sửa lại nếu cần, rồi **Lưu**.

Skill có sẵn nằm ở `foxprofile\repo\src\core\skills\`. **Cài skill từ file (.json)** chép skill vào
`muse_telebot\skills\` (không bị cập nhật ghi đè, không đưa lên git). Định dạng: [docs/SKILL_PACKS.md](docs/SKILL_PACKS.md).

## Đội Muse: 1 Muse làm chỉ huy

Mặc định mỗi Muse tự làm trong topic của mình (**Độc lập**). Muốn 1 Muse điều phối cả đội:

1. Trên dashboard FoxProfile bấm **Đội Muse** ở thanh bên, chọn đội, chọn **Có chỉ huy**.
2. Chọn **Muse chỉ huy**. Nên chọn Muse không dùng cho việc khác, vì khung chat của nó dùng để điều phối.
3. Chọn cách **gửi việc**:
   - **Duyệt tay**: mỗi việc chỉ huy giao hiện trong mục General kèm nút ✅ Gửi / ❌ Bỏ.
   - **Tự động**: việc được gửi đi ngay.
4. Ở mục **Thành viên và vai trò**: bỏ tick Muse nào không muốn cho vào đội (chỉ huy sẽ không giao việc cho Muse
   đó; profile mới tạo tự vào đội), và ghi **vai trò** từng Muse (vd *viết kịch bản*, *làm ảnh*) để chỉ huy biết giao
   việc cho ai. Bỏ tick thì việc Muse đang làm vẫn chạy cho xong; muốn **tách hẳn** 1 Muse thì bấm nút ✂ cạnh tên
   nó (hoặc gõ `/tach` trên Telegram): áp dụng ngay, không cần Lưu. Bot huỷ mọi việc đang mở của Muse đó, bỏ vai trò
   và ngữ cảnh đội của nó; tick thêm *Xoá luôn dữ liệu Muse* để Muse không còn nhớ gì của đội (không hoàn tác),
   không tick thì bot nhắn Muse rằng nó đã rời đội. Muốn cho vào đội lại thì tick lại.
5. Mục **Duyệt kết quả**: **điểm tối thiểu để đạt** (/10, mặc định 8), số lần làm lại tối đa (3), số phút im lặng
   trước khi bot nhắc Muse (3), báo quá hạn sau (30 phút), số việc mới mỗi giờ (20). **Video nộp từng cái một**,
   **Gửi cả ảnh/video chưa đạt lên Telegram** và **Đăng video đạt** nằm trong mục **Skill → Thiết lập theo skill**.
6. Ô **Xoá dữ liệu Muse khi lưu** tự tick khi bạn đổi ngữ cảnh: bot xoá sạch dữ liệu Muse (lịch sử chat, file,
   artifact, tin trong topic) của đúng các Muse vừa đổi ngữ cảnh rồi mới gửi ngữ cảnh mới, để không lẫn thông tin cũ.
   Đổi sang mẫu khác thì bot bỏ luôn việc, video mẫu, kịch bản và cất bộ nhân vật khoá cũ. Không đổi ngữ cảnh mà tự
   tick thì xoá chỉ huy và cả đội. Không hoàn tác; dashboard hỏi xác nhận.
7. Bấm **Lưu**: bot áp dụng ngay, không cần khởi động lại.

Mục **Skill** có skill **Gia đình 4 người — có thoại**: bấm **Áp dụng** 1 lần là điền cho cả đội. Chỉ huy
nhận vai **nghiên cứu, phân tích, xây dựng kịch bản chi tiết** (không tự làm video); mọi Muse đang tick nhận vai
**xây dựng nhân vật và sản xuất video theo kịch bản** (ô vai trò còn trống được điền sẵn). Muse đang có ngữ cảnh
khác thì dashboard hỏi trước khi thay. Bấm **Lưu** để bot gửi cho các Muse.

Nút **Reset đội** (góc dưới trái hộp Đội Muse, bấm 2 lần để xác nhận) đưa mọi thiết lập về mặc định (Độc lập, bỏ chỉ
huy, vai trò, ngôn ngữ, ngữ cảnh...) và bot xoá dữ liệu Muse của chỉ huy + các Muse trong đội, bỏ mọi việc, video mẫu,
kịch bản chốt. Bộ nhân vật khoá và video mẫu cũ không bị xoá mà chuyển vào
`Videos\downloads\muse_telebot\da_reset\<thời điểm>\` (kèm bản sao state) để lấy lại khi cần.

Sau đó bạn nhắn yêu cầu vào **mục General** của nhóm. Chỉ huy sẽ chia việc và giao cho các Muse. Mỗi việc có mã
T1, T2...; việc giao đi hiện cả trong topic của Muse nhận việc. Muse làm xong thì bot gửi kết quả (cả ảnh/video) cho
chỉ huy chấm. Gõ `/tiendo` để xem bảng việc.

- **Duyệt tự động theo điểm:** từ điểm tối thiểu trở lên là đạt; dưới mức đó bot tự gửi điểm và nhận xét cho Muse làm
  lại. Làm lại quá số lần tối đa mà vẫn chưa đạt: bot dừng việc và báo bạn.
- **Giao cả đội 1 lệnh:** `[[giao: Muse2, Muse3 | ...]]` hoặc `[[giao: cả đội | ...]]` tạo mỗi Muse 1 mã việc, mỗi
  Muse tự dùng bộ nhân vật của mình.
- **Video từng cái một:** chỉ huy giao `[[giao: Muse3 | mô tả | 5 video]]` thì Muse làm và nộp đúng 1 video, chỉ huy
  chấm đạt bot mới cho làm video tiếp.
- **Video dài chia đoạn:** `[[giao: Muse3 | mô tả | 4 đoạn]]` — Muse nộp từng đoạn; đoạn sau bot gửi kèm khung hình
  cuối của đoạn trước để nối liền; đủ đoạn đạt thì bot tự nối thành 1 video (ffmpeg), gửi vào topic và hỏi đăng.
- **Bot tự đo video trước khi chuyển chỉ huy:** trùng file đã nộp, không có tiếng, sai khung dọc/ngang, sai thời
  lượng so với video mẫu → bot trả Muse làm lại ngay (tối đa 2 lần mỗi video, không tính lượt chấm). Báo cáo gửi chỉ
  huy luôn có dòng "Bot đo: ..." (thời lượng, khung, fps, có tiếng hay không).
- **Việc chưa đạt chỉ báo bằng chữ:** Telegram chỉ nhận kết quả chữ và số lần chưa đạt; ảnh/video được bot giữ lại gửi
  chỉ huy chấm, đạt mới gửi vào topic của Muse đó. Muốn xem sớm: `/ketqua T8`.
- **Trang tổng hợp video:** chỉ huy luôn giữ 1 trang artifact "Tổng hợp video" (mã việc, Muse tạo, link tải video,
  caption, hashtag, điểm, trạng thái, chỉ đạo tiếp). Muse làm video ghi `Caption:`, `Hashtag:` (và `Link tải:` nếu
  có) khi nộp; bot trích ra thành "dòng chuẩn" gửi kèm báo cáo để chỉ huy chép đúng vào trang.
- **Chống lệch thông tin:** chỉ huy nhắc mã việc đã đạt (vd "dùng bộ nhân vật T5") thì bot tự đính kèm ảnh/video và mô
  tả đã duyệt của T5 cho Muse làm, không để chỉ huy tả lại theo trí nhớ. Bot báo cho Muse điểm các việc trước của nó,
  nhắc Muse 1 lần trước khi báo cáo khi Muse im lặng chưa ghi xong, bỏ qua điểm chấm trùng, và bỏ qua tin "Mẹo..."
  Muse tự gửi (không tính là kết quả).
- **Làm video theo video mẫu:** dán link video (Facebook, TikTok, YouTube, Instagram, X...) vào General, vd
  "Làm 1 video giống thế này https://www.facebook.com/share/r/...". Bot tải video về (video dài quá 5 phút hoặc nặng quá 60 MB thì
  không tải cả video mà lấy 48 khung hình rải đều thẳng từ link, Muse tự quyết định có dùng không), đặt mã **M1**,
  M2..., cắt khung hình mỗi giây thành ảnh ghép (góc trái ghi giây) rồi gửi kèm cho chỉ huy. Gửi thẳng file video cho
  chỉ huy cũng được. Chỉ huy đánh giá khả thi (mức A: tới 40 giây, giao 1 video; mức B: 40–150 giây, chia đoạn; mức C:
  báo bạn trước), viết phân kịch theo từng giây (gồm trang phục, kiểu tóc từng giai đoạn), đổi vai sang nhân vật gia
  đình, gửi bạn duyệt, rồi chốt `[[kichban: M1 | phân kịch]]` (bot lưu bản v1, v2...) và giao
  `[[giao: cả đội | Làm video theo video mẫu M1]]`: bot tự đính kèm kịch bản chốt mới nhất, video mẫu, ảnh ghép và
  ảnh bộ nhân vật cho từng Muse — chỉ huy không phải chép lại kịch bản. Link dán vào topic của 1 Muse cũng được bot
  tải và gửi kèm như vậy.
- **Khoá bộ nhân vật:** việc tạo bộ nhân vật được chấm đạt thì bot chép ảnh vào
  `Videos\downloads\muse_telebot\nhan_vat\<tên Muse>\<mã việc>\` (không bị dọn, mỗi Muse giữ nhiều bộ). Bộ tạo "cho
  video mẫu M2" được gắn với M2 và kèm cho mọi Muse làm M2; còn lại là bộ chung (gia đình) của Muse đó. Việc theo video
  mẫu mà chỉ huy không ghi bộ nào: bot kèm bộ gắn với mẫu đó, không có thì bộ chung của chính Muse làm, không có nữa
  thì bộ chung mới nhất của đội.

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
  đổi). Chỉ huy ra lệnh bằng dòng `[[giao: Muse2 | việc]]` (nhiều Muse / `cả đội`, `| 5 video`, `| 4 đoạn`),
  `[[kichban: M1 | phân kịch]]`, `[[nhan: T3 | nội dung]]`, `[[lamlai: T3 | cần sửa gì]]`,
  `[[danhgia: T3 | 8/10 | nhận xét]]`; Muse làm việc kết thúc bằng `[[xong: T3]]` hoặc `[[vuong: T3 | lý do]]`. Bot
  thực hiện lệnh và ẩn các dòng này khỏi Telegram. Mỗi Muse làm 1 việc một lúc. Muse không ghi `[[xong]]` mà đã rảnh
  và im lặng `quiet_minutes` phút thì bot nhắc 1 lần, vẫn im thì báo cáo. Bảng việc lưu trong `muse_telebot_state.json`
  (`tasks`); file kết quả ở `<MUSE_UPLOAD_DIR>/team/<mã việc>/p<video>r<lần>/` (vòng chưa đạt xoá khi việc đóng, cả
  thư mục xoá sau 7 ngày). Dashboard lưu `reset_id` mới khi chủ tick "Xoá dữ liệu Muse": bot reset Muse của chỉ huy +
  đội đúng 1 lần cho mỗi mã đó. Nút "Reset đội" lưu thêm `reset_full: true` + `reset_targets`: bot chạy cả khi đã về
  chế độ Độc lập, reset Muse của `reset_targets` (chỉ profile có topic), xoá `tasks` / `samples` / `scripts` (mã T, M
  vẫn đánh số tiếp) và chuyển `nhan_vat\` + `mau\` vào `<MUSE_UPLOAD_DIR>/da_reset/<thời điểm>/`. Tách 1 Muse
  (nút ✂ / `/tach`, API `POST /settings/muse-team/detach`) ghi `detached: {profile: {id, wipe}}` và thêm Muse vào
  `excluded`: bot huỷ việc đang mở của Muse đó 1 lần cho mỗi `id` (state `team_detached`); `wipe` thì đi qua
  `reset_targets`, không thì bot gửi Muse tin rời đội (state `team_setup` = `leave:<id>`).
- **Tên agent:** khi tự tạo topic hoặc `/gan`, nếu agent Muse còn tên mặc định `Muse` thì bot gửi
  `Change your name to <profile>` để tên agent trùng tên profile / topic. Agent đã có tên riêng thì giữ nguyên.
- `MUSE_UPLOAD_DIR` phải nằm trong `FOXPROFILE_UPLOAD_DIRS`. Không chạy hai bot cùng token (Telegram báo 409).
- **Tự động lưu video Muse:** mặc định bật, bot giữ 1 bản mọi video tải từ chat Muse (kể cả video giữ lại cho chỉ
  huy chấm hay quá 50 MB không gửi được Telegram, tới 1 GB) vào `E:\Videos\Downloaded\<tên profile>\`, ví dụ
  `E:\Videos\Downloaded\Muse2\`. Bật / tắt và đổi thư mục ở dashboard → **Thư mục upload** → *Tự động lưu video
  Muse* (`MUSE_SAVE_VIDEOS`, `MUSE_SAVE_VIDEO_DIR` trong `.env`, API `GET/PUT /settings/video-save`); bot đọc lại
  `.env` khi file đổi, không cần chạy lại. Cùng tên cùng dung lượng thì không lưu lại; khác nội dung thì thêm `_2`.
- **Tạo Trang Facebook + kênh YouTube theo profile:** `python social_post\create_channels.py --profile Muse9`
  đọc `social_post\data\channels\<profile>.json` (tên, hạng mục, tiểu sử / mô tả, ảnh đại diện, ảnh bìa / banner
  nằm trong `Videos\downloads`, `account` = tên trang cá nhân để chuyển về sau khi tạo Trang). Kênh YouTube là kênh
  thêm (Tài khoản thương hiệu) của tài khoản Google đang đăng nhập; ảnh, mô tả, liên kết gắn trong YouTube Studio.
  Tạo xong ghi `created` vào file, chạy lại không tạo trùng; `--dry-run` chỉ điền form, `--refresh` gắn lại ảnh /
  mô tả kênh YouTube. Không đăng ký tài khoản mới, không vượt xác minh SĐT / CAPTCHA.
- **Tự động đăng fanpage / TikTok / kênh YouTube (`social_post\`):**
  1. Trên dashboard FoxProfile, sửa profile → tick **Tự động đăng lên fanpage Facebook**, **TikTok** và/hoặc
     **kênh YouTube**; Bảng đăng bài ghi Page ID (asset_id trong link Business Suite), @TikTok, @kênh YouTube.
     Mở profile và đăng nhập Facebook / TikTok / Google trong trình duyệt của profile đó.
  2. `start_all.bat` mở thêm cửa sổ **Muse2tele_AutoPost** (hoặc chạy `start_autopost.bat`). Nó tạo thư mục
     `Videos\downloads\social_queue\<tên profile>\` cho mỗi profile đã tick.
  3. Bỏ file vào thư mục đó: video → TikTok + fanpage + YouTube, ảnh → fanpage. Caption lấy từ file `.txt` cùng tên
     (vd `clip1.mp4` + `clip1.txt`), không có thì dùng tên file. `pages.txt` (mỗi dòng 1 tên Trang) để chỉ đăng lên
     một số Trang; không có thì đăng lên mọi Trang tài khoản quản lý. YouTube: dòng đầu caption = tiêu đề, phần còn
     lại = mô tả; ảnh `clip1.cover1.jpg` .. `clip1.cover3.jpg` cạnh video = thumbnail (2-3 ảnh: Thử nghiệm A/B), cần
     kênh đã xác minh số điện thoại (Studio → Cài đặt → Kênh → Điều kiện sử dụng tính năng → bậc trung).
  - **Bộ đăng bài do Muse làm (bắt buộc với video):** video chưa có `clip1.post.json` thì AutoPost CHƯA đăng mà ghi
     `clip1.kit_request.json`; bot nhờ Muse (Muse đã làm video nếu là video đội, không thì Muse của profile) làm bộ
     đăng bài, gửi kèm 5 khung hình trích từ video: tiêu đề + 3 tiêu đề thử nghiệm, mô tả, hashtag, caption TikTok,
     nội dung Facebook (khối `POSTKIT <mã>` + JSON) và 3 cover `<mã>-a/b/c.jpg`. Bot lưu thành `clip1.post.json` +
     `clip1.cover1..3.jpg` rồi AutoPost đăng: YouTube = tiêu đề + mô tả + hashtag + thử nghiệm 3 cover, TikTok / Facebook
     = caption riêng. Có bộ đăng bài mà thiếu cover thì chờ thêm 60 phút. Quá 3 giờ Muse chưa làm thì nhờ lại (tối đa
     2 lần). Tắt: `AUTO_POST_REQUIRE_KIT=0` trong `.env`. Định dạng: `social_post\post_kit.py`.
     **Bộ nhớ dài hạn:** Muse nào sẽ được nhờ làm bộ đăng bài (Muse của profile đã tick Tự động đăng và có kênh trong
     Bảng đăng bài; Muse thợ của đội chỉ huy có đăng video đội) được bot gửi sẵn quy tắc bộ đăng bài (nền tảng, kênh,
     quy cách 3 cover, định dạng `POSTKIT`) vào bộ nhớ dài hạn khi Muse rảnh; mỗi yêu cầu sau đó chỉ cần nhắc ngắn. Đổi
     tick / kênh thì gửi lại, reset Muse thì gửi lại, bỏ hết tick thì nhắn Muse bỏ quy tắc. Trạng thái: state
     `postkit_rule`.
  4. Đăng xong file chuyển sang `done\`, lỗi 3 lần thì sang `failed\`. Chưa đăng nhập thì 30 phút thử lại.
     Nhật ký: `social_post\logs\auto_post.log`. Thử không bấm Đăng: `python auto_post.py --dry-run`.
  Script lẻ: `fanpage_post.py --profile P --list-pages | --plan jobs.json` (định dạng: `fanpage_jobs.py`; danh sách
  Trang đọc thẳng từ dữ liệu nhúng trong HTML Business Suite, ~7 giây, không bấm bộ chọn Trang),
  `tiktok_post.py --profile P --folder D --file F [--caption "..."]`,
  `youtube_post.py --profile P --folder D --file F --expect-channel Handle [--caption-file F.txt] [--thumbs a b c]`
  (`--thumbs-only VIDEO_ID --thumbs a b c`: đặt lại thumbnail / A/B cho video đã đăng). Script làm việc trên một tab riêng, không
  đụng tab Muse của bot. Thư mục hàng đợi phải nằm trong `FOXPROFILE_UPLOAD_DIRS` (đổi ở dashboard → Thư mục upload).
