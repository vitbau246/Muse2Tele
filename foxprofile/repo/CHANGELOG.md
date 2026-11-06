# Changelog

Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/); phiên bản theo [Semantic Versioning](https://semver.org/lang/vi/).

## [Unreleased]

### Thêm
- Đội Muse: mục "Đăng video đạt" (`post_mode`: không đăng / hỏi trước / tự động, `post_profile`: kênh đăng mặc định). Video đạt hiện trong General kèm nút 📤 cho từng kênh của Bảng đăng bài (ghi rõ Trang + TikTok); bấm thì bot chép video và caption + hashtag vào hàng đợi đăng của profile đó, báo nếu profile chưa tick tự đăng. Chế độ tự động đưa thẳng vào kênh mặc định.
- Bảng đăng bài: tối đa bài/ngày, khung giờ đăng (vd `11-13, 19-23`) và ngôn ngữ caption cho từng profile; `auto_post.py` hẹn lại khi ngoài khung giờ / đủ bài trong ngày, và không đăng cùng một video (nhận theo nội dung, đổi tên vẫn nhận ra) hai lần lên cùng Trang / tài khoản TikTok (`social_post/data/posted_history.json`). Đội Muse xin thêm caption theo ngôn ngữ của kênh (`Caption (en): ...`) và dùng đúng caption đó khi đăng.
- Bảng đăng bài: nút "Kiểm tra tài khoản" cho từng profile chạy `social_post/check_accounts.py` (mở profile, không đăng gì): liệt kê Trang tài khoản Facebook quản lý, đọc tài khoản TikTok đang đăng nhập và so với bảng; API `POST /api/v1/settings/post-map/check/{name}`, kết quả ở `rows[].check`. `tiktok_post.py --check-account` in tài khoản đang đăng nhập.
- "Bảng đăng bài" ở thanh bên (app desktop và web panel): map mỗi profile với Page ID Facebook và tài khoản TikTok, gợi ý các Trang tài khoản đã quét, báo profile tick tự đăng mà chưa map; mỗi Page ID / tài khoản TikTok chỉ thuộc 1 profile. Lưu ở `social_post/data/post_map.json`; API `GET/PUT /api/v1/settings/post-map`. `auto_post.py` chỉ đăng lên Trang đã map (không còn đăng lên mọi Trang tài khoản quản lý) và chờ nếu chưa map; `fanpage_post.py` chọn Trang theo Page ID, dừng khi Trang không thuộc tài khoản đăng nhập hoặc Business Suite mở Trang khác; `tiktok_post.py --expect-account` dừng khi tài khoản TikTok đăng nhập khác tài khoản đã map (mã thoát 6, không thử lại).
- Đội Muse: "Ngôn ngữ giao việc" cho chế độ Có chỉ huy (`task_lang`): chỉ huy viết việc, tin nhắn và nhận xét bằng ngôn ngữ này; Muse có ngôn ngữ riêng nhận việc bằng ngôn ngữ của nó.
- Đội Muse: phần "Ngôn ngữ và ngữ cảnh" cho chỉ huy và từng Muse thành viên (app desktop và web panel): chọn ngôn ngữ trả lời và nhập ngữ cảnh làm bộ nhớ dài hạn (tối đa 6000 ký tự), có mẫu "Phim ngắn gia đình hài (đạo diễn, 9:16)". Bot gửi cho Muse 1 lần dạng "Cập nhật bộ nhớ dài hạn", gửi lại khi sửa hoặc sau khi xoá dữ liệu Muse; việc mới chỉ đến Muse sau khi Muse đã nhận thiết lập. Lưu ở `setup` trong `muse_team.json`; API `GET/PUT /api/v1/settings/muse-team` thêm `setup`, `langs`, `templates`.
- Muse2Tele: mục "Đội Muse" ở thanh bên (app desktop và web panel) để chọn chế độ Độc lập hoặc Có chỉ huy (1 Muse ở mục General giao việc, theo dõi và chấm các Muse khác), Muse chỉ huy, gửi việc duyệt tay hoặc tự động, và vai trò từng Muse; lưu ở `muse_telebot/muse_team.json`; API `GET/PUT /api/v1/settings/muse-team`. Thêm mục "Duyệt kết quả" (điểm tối thiểu để đạt /10, số lần làm lại, phút im lặng, phút quá hạn, việc mới mỗi giờ, video nộp từng cái một, gửi ảnh/video chưa đạt lên Telegram) và ô "Xoá dữ liệu Muse khi lưu" (mặc định tick, có hỏi xác nhận) để bot xoá dữ liệu Muse của chỉ huy và cả đội 1 lần.
- Muse2Tele: thông báo phiên bản mới trên GitHub (dải thông báo + nút "Kiểm tra cập nhật" ở app desktop và web panel) và cập nhật toàn bộ dự án bằng 1 nút, giữ nguyên dữ liệu; API `GET /api/v1/update`, `POST /api/v1/update/apply` (gọi `updater.py` của Muse2Tele, chạy tách rời rồi khởi động lại FoxProfile).
- Muse2Tele: ô tick "Tự động đăng lên fanpage Facebook / TikTok" khi tạo và sửa profile (app desktop và web panel), lưu trong `profiles.json` (`auto_post_fanpage`, `auto_post_tiktok`), có trong `POST/PATCH/GET /api/v1/profiles`; dòng profile hiện nhãn Fanpage / TikTok. Mục "Thư mục upload" ở thanh bên để chọn `FOXPROFILE_UPLOAD_DIRS` (nhiều thư mục) và `MUSE_UPLOAD_DIR` kèm giải thích, lưu vào `.env` của Muse2Tele; API `GET/PUT /api/v1/settings/upload-dirs`.
- Clone profile: nút Clone trên mỗi dòng (app desktop và web panel), `POST /api/v1/profiles/{name}/clone` và MCP `clone_profile`. Profile mới lấy proxy, hệ điều hành, timezone, locale và engine của profile nguồn; tuỳ chọn chép dữ liệu trình duyệt (cookie, đăng nhập, tab; bỏ qua file khoá và cache) và tạo fingerprint mới. Clone được cả khi profile nguồn đang chạy.
- Web panel: mục "Download folder" ở thanh bên để chọn thư mục lưu file tải về (lưu trong `settings.json`, áp dụng ngay cả với profile đang chạy). `FOXPROFILE_DOWNLOAD_DIR` chỉ là giá trị mặc định ban đầu; nếu chưa đặt gì thì dùng `Downloads/FoxProfile`. API: `GET/PUT /api/v1/settings`.
- `FOXPROFILE_WINDOW_SIZE` (ví dụ `1280x800`): đặt kích thước cửa sổ trình duyệt cho mọi lần mở, áp lên fingerprint của profile lúc mở (không sửa `fingerprint.json`). Cửa sổ nhỏ hơn tốn ít bộ nhớ GPU hơn. Để trống thì giữ kích thước theo fingerprint như trước.

### Sửa
- Profile mở lại được sau khi FoxProfile bị tắt ngang hoặc crash: trình duyệt cũ còn sót vẫn giữ thư mục dữ liệu, khiến mọi lần mở sau đều lỗi ngay. Giờ trước khi mở, FoxProfile đóng các process runner và trình duyệt còn dùng thư mục dữ liệu của profile đó (thêm phụ thuộc `psutil`).
- Một client gọi mở lại liên tục không còn làm cạn RAM của máy: profile mở lỗi 3 lần trong 2 phút thì `POST /browser/{name}/launch` trả 429 (kèm `Retry-After`) trong 5 phút. Chỉnh bằng `FOXPROFILE_LAUNCH_FAILURE_LIMIT`, `FOXPROFILE_LAUNCH_FAILURE_WINDOW`, `FOXPROFILE_LAUNCH_BACKOFF`. App desktop không bị chặn.
- File tải từ trình duyệt của profile (cả Camoufox và Chrome) không còn biến mất: Playwright giữ chúng trong thư mục tạm và xoá khi đóng browser, nên trước đây trang báo đã tải xong nhưng không có file. Giờ mỗi file được lưu vào thư mục download đã chọn, tự đánh số nếu trùng tên.
- App desktop: nút "Launch" không còn bị gãy chữ thành hai dòng khi dùng giao diện English.
- Proxy dạng `host:port:user:pass` có `@` hoặc `:` trong mật khẩu không còn bị bỏ qua (trước đây profile mở mà không qua proxy). Chấp nhận proxy IPv6 dạng `[2001:db8::1]`; host proxy tối đa 253 ký tự.
- Tên profile không phân biệt hoa thường: "Demo" và "demo" không còn tạo được hai profile dùng chung một thư mục dữ liệu trên Windows/macOS. Đổi tên chỉ khác hoa thường vẫn giữ nguyên dữ liệu; tên chứa ký tự điều khiển bị từ chối.
- Đổi tên profile sang tên có thư mục dữ liệu sót lại trả về lỗi 409 thay vì làm hỏng danh sách profile. `profiles.json` được ghi nguyên tử, và các thao tác đồng thời (API, MCP, app) không còn ghi đè lẫn nhau, gây lỗi 500 hay xoá nhầm thư mục của profile vừa tạo lại.
- Proxy không vào được mạng báo lỗi dễ hiểu ("no internet connection through proxy host:port") thay vì chuỗi lỗi nội bộ; chi tiết vẫn có trong log.
- MCP `update_profile(proxy="")` xoá được proxy.
- Điều khiển trang từ chối cả scheme bị mã hoá phần trăm (`%66ile:`) và URL hỏng như `[::1`.
- Web panel: xác nhận "New fingerprint" không còn đóng luôn hộp thoại cookie; Esc đóng màn hình xem trực tiếp và đúng hộp thoại trên cùng; hiện lỗi kèm nút Thử lại khi không kết nối được server thay vì trang trắng; nút Lưu và các thao tác cookie bị khoá khi đang chạy; lỗi 422 hiển thị dễ đọc.
- App desktop: hỏi xác nhận trước khi tạo fingerprint mới; ô chọn ở tiêu đề bảng không còn bỏ chọn các profile ở trang khác; rail hiện số profile và số trình duyệt đang chạy; hộp thoại xoá nói rõ cookie và dữ liệu sẽ mất vĩnh viễn.

### Thay đổi
- Ngôn ngữ giao diện mặc định của app desktop và web panel là English; đặt `FOXPROFILE_LANG=vi` (hoặc bấm "Tiếng Việt" trong app) để dùng tiếng Việt.

## [2.3.1] - 2026-10-09

### Sửa
- Web panel: bảng profile không còn tràn mất cột thao tác (Mở/Dừng) khi cửa sổ trình duyệt hẹp hơn khoảng 1460px; bảng giờ đổi bố cục theo bề rộng thực của chính nó.
- Profile không còn kẹt ở trạng thái "Đang mở" trên app desktop khi cùng lúc được mở qua API hoặc MCP; hai lệnh mở đồng thời cho cùng một profile không còn khởi chạy hai trình duyệt.

## [2.3.0] - 2026-10-09

### Thay đổi
- Thiết kế lại giao diện app desktop và web panel theo một hệ thống chung (xem `DESIGN.md`): nền giấy sáng, rail xanh, bảng profile thẳng cột với cột Thiết bị / Proxy / Timezone · Locale, và "dấu" trạng thái (đang chạy, đang mở, lỗi) phân biệt bằng cả hình dạng lẫn màu. Font Be Vietnam Pro và JetBrains Mono được đóng gói sẵn (OFL), chạy được không cần mạng.
- Thêm bộ lọc profile kèm số đếm (tất cả, đang chạy, có/không proxy, engine Chrome) trên cả hai giao diện; web panel có thêm thao tác hàng loạt và hộp thoại xác nhận riêng; app desktop đổi được Tiếng Việt / English ngay khi đang chạy.
- Thuật ngữ chuyên ngành giữ tiếng Anh trong giao diện tiếng Việt (fingerprint, engine, timezone, locale).

### Thêm
- Nhân **Chrome (thử nghiệm)** bên cạnh Camoufox, dựa trên fingerprint-chromium: chọn khi tạo profile trên app, web panel, REST API (`"engine": "chrome"`) và MCP (`create_profile(engine="chrome")`). Nhân cố định sau khi tạo. Cookie, fingerprint, điều khiển trang, mở lại tab và Kiểm tra IP dùng được như profile Camoufox. Bản trình duyệt được tự tải ở nền khi tạo profile Chrome đầu tiên, hoặc lúc mở profile nếu chưa có (cũng tải tay được bằng `python -m chrome_engine fetch`).
- Proxy dạng `host:port:user:pass` (định dạng thường gặp của nhà bán proxy) được chấp nhận ở mọi nơi nhập proxy, kể cả có tiền tố `socks5://`.
- Mở lại các tab đang mở khi profile được dừng (lưu vào `camoufox_data/<profile>/tabs.json` mỗi 2 giây khi tab thay đổi, chỉ `http`/`https`, tối đa 30 tab). Tắt bằng `FOXPROFILE_RESTORE_TABS=false`.

### Sửa
- Rò rỉ DNS khi dùng proxy `socks5://`/`socks4://`: việc tra IP đi ra lúc mở profile và nút **Kiểm tra IP** từng phân giải tên miền bằng DNS của máy (lộ nhà mạng thật). Nay chuyển sang `socks5h://`/`socks4a://` để proxy phân giải. Bản thân trình duyệt không bị ảnh hưởng.
- Chế độ `HEADLESS=virtual` (server Linux) không còn bỏ sót tiến trình Xvfb khi profile mở lỗi (ví dụ proxy không vào được) hoặc khi runner bị kill cứng/crash. Runner tự quản lý màn hình ảo và ghi lại Xvfb nó đã bật (theo PID và thời điểm khởi động, trong thư mục tạm riêng của user) để launcher, hoặc lần mở sau, tắt đúng Xvfb đó.

## [2.2.0] - 2026-10-08

### Thêm
- Đặt cố định múi giờ (IANA) và ngôn ngữ (`vi-VN`) cho từng profile; để trống vẫn tự động theo IP.
- Nút **Kiểm tra IP**: đối chiếu IP đi ra với Cloudflare, ipinfo và ip-api, cảnh báo lệch quốc gia/múi giờ, IP datacenter, proxy dual-stack và ngôn ngữ ngẫu nhiên. Có trên app, web panel, REST API (`GET /profiles/{name}/ip-check`, `POST /proxy/geo-check`) và MCP (`check_profile_ip`).
- Hướng dẫn triển khai lên server Linux (`docs/DEPLOY.md`, `deploy/`) và các script e2e thủ công (`tests/e2e/`).

## [2.1.0] - 2026-10-08

### Thêm
- MCP server (27 tool) cho AI agent, qua stdio và qua HTTP tại `/mcp`.
- Web panel có token bảo vệ, xem và điều khiển màn hình trình duyệt từ xa.
- Server mode chạy ẩn trình duyệt (`python -m src.server`).
- Hộp thoại hướng dẫn kết nối MCP cho Claude Code, Cursor, VS Code và Claude Desktop.

### Sửa
- Server mode đọc đúng `FOXPROFILE_HEADLESS` từ `.env`.

## [2.0.0] - 2026-10-08

Phát hành đầu tiên của FoxProfile: vân tay cố định theo profile, proxy riêng, xuất/nhập cookie (JSON và Netscape), REST API, giao diện tiếng Việt/tiếng Anh.

[Unreleased]: https://github.com/chienbm98/foxprofile/compare/v2.3.1...HEAD
[2.3.1]: https://github.com/chienbm98/foxprofile/compare/v2.3.0...v2.3.1
[2.3.0]: https://github.com/chienbm98/foxprofile/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/chienbm98/foxprofile/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/chienbm98/foxprofile/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/chienbm98/foxprofile/releases/tag/v2.0.0
