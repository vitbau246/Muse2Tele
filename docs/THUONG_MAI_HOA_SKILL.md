# Thương mại hoá skill pack của Muse2Tele

*Nghiên cứu ngày 2026-11-10. Phạm vi: bán / thu phí các mẫu ngữ cảnh + thiết lập đội Muse (skill pack) cho người
dùng tải repo Muse2Tele về chạy trên máy của họ.*

## 1. Kết luận

- **Không khoá được nội dung skill bằng kỹ thuật.** Ngữ cảnh là chữ thường: bot gửi nguyên văn vào chat Muse, nó
  nằm trong `muse_team.json` và trong ô ngữ cảnh trên dashboard. Mã hoá file skill chỉ làm khó người mua thật, người
  muốn chép vẫn chép được từ Muse hoặc từ file cấu hình sau khi áp dụng.
- Vì vậy **đừng bán "file chữ"**, hãy bán thứ không chép được: **bản cập nhật liên tục, kết quả đã kiểm chứng, công cụ
  đi kèm và hỗ trợ**. Hợp nhất là **gói thuê bao "Skill Store"**: key license mở quyền tải bộ skill mới nhất, skill
  mới hằng tháng, bộ nhân vật khoá mẫu, kênh hỗ trợ.
- Bước đầu ít rủi ro: **Lemon Squeezy hoặc Polar** (có sẵn key license + API kiểm tra, tự lo thuế / hoá đơn quốc tế),
  bán **gói trả 1 lần + thuê bao**, giao skill qua file `.json` cài bằng nút *Cài skill từ file*. Chỉ thêm kiểm tra key
  trong dashboard khi có người mua thật.
- **Cần làm rõ 2 điểm pháp lý trước khi thu tiền:** giấy phép của chính repo Muse2Tele (hiện **chưa có file
  LICENSE** ở thư mục gốc) và điều khoản dùng muse.ai (bot điều khiển giao diện web của Muse qua trình duyệt).

## 2. Hiện trạng trong repo (sau thay đổi này)

| Thứ đã có | Ý nghĩa cho thương mại hoá |
|---|---|
| Skill = 1 file JSON (`docs/SKILL_PACKS.md`), có trường `license`, `price`, `homepage`, `author`, `version` | Đóng gói, đặt tên, phiên bản hoá được từng sản phẩm. |
| 6 skill miễn phí trong `foxprofile/repo/src/core/skills/` | Làm "bản dùng thử" / phễu kéo người dùng. |
| Skill chủ cài vào `muse_telebot/skills/` (không bị cập nhật ghi đè, git bỏ qua) | Chỗ chứa skill trả phí, tách khỏi repo công khai. |
| Dashboard: thẻ skill có nhãn license, nút Cài / Gỡ; API `GET/POST/DELETE /settings/muse-team/skills` | Kênh giao hàng: người mua tải file về và cài. |
| `features: ["video"]` + `settings` trong skill | Skill bán được là "cách làm việc trọn gói" chứ không chỉ là đoạn chữ. |
| Nhiều đội, mỗi đội 1 nhóm Telegram | Phân khúc theo số đội / số kênh (xem mục 4). |

Chưa có: kiểm tra key license, danh mục skill trực tuyến, chữ ký xác thực skill chính chủ.

## 3. Thứ gì có thể bảo vệ, thứ gì không

| Tài sản | Bảo vệ được? | Cách giữ giá trị |
|---|---|---|
| Văn bản ngữ cảnh chỉ huy / thành viên | Không (lộ khi dùng) | Cập nhật thường xuyên theo trend; người mua trả tiền cho bản mới, không phải bản cũ. |
| Bộ nhân vật khoá (ảnh), bối cảnh, ảnh tham chiếu | Một phần (file ảnh, có thể đóng dấu) | Bán kèm skill như tài sản số; ghi điều khoản dùng. |
| Điểm chất lượng đã kiểm chứng (vd bộ 4 mẫu không lời đã thử trên Muse8 ngày 2026-11-08) | Có (là dữ liệu của mình) | Ghi "đã thử, điểm trung bình X/10, lỗi thường gặp" trên trang bán: lý do để mua thay vì tự viết. |
| Tính năng bot (đo kỹ thuật, tạo hình, đăng bài) | Có nếu tách thành phần trả phí phía máy chủ | Giai đoạn sau: chức năng nặng (phân tích video mẫu, chấm tự động) chạy trên máy chủ, gọi bằng key. |
| Hỗ trợ, cộng đồng, cập nhật | Có | Phần chính của thuê bao. |

Mã hoá / làm rối skill trong client: không khuyến nghị (tốn công, dễ gỡ, gây lỗi cho người mua).

## 4. Mô hình bán

1. **Freemium theo skill**: skill có sẵn trong repo miễn phí (đang có 6). Skill chuyên sâu theo ngách (review sản
   phẩm, bán hàng TikTok Shop, kênh trẻ em an toàn, hoạt hình 3D theo series...) bán riêng, 1 lần.
2. **Thuê bao Skill Store** (khuyến nghị làm doanh thu chính): mỗi tháng skill mới + cập nhật skill cũ theo xu hướng,
   bộ nhân vật mẫu, báo cáo "skill nào đang chạy tốt". Hết hạn thì giữ bản đã tải nhưng không nhận bản mới.
3. **Gói theo quy mô**: giới hạn số đội (= số nhóm Telegram) hoặc số profile dùng skill trả phí. Dễ hiểu với người
   chạy nhiều kênh. Chỉ thực thi được khi có kiểm tra key (mục 5, bước 2).
4. **Dịch vụ**: viết skill riêng cho kênh của khách, cài đặt hộ, đào tạo. Không cần thêm code.
5. **Chợ skill (về sau)**: cho tác giả khác bán skill, chia doanh thu. Cần chữ ký xác thực + kiểm duyệt nội dung.

## 5. Lộ trình kỹ thuật

| Bước | Việc | Công sức |
|---|---|---|
| 1 (đã xong) | Định dạng skill JSON, cài từ file, nhãn license, thư mục skill riêng của chủ | — |
| 2 | Nhập key license trên dashboard; FoxProfile gọi API kiểm tra key (Lemon Squeezy `POST /v1/licenses/activate` + `/validate`, hoặc Polar `/v1/customer-portal/license-keys/validate`), lưu mã kích hoạt; skill có `license` khác `free` cần key hợp lệ mới **tải / cập nhật** (không khoá skill đã cài). | 1-2 ngày |
| 3 | Danh mục skill trực tuyến: file `catalog.json` (id, version, giá, link mua, link tải có ký); dashboard hiện tab "Cửa hàng", báo skill có bản mới. | 2-3 ngày |
| 4 | Ký skill chính chủ (Ed25519): dashboard hiện dấu "LinkGold xác thực", cảnh báo skill lạ. Cần cho chợ skill. | 1 ngày |
| 5 | Tính năng trả phí phía máy chủ (phân tích video mẫu, gợi ý kịch bản) gọi bằng key. | lớn, làm khi có doanh thu |

Ghi chú nền tảng (đã kiểm tra tài liệu):
- **Lemon Squeezy**: License API riêng, gọi bằng chính key (không lộ API key của người bán), có activate / validate /
  deactivate theo "instance"; không tắt được key qua API, phải tắt trên dashboard. Là Merchant of Record nên lo thuế.
- **Polar**: license key là "benefit" gắn vào sản phẩm, tự thu hồi khi huỷ thuê bao, có giới hạn số lần kích hoạt;
  phải gửi `organization_id` khi kiểm tra; đường dẫn API từng đổi, cần đọc tài liệu hiện hành khi làm.
- Khách Việt Nam: cân nhắc thêm kênh thanh toán nội địa (chuyển khoản / ví) cấp key thủ công ở giai đoạn đầu.

## 6. Pháp lý và rủi ro

- **Giấy phép repo**: thư mục gốc Muse2Tele chưa có LICENSE (mặc định mọi quyền thuộc tác giả, người khác không có
  quyền dùng lại rõ ràng). Thư mục `foxprofile/repo` là FoxProfile của tác giả khác theo **MIT**: được dùng thương mại
  nhưng phải giữ thông báo bản quyền MIT khi phân phối. Đề xuất: chọn giấy phép cho phần code Muse2Tele, và **tách
  giấy phép nội dung skill** (skill miễn phí: CC BY 4.0; skill trả phí: điều khoản sử dụng riêng, cấm bán lại / chia sẻ).
- **Điều khoản muse.ai**: bot tự động hoá giao diện web Muse qua trình duyệt chống phát hiện. Bán sản phẩm xây trên
  việc này có rủi ro bị chặn tài khoản / bị yêu cầu ngừng. Đọc ToS của Muse, tránh quảng cáo theo hướng "lách" nền tảng.
- **Nội dung skill**: các skill hiện có nhắc tên tác phẩm / nhân vật của người khác (Chaplin, Mr. Bean, Larva, Oggy,
  Shaun the Sheep, Simon's Cat...) như *tham khảo nhịp gag*, có ghi không dùng nhân vật của họ. Khi bán, không dùng các
  tên này làm tên sản phẩm hay hình quảng cáo.
- **Trẻ em và an toàn**: skill gia đình / trẻ em đã có luật an toàn; giữ và nêu rõ trên trang bán.
- **Kết quả không đảm bảo**: chất lượng phụ thuộc Muse; ghi rõ "kết quả thử nghiệm", không hứa điểm / lượt xem.

## 7. Việc nên làm tiếp (theo thứ tự)

1. Quyết định giấy phép cho repo + điều khoản nội dung skill.
2. Đọc ToS muse.ai, quyết định mức độ quảng bá.
3. Làm 2-3 skill trả phí đầu tiên từ các mẫu đã thử tốt, kèm số liệu thử nghiệm, bán dạng file qua Lemon Squeezy / Polar.
4. Có người mua thì làm bước 2-3 của lộ trình (key + danh mục cập nhật).
