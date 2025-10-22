# Google Drive API Setup Guide

## Bước 1: Cài đặt thư viện

```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

## Bước 2: Tạo Google Cloud Project

1. Truy cập [Google Cloud Console](https://console.cloud.google.com/)
2. Tạo project mới hoặc chọn project có sẵn
3. Enable **Google Drive API**:
   - Vào **APIs & Services** > **Library**
   - Tìm "Google Drive API"
   - Click **Enable**

## Bước 3: Tạo OAuth 2.0 Credentials

1. Vào **APIs & Services** > **Credentials**
2. Click **Create Credentials** > **OAuth client ID**
3. Chọn **Application type**: **Desktop app**
4. Đặt tên: `Turnitin Bot`
5. Click **Create**
6. Download file JSON
7. Đổi tên file thành `credentials.json`
8. Copy vào thư mục bot

## Bước 4: Chạy lần đầu

Lần đầu chạy bot, sẽ mở trình duyệt để login Google:

1. Chọn tài khoản Google
2. Click **Allow** để cấp quyền
3. Bot sẽ tạo file `token.pickle` để lưu credentials

## Bước 5: Test

Upload file lên bot và kiểm tra:

- Bot sẽ upload reports lên Google Drive
- Gửi link download cho user
- Link có dạng:
  - View: `https://drive.google.com/file/d/FILE_ID/view`
  - Download: `https://drive.google.com/uc?export=download&id=FILE_ID`

## Lưu ý:

- File `credentials.json` và `token.pickle` đã được thêm vào `.gitignore`
- Không commit 2 files này lên Git
- Link download có thời hạn 24h (có thể config)
- Files trên Drive có thể tự động xóa sau khi gửi (optional)

## Troubleshooting:

### Lỗi: "credentials.json not found"

- Download lại credentials từ Google Cloud Console
- Đảm bảo file tên đúng là `credentials.json`

### Lỗi: "Access denied"

- Enable Google Drive API trong Google Cloud Console
- Kiểm tra OAuth consent screen đã setup chưa

### Lỗi: "Token expired"

- Xóa file `token.pickle`
- Chạy lại bot để login lại
