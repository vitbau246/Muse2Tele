# Skill pack (định dạng 1)

Skill pack là 1 file JSON gói sẵn cách làm việc cho 1 đội Muse: ngữ cảnh (bộ nhớ dài hạn) cho chỉ huy, cho thành
viên, vai trò thành viên và các thiết lập đi kèm. Dashboard → **Đội Muse** → **Skill** → **Áp dụng** điền cho cả đội;
chủ sửa lại được trước khi **Lưu**.

- Skill có sẵn: `foxprofile/repo/src/core/skills/*.json` (đi cùng bản cập nhật).
- Skill chủ cài (mua, được chia sẻ, tự viết): `muse_telebot/skills/<id>.json`. Cài bằng nút **Cài skill từ file
  (.json)** hoặc `POST /api/v1/settings/muse-team/skills` (body = nội dung file). Thư mục này không bị bản cập nhật ghi
  đè và không đưa lên git. Không được trùng `id` với skill có sẵn.

```json
{
  "format": 1,
  "id": "shop_review",
  "label": "Review sản phẩm — có thoại",
  "description": "1-2 câu hiện trên thẻ skill.",
  "version": "1.0.0",
  "author": "Tên tác giả",
  "license": "free",
  "category": "video",
  "homepage": "https://...",
  "price": "",
  "features": ["video"],
  "settings": {"one_video": true, "show_failed_media": false, "post_mode": "ask"},
  "member_role": "Vai trò điền vào ô vai trò còn trống của thành viên",
  "chief": "Ngữ cảnh cho Muse chỉ huy (tối đa 6000 ký tự)",
  "member": "Ngữ cảnh cho mỗi Muse thành viên (tối đa 6000 ký tự)",
  "order": 50
}
```

| Trường | Bắt buộc | Ý nghĩa |
|---|---|---|
| `id` | có | 1-40 ký tự `a-z 0-9 - _`, chữ đầu là chữ / số. Cài lại cùng `id` = cập nhật. |
| `label`, `chief`, `member` | có | Tên hiển thị; 2 ngữ cảnh. |
| `features` | không | `["video"]` bật quy trình video của bot: tải video mẫu từ link, đo kỹ thuật video nộp, bước tạo hình, việc nhiều video / chia đoạn, dòng Caption / Hashtag, đăng video đạt, trang tổng hợp video. Bỏ trống = đội việc chung (giao / chấm). |
| `settings` | không | Thiết lập áp vào đội khi chọn skill: `one_video`, `show_failed_media`, `post_mode` (`off` / `ask` / `auto`). Skill video không ghi thì lấy `true / false / ask`. |
| `license`, `price`, `homepage`, `author`, `version`, `category`, `description`, `order` | không | Thông tin hiển thị; `license` khác `free` hiện nhãn trên thẻ. Bot không kiểm tra license (xem [THUONG_MAI_HOA_SKILL.md](THUONG_MAI_HOA_SKILL.md)). |

Trường lạ bị bỏ qua. `format` lớn hơn 1 thì bản Muse2Tele này từ chối (cần cập nhật).

Gợi ý viết ngữ cảnh: chỉ huy nghiên cứu / phân tích / viết kịch bản chi tiết và chấm theo checklist; thành viên chỉ
làm đúng phần được giao, nộp rồi dừng. Ghi cố định dàn nhân vật, phong cách, luật an toàn. Đừng chép cú pháp lệnh
`[[giao: ...]]` vào ngữ cảnh: bot tự gửi cú pháp cho chỉ huy khi giới thiệu đội.
