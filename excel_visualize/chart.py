# File: excel_visualize/chart.py
import matplotlib.pyplot as plt
import io
import base64
import pandas as pd

# Cấu hình font tiếng Việt (nếu chạy trên môi trường không có font, có thể bị lỗi ô vuông)
# Bạn có thể cần cài thêm font hoặc bỏ qua nếu server đã config
plt.rcParams['font.sans-serif'] = ['Arial', 'DejaVu Sans', 'Liberation Sans'] 

def _clean_name_for_label(name: str) -> str:
    """Làm ngắn tên KCN để hiển thị trục X cho đẹp"""
    s = str(name)
    # Cắt bỏ các tiền tố dài dòng
    for prefix in ["Khu công nghiệp", "Cụm công nghiệp", "KCN", "CCN"]:
        if s.lower().startswith(prefix.lower()):
            s = s[len(prefix):].strip()
            # Xử lý trường hợp "Khu công nghiệp A - Tỉnh B" -> Lấy "A"
            if " - " in s:
                s = s.split(" - ")[0]
    return s

def _plot_base64(fig) -> str:
    """Helper chuyển Matplotlib Figure sang Base64 string"""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight')
    buf.seek(0)
    base64_str = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return base64_str

def plot_price_bar_chart_base64(df: pd.DataFrame, title_location: str, industrial_type: str) -> str:
    """
    Vẽ biểu đồ giá thuê đất.
    - df: DataFrame đã có cột 'Giá số'
    - title_location: Tên tỉnh hoặc danh sách khu vực (để hiển thị trên tiêu đề)
    """
    # Sắp xếp giá giảm dần
    df_sorted = df.sort_values(by="Giá số", ascending=False).head(15) # Lấy top 15 nếu quá nhiều
    
    names = df_sorted["Tên"].apply(_clean_name_for_label).tolist()
    values = df_sorted["Giá số"].tolist()
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Vẽ cột màu xanh dương
    bars = ax.bar(names, values, color="#1f77b4")
    
    # Label trục
    ax.set_ylabel("Giá thuê (USD/m²/năm)", fontsize=12)
    ax.set_title(f"Giá thuê đất {industrial_type} tại {title_location}", fontsize=14, fontweight='bold', pad=20)
    
    # Xoay tên trục X nếu dài
    plt.xticks(rotation=45, ha='right')
    
    # Hiển thị giá trị trên đầu cột
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{height:.1f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),  # 3 points vertical offset
                    textcoords="offset points",
                    ha='center', va='bottom')

    plt.tight_layout()
    return _plot_base64(fig)

def plot_area_bar_chart_base64(df: pd.DataFrame, title_location: str, industrial_type: str) -> str:
    """
    Vẽ biểu đồ diện tích.
    - df: DataFrame đã có cột 'Diện tích số'
    """
    # Sắp xếp diện tích giảm dần
    df_sorted = df.sort_values(by="Diện tích số", ascending=False).head(15)
    
    names = df_sorted["Tên"].apply(_clean_name_for_label).tolist()
    values = df_sorted["Diện tích số"].tolist()
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Vẽ cột màu xanh lá cây
    bars = ax.bar(names, values, color="#2ca02c")
    
    ax.set_ylabel("Diện tích (ha)", fontsize=12)
    ax.set_title(f"Diện tích {industrial_type} tại {title_location}", fontsize=14, fontweight='bold', pad=20)
    
    plt.xticks(rotation=45, ha='right')
    
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{int(height)}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha='center', va='bottom')

    plt.tight_layout()
    return _plot_base64(fig)