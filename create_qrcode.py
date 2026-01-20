import qrcode

# 1. Nhập địa chỉ trang web công ty của bạn
url_cong_ty = "https://www.chatiip.com/"  # Thay đổi link này thành web của bạn

# 2. Cấu hình chi tiết cho QR Code
qr = qrcode.QRCode(
    version=2,  # Kích thước ma trận (1 là nhỏ nhất, 40 là lớn nhất)
    error_correction=qrcode.constants.ERROR_CORRECT_H, # Mức độ sửa lỗi (H là cao nhất, giúp QR vẫn đọc được nếu bị che/bẩn 1 phần)
    box_size=10, # Kích thước của mỗi ô vuông nhỏ (pixel)
    border=4,    # Độ dày viền trắng xung quanh (tiêu chuẩn là 4)
)

# 3. Thêm dữ liệu vào
qr.add_data(url_cong_ty)
qr.make(fit=True)

# 4. Tạo hình ảnh (tùy chỉnh màu sắc)
# fill_color: Màu của mã QR (thường là đen)
# back_color: Màu nền (thường là trắng)
img = qr.make_image(fill_color="black", back_color="white")

# 5. Lưu file ảnh
ten_file = "qr_code.png"
img.save(ten_file)

print(f"Đã tạo xong mã QR! Kiểm tra file '{ten_file}' trong thư mục của bạn.")