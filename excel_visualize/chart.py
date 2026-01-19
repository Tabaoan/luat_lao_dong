import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import io
import base64
import pandas as pd
import os
from datetime import datetime

# ================= CẤU HÌNH =================
plt.rcParams['font.sans-serif'] = ['Arial', 'DejaVu Sans', 'Liberation Sans', 'sans-serif']

# --- FIX ĐƯỜNG DẪN TUYỆT ĐỐI ---
# 1. Lấy vị trí của file chart.py hiện tại (.../project/excel_visualize)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# 2. Lấy thư mục gốc dự án (project) bằng cách đi ngược ra 1 cấp
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
# 3. Nối vào folder assets
LOGO_PATH = os.path.join(PROJECT_ROOT, "assets", "company_logos.png")
QR_PATH = os.path.join(PROJECT_ROOT, "assets", "chatiip.png")

# Debug: In ra để kiểm tra xem code tìm thấy file chưa
print(f"Checking Logo Path: {LOGO_PATH} -> Exists: {os.path.exists(LOGO_PATH)}")
# ============================================

def _clean_name_for_label(name: str) -> str:
    """Làm ngắn tên KCN để hiển thị trục X cho đẹp"""
    s = str(name)
    for prefix in ["Khu công nghiệp", "Cụm công nghiệp", "KCN", "CCN", "Khu CN", "Cụm CN"]:
        if s.lower().startswith(prefix.lower()):
            s = s[len(prefix):].strip()
            if s.startswith("-") or s.startswith(":"):
                 s = s[1:].strip()
            if " - " in s:
                s = s.split(" - ")[0]
    return s

def _get_footer_text() -> str:
    """Tạo dòng chữ chân trang với thời gian thực"""
    now = datetime.now()
    time_str = now.strftime("%H:%M ngày %d/%m/%Y")
    return f"Biểu đồ được tạo bởi ChatIIP.com vào lúc {time_str}. Dữ liệu từ IIPMAP.com"

def _add_branding(fig):
    """Thêm Logo và QR vào Figure"""
    # 1. Thêm Logo (Góc trên bên phải)
    if os.path.exists(LOGO_PATH):
        try:
            img_logo = mpimg.imread(LOGO_PATH)
            # [left, bottom, width, height]
            logo_ax = fig.add_axes([0.85, 0.88, 0.13, 0.13], anchor='NE', zorder=10)
            logo_ax.imshow(img_logo)
            logo_ax.axis('off')
        except Exception as e:
            print(f"⚠️ Warning: Lỗi khi đọc file Logo: {e}")
    else:
        # Bổ sung thông báo nếu không tìm thấy file
        print(f"❌ Error: Không tìm thấy file Logo tại: {LOGO_PATH}")

    # 2. Thêm QR (Góc dưới bên phải)
    if os.path.exists(QR_PATH):
        try:
            img_qr = mpimg.imread(QR_PATH)
            # Vị trí góc dưới phải
            qr_ax = fig.add_axes([0.88, 0.02, 0.1, 0.1], anchor='SE', zorder=10)
            qr_ax.imshow(img_qr)
            qr_ax.axis('off')
        except Exception as e:
            print(f"⚠️ Warning: Lỗi khi đọc file QR: {e}")
    else:
        print(f"❌ Error: Không tìm thấy file QR tại: {QR_PATH}")

def _plot_base64(fig) -> str:
    """Helper chuyển Matplotlib Figure sang Base64 string"""
    # Footer text
    fig.text(0.5, 0.01, _get_footer_text(), ha='center', fontsize=10, color='#555555', style='italic')

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    buf.seek(0)
    base64_str = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return base64_str

# ==========================================
# CÁC HÀM VẼ (BAR, BARH, PIE, LINE, DUAL)
# ==========================================

def plot_horizontal_bar_chart(df: pd.DataFrame, title_str: str, col_name: str, color: str, unit: str) -> str:
    """Vẽ biểu đồ cột ngang"""
    df_sorted = df.sort_values(by=col_name, ascending=True).tail(15) 
    names = df_sorted["Tên"].apply(_clean_name_for_label).tolist()
    values = df_sorted[col_name].tolist()

    fig, ax = plt.subplots(figsize=(14, 9))
    bars = ax.barh(names, values, color=color, height=0.6, zorder=3)
    ax.grid(axis='x', linestyle='--', alpha=0.5, zorder=0)
    
    ax.set_xlabel(unit, fontsize=13, fontweight='bold')
    ax.set_title(title_str, fontsize=18, fontweight='bold', pad=20, color='#333333')
    
    for bar in bars:
        width = bar.get_width()
        ax.annotate(f'{width:.1f}', 
                    xy=(width, bar.get_y() + bar.get_height()/2),
                    xytext=(5, 0), textcoords="offset points",
                    ha='left', va='center', fontweight='bold', fontsize=10)
    
    plt.subplots_adjust(top=0.85, bottom=0.1, left=0.25, right=0.85)
    _add_branding(fig)
    return _plot_base64(fig)

def plot_pie_chart(df: pd.DataFrame, title_str: str, col_name: str, unit: str) -> str:
    """Vẽ biểu đồ tròn"""
    df_sorted = df.sort_values(by=col_name, ascending=False)
    
    if len(df_sorted) > 10:
        top_10 = df_sorted.head(10).copy()
        others_val = df_sorted.iloc[10:][col_name].sum()
        other_row = pd.DataFrame([{"Tên": "Khu vực khác", col_name: others_val}])
        df_plot = pd.concat([top_10, other_row], ignore_index=True)
    else:
        df_plot = df_sorted

    names = df_plot["Tên"].apply(_clean_name_for_label).tolist()
    values = df_plot[col_name].tolist()
    
    fig, ax = plt.subplots(figsize=(14, 9))
    
    wedges, texts, autotexts = ax.pie(values, labels=names, autopct='%1.1f%%', 
                                      startangle=90, counterclock=False, 
                                      textprops={'fontsize': 10}, pctdistance=0.85)
    
    centre_circle = plt.Circle((0,0),0.70,fc='white')
    fig.gca().add_artist(centre_circle)

    ax.set_title(title_str, fontsize=18, fontweight='bold', pad=30, color='#333333')
    plt.setp(autotexts, size=9, weight="bold", color="black")
    
    plt.subplots_adjust(top=0.85, bottom=0.1, left=0.1, right=0.9)
    _add_branding(fig)
    return _plot_base64(fig)

def plot_line_chart(df: pd.DataFrame, title_str: str, col_name: str, color: str, unit: str) -> str:
    """Vẽ biểu đồ đường"""
    df_sorted = df.sort_values(by=col_name, ascending=False).head(15)
    names = df_sorted["Tên"].apply(_clean_name_for_label).tolist()
    values = df_sorted[col_name].tolist()

    fig, ax = plt.subplots(figsize=(14, 9))
    
    ax.plot(names, values, marker='o', linestyle='-', color=color, linewidth=3, markersize=10, zorder=3)
    ax.grid(True, linestyle='--', alpha=0.5, zorder=0)
    
    ax.set_ylabel(unit, fontsize=13, fontweight='bold')
    ax.set_title(title_str, fontsize=18, fontweight='bold', pad=30, color='#333333')
    
    ax.set_xticklabels(names, rotation=90, ha='center', fontsize=11)

    for i, txt in enumerate(values):
        ax.annotate(f"{txt:.1f}", (names[i], values[i]), xytext=(0, 10), 
                    textcoords='offset points', ha='center', fontweight='bold', fontsize=10)

    plt.subplots_adjust(top=0.85, bottom=0.30, left=0.1, right=0.85)
    _add_branding(fig)
    return _plot_base64(fig)

def plot_price_bar_chart_base64(df: pd.DataFrame, title_location: str, industrial_type: str) -> str:
    df_sorted = df.sort_values(by="Giá số", ascending=False).head(15)
    names = df_sorted["Tên"].apply(_clean_name_for_label).tolist()
    values = df_sorted["Giá số"].tolist()
    
    fig, ax = plt.subplots(figsize=(14, 9))
    bars = ax.bar(names, values, color="#1f77b4", width=0.6, zorder=3)
    ax.grid(axis='y', linestyle='--', alpha=0.5, zorder=0)

    ax.set_ylabel("Giá thuê (USD/m²/năm)", fontsize=13, fontweight='bold')
    ax.set_title(f"GIÁ THUÊ ĐẤT {industrial_type.upper()}\nTẠI {title_location.upper()}", 
                 fontsize=18, fontweight='bold', pad=30, color='#333333')
    
    ax.set_xticklabels(names, rotation=90, ha='center', fontsize=11)
    
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{height:.1f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 5), textcoords="offset points",
                    ha='center', va='bottom', fontweight='bold', fontsize=10)

    plt.subplots_adjust(top=0.85, bottom=0.30, left=0.1, right=0.85)
    _add_branding(fig)
    return _plot_base64(fig)

def plot_area_bar_chart_base64(df: pd.DataFrame, title_location: str, industrial_type: str) -> str:
    df_sorted = df.sort_values(by="Diện tích số", ascending=False).head(15)
    names = df_sorted["Tên"].apply(_clean_name_for_label).tolist()
    values = df_sorted["Diện tích số"].tolist()
    
    fig, ax = plt.subplots(figsize=(14, 9))
    bars = ax.bar(names, values, color="#2ca02c", width=0.6, zorder=3)
    ax.grid(axis='y', linestyle='--', alpha=0.5, zorder=0)
    
    ax.set_ylabel("Diện tích (ha)", fontsize=13, fontweight='bold')
    ax.set_title(f"DIỆN TÍCH {industrial_type.upper()}\nTẠI {title_location.upper()}", 
                 fontsize=18, fontweight='bold', pad=30, color='#333333')
    
    ax.set_xticklabels(names, rotation=90, ha='center', fontsize=11)
    
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{int(height)}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 5), textcoords="offset points",
                    ha='center', va='bottom', fontweight='bold', fontsize=10)

    plt.subplots_adjust(top=0.85, bottom=0.30, left=0.1, right=0.85)
    _add_branding(fig)
    return _plot_base64(fig)

def plot_dual_bar_chart_base64(df: pd.DataFrame, title_location: str, industrial_type: str) -> str:
    """Vẽ biểu đồ đôi (Dual)"""
    df_sorted = df.sort_values(by="Giá số", ascending=False).head(10)
    
    names = df_sorted["Tên"].apply(_clean_name_for_label).tolist()
    prices = df_sorted["Giá số"].fillna(0).tolist()
    areas = df_sorted["Diện tích số"].fillna(0).tolist()
    
    x = range(len(names))
    width = 0.35

    fig, ax1 = plt.subplots(figsize=(14, 9))

    # Trục 1: Giá
    bars1 = ax1.bar([i - width/2 for i in x], prices, width, label='Giá thuê', color='#1f77b4', zorder=3)
    ax1.set_ylabel('Giá thuê (USD/m²/năm)', color='#1f77b4', fontsize=13, fontweight='bold')
    ax1.tick_params(axis='y', labelcolor='#1f77b4')
    ax1.grid(axis='y', linestyle='--', alpha=0.5, zorder=0)
    
    # Trục 2: Diện tích
    ax2 = ax1.twinx()
    bars2 = ax2.bar([i + width/2 for i in x], areas, width, label='Diện tích', color='#2ca02c', zorder=3)
    ax2.set_ylabel('Diện tích (ha)', color='#2ca02c', fontsize=13, fontweight='bold')
    ax2.tick_params(axis='y', labelcolor='#2ca02c')

    ax1.set_title(f"TỔNG QUAN GIÁ & DIỆN TÍCH {industrial_type.upper()}\nTẠI {title_location.upper()}", 
                  fontsize=18, fontweight='bold', pad=30, color='#333333')
    ax1.set_xticks(x)
    ax1.set_xticklabels(names, rotation=90, ha='center', fontsize=11)

    for bar in bars1:
        if bar.get_height() > 0:
            ax1.annotate(f'{bar.get_height():.0f}',
                         xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                         xytext=(0, 3), textcoords="offset points",
                         ha='center', va='bottom', fontsize=9, color='#1f77b4', fontweight='bold')
    
    for bar in bars2:
        if bar.get_height() > 0:
            ax2.annotate(f'{int(bar.get_height())}',
                         xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                         xytext=(0, 3), textcoords="offset points",
                         ha='center', va='bottom', fontsize=9, color='#2ca02c', fontweight='bold')

    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines + lines2, labels + labels2, loc='upper left')

    plt.subplots_adjust(top=0.85, bottom=0.30, left=0.1, right=0.85)
    _add_branding(fig)
    return _plot_base64(fig)