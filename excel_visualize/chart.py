# File: excel_visualize/chart.py
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import io
import base64
import pandas as pd
import os
from datetime import datetime

# ================= CẤU HÌNH =================
# Cấu hình font (giữ nguyên)
plt.rcParams['font.sans-serif'] = ['Arial', 'DejaVu Sans', 'Liberation Sans', 'sans-serif']

# Đường dẫn đến thư mục chứa ảnh thương hiệu (Cần đảm bảo folder 'assets' tồn tại ở root)
ASSETS_DIR = "assets"
LOGO_PATH = os.path.join(ASSETS_DIR, r"company_logos.png") # Bạn có thể đổi tên file nếu cần
QR_PATH = os.path.join(ASSETS_DIR, r"chatiip.png")
# ============================================


def _clean_name_for_label(name: str) -> str:
    """Làm ngắn tên KCN để hiển thị trục X cho đẹp"""
    s = str(name)
    for prefix in ["Khu công nghiệp", "Cụm công nghiệp", "KCN", "CCN", "Khu CN", "Cụm CN"]:
        if s.lower().startswith(prefix.lower()):
            s = s[len(prefix):].strip()
            if s.startswith("-") or s.startswith(":"):
                 s = s[1:].strip()
            # Xử lý trường hợp "Khu công nghiệp A - Tỉnh B" -> Lấy "A"
            if " - " in s:
                s = s.split(" - ")[0]
    return s

def _get_footer_text() -> str:
    """Tạo dòng chữ chân trang với thời gian thực"""
    now = datetime.now()
    # Format: H giờ M phút, ngày d tháng m năm Y
    time_str = now.strftime("%H giờ %M phút, ngày %d tháng %m năm %Y")
    return f"Biểu đồ được tạo bởi ChatIIP.com vào lúc {time_str}. Dữ liệu được lấy từ IIPMAP.com"

def _add_branding(fig):
    """Thêm Logo (góc trên phải) và QR (góc dưới phải) vào Figure"""
    # 1. Thêm Logo (Góc trên bên phải)
    if os.path.exists(LOGO_PATH):
        try:
            img_logo = mpimg.imread(LOGO_PATH)
            # Tạo một axes mới tại vị trí [left, bottom, width, height] tương đối so với figure
            # 0.87, 0.88 là vị trí góc trên phải. 0.12 là kích thước.
            logo_ax = fig.add_axes([0.87, 0.88, 0.12, 0.12], anchor='NE', zorder=10)
            logo_ax.imshow(img_logo)
            logo_ax.axis('off') # Tắt khung viền của ảnh
        except Exception as e:
            print(f"Warning: Không thể load Logo tại {LOGO_PATH}: {e}")

    # 2. Thêm QR (Góc dưới bên phải)
    if os.path.exists(QR_PATH):
        try:
            img_qr = mpimg.imread(QR_PATH)
            # Vị trí góc dưới phải, nằm trên footer một chút
            qr_ax = fig.add_axes([0.88, 0.03, 0.1, 0.1], anchor='SE', zorder=10)
            qr_ax.imshow(img_qr)
            qr_ax.axis('off')
        except Exception as e:
            print(f"Warning: Không thể load QR tại {QR_PATH}: {e}")

def _plot_base64(fig) -> str:
    """Helper chuyển Matplotlib Figure sang Base64 string"""
    # Thêm footer text vào giữa đáy ảnh
    fig.text(0.5, 0.01, _get_footer_text(), ha='center', fontsize=9, color='gray')

    buf = io.BytesIO()
    # Lưu ý: Không dùng bbox_inches='tight' ở đây vì nó có thể cắt mất các phần tử absolute (logo/qr)
    # Chúng ta đã căn chỉnh margin thủ công trong hàm vẽ.
    fig.savefig(buf, format="png", dpi=100)
    buf.seek(0)
    base64_str = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return base64_str

def plot_price_bar_chart_base64(df: pd.DataFrame, title_location: str, industrial_type: str) -> str:
    # Sắp xếp và lấy top 15
    df_sorted = df.sort_values(by="Giá số", ascending=False).head(15)
    names = df_sorted["Tên"].apply(_clean_name_for_label).tolist()
    values = df_sorted["Giá số"].tolist()
    
    # Tăng kích thước Figure để cân bằng hơn (Rộng 14, Cao 9 inch)
    fig, ax = plt.subplots(figsize=(14, 9))
    
    # Vẽ cột
    bars = ax.bar(names, values, color="#1f77b4", width=0.6)
    
    # Thiết lập trục và tiêu đề
    ax.set_ylabel("Giá thuê (USD/m²/năm)", fontsize=13, fontweight='bold')
    # Tiêu đề dịch lên cao một chút để tránh logo
    ax.set_title(f"GIÁ THUÊ ĐẤT {industrial_type.upper()}\nTẠI {title_location.upper()}", 
                 fontsize=16, fontweight='bold', pad=25, color='#333333')
    
    # Xoay tên trục X thẳng đứng (90 độ)
    ax.set_xticklabels(names, rotation=90, ha='center', fontsize=11)
    
    # Hiển thị giá trị trên đầu cột
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{height:.1f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 5), textcoords="offset points",
                    ha='center', va='bottom', fontweight='bold', fontsize=10)

    # Căn chỉnh lề thủ công để tạo không gian cho Logo, QR và tên trục X dài
    # top=0.85: Chừa chỗ cho logo phía trên tiêu đề
    # bottom=0.25: Chừa chỗ rộng phía dưới cho tên KCN xoay dọc và footer
    # right=0.85: Chừa chỗ bên phải cho logo/qr không đè vào biểu đồ
    plt.subplots_adjust(top=0.88, bottom=0.25, left=0.1, right=0.85)
    
    # Thêm các yếu tố thương hiệu
    _add_branding(fig)
    
    return _plot_base64(fig)

def plot_area_bar_chart_base64(df: pd.DataFrame, title_location: str, industrial_type: str) -> str:
    # Sắp xếp và lấy top 15
    df_sorted = df.sort_values(by="Diện tích số", ascending=False).head(15)
    names = df_sorted["Tên"].apply(_clean_name_for_label).tolist()
    values = df_sorted["Diện tích số"].tolist()
    
    # Tăng kích thước Figure
    fig, ax = plt.subplots(figsize=(14, 9))
    
    # Vẽ cột
    bars = ax.bar(names, values, color="#2ca02c", width=0.6)
    
    # Thiết lập trục và tiêu đề
    ax.set_ylabel("Diện tích (ha)", fontsize=13, fontweight='bold')
    ax.set_title(f"DIỆN TÍCH {industrial_type.upper()}\nTẠI {title_location.upper()}", 
                 fontsize=16, fontweight='bold', pad=25, color='#333333')
    
    # Xoay tên trục X thẳng đứng
    ax.set_xticklabels(names, rotation=90, ha='center', fontsize=11)
    
    # Hiển thị giá trị trên đầu cột
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{int(height)}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 5), textcoords="offset points",
                    ha='center', va='bottom', fontweight='bold', fontsize=10)

    # Căn chỉnh lề thủ công
    plt.subplots_adjust(top=0.88, bottom=0.25, left=0.1, right=0.85)
    
    # Thêm các yếu tố thương hiệu
    _add_branding(fig)
    
    return _plot_base64(fig)