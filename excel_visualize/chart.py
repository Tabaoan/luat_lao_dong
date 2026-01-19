import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import io
import base64
import pandas as pd
import os
from datetime import datetime

# ================= CẤU HÌNH =================
plt.rcParams['font.sans-serif'] = ['Arial', 'DejaVu Sans', 'Liberation Sans', 'sans-serif']

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(CURRENT_DIR, "assets", "company_logos.png")
QR_PATH = os.path.join(CURRENT_DIR, "assets", "chatiip.png")
# ============================================

def _clean_name_for_label(name: str) -> str:
    s = str(name)
    for prefix in ["Khu công nghiệp", "Cụm công nghiệp", "KCN", "CCN", "Khu CN", "Cụm CN"]:
        if s.lower().startswith(prefix.lower()):
            s = s[len(prefix):].strip()
            if s.startswith("-") or s.startswith(":"): s = s[1:].strip()
            if " - " in s: s = s.split(" - ")[0]
    return s

def _get_footer_text() -> str:
    now = datetime.now()
    time_str = now.strftime("%H:%M ngày %d/%m/%Y")
    return f"Biểu đồ được tạo bởi ChatIIP.com vào lúc {time_str}. Dữ liệu từ IIPMAP.com"

def _add_branding(fig):
    if os.path.exists(LOGO_PATH):
        try:
            img_logo = mpimg.imread(LOGO_PATH)
            logo_ax = fig.add_axes([0.85, 0.88, 0.13, 0.13], anchor='NE', zorder=10)
            logo_ax.imshow(img_logo)
            logo_ax.axis('off')
        except: pass
    if os.path.exists(QR_PATH):
        try:
            img_qr = mpimg.imread(QR_PATH)
            qr_ax = fig.add_axes([0.88, 0.02, 0.1, 0.1], anchor='SE', zorder=10)
            qr_ax.imshow(img_qr)
            qr_ax.axis('off')
        except: pass

def _plot_base64(fig) -> str:
    fig.text(0.5, 0.01, _get_footer_text(), ha='center', fontsize=10, color='#555555', style='italic')
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    buf.seek(0)
    base64_str = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return base64_str

# =========================================================
# HELPER: TẠO SỐ THỨ TỰ KHOANH TRÒN (❶ Tên...)
# =========================================================
def _convert_to_circled_num(i: int) -> str:
    """Chuyển số nguyên i (bắt đầu từ 1) thành ký tự khoanh tròn Unicode"""
    # 1-10: ❶..❿ (U+2776 - U+277F)
    if 1 <= i <= 10:
        return chr(0x2776 + i - 1)
    # 11-20: ⓫..⓴ (U+24EB - U+24F4)
    elif 11 <= i <= 20:
        return chr(0x24EB + i - 11)
    # >20: Dùng (n)
    else:
        return f"({i})"

def _get_circled_names(df: pd.DataFrame) -> list:
    """Trả về danh sách tên có kèm số khoanh tròn: ❶ Tên A, ❷ Tên B..."""
    raw_names = df["Tên"].apply(_clean_name_for_label).tolist()
    circled_names = []
    for i, name in enumerate(raw_names):
        prefix = _convert_to_circled_num(i + 1)
        circled_names.append(f"{prefix} {name}")
    return circled_names

# =========================================================
# CÁC HÀM VẼ (ĐÃ UPDATE STYLE MỚI)
# =========================================================

def plot_horizontal_bar_chart(df: pd.DataFrame, title_str: str, col_name: str, color: str, unit: str) -> str:
    # Barh vẽ từ dưới lên, cần đảo ngược để số 1 nằm trên cùng
    df_reversed = df.iloc[::-1]
    
    # Tạo tên có số trước khi đảo ngược để khớp index
    names_desc = _get_circled_names(df) # [❶ Max, ❷ 2nd...]
    names_asc = names_desc[::-1]       # [Min, ..., ❶ Max]
    
    values = df_reversed[col_name].tolist()
    num_items = len(values)

    fig_height = max(9, num_items * 0.5)
    fig, ax = plt.subplots(figsize=(14, fig_height))
    
    bars = ax.barh(names_asc, values, color=color, height=0.6, zorder=3)
    ax.grid(axis='x', linestyle='--', alpha=0.5, zorder=0)
    
    ax.set_xlabel(unit, fontsize=13, fontweight='bold')
    ax.set_title(title_str, fontsize=18, fontweight='bold', pad=20, color='#333333')
    
    font_size = 10 if num_items < 30 else 8
    
    for bar in bars:
        width = bar.get_width()
        ax.annotate(f'{width:.1f}', 
                    xy=(width, bar.get_y() + bar.get_height()/2),
                    xytext=(5, 0), textcoords="offset points",
                    ha='left', va='center', fontweight='bold', fontsize=font_size)
    
    plt.subplots_adjust(top=1 - (1.5/fig_height), bottom=0.5/fig_height, left=0.25, right=0.85)
    _add_branding(fig)
    return _plot_base64(fig)

def plot_pie_chart(df: pd.DataFrame, title_str: str, col_name: str, unit: str) -> str:
    names = _get_circled_names(df)
    values = df[col_name].tolist()
    
    fig_size = 14 if len(names) < 20 else 20
    fig, ax = plt.subplots(figsize=(fig_size, fig_size))
    
    wedges, texts, autotexts = ax.pie(values, labels=names, autopct='%1.1f%%', 
                                      startangle=90, counterclock=False, 
                                      textprops={'fontsize': 9}, pctdistance=0.85, labeldistance=1.05)
    
    centre_circle = plt.Circle((0,0),0.70,fc='white')
    fig.gca().add_artist(centre_circle)

    ax.set_title(title_str, fontsize=18, fontweight='bold', pad=30, color='#333333')
    plt.setp(autotexts, size=8, weight="bold", color="black")
    
    plt.subplots_adjust(top=0.9, bottom=0.1, left=0.1, right=0.9)
    _add_branding(fig)
    return _plot_base64(fig)

def plot_line_chart(df: pd.DataFrame, title_str: str, col_name: str, color: str, unit: str) -> str:
    names = _get_circled_names(df)
    values = df[col_name].tolist()
    num_items = len(names)

    fig_width = max(14, num_items * 0.4)
    fig, ax = plt.subplots(figsize=(fig_width, 9))
    
    ax.plot(names, values, marker='o', linestyle='-', color=color, linewidth=2, markersize=8, zorder=3)
    ax.grid(True, linestyle='--', alpha=0.5, zorder=0)
    
    ax.set_ylabel(unit, fontsize=13, fontweight='bold')
    ax.set_title(title_str, fontsize=18, fontweight='bold', pad=30, color='#333333')
    ax.set_xticklabels(names, rotation=90, ha='center', fontsize=10)

    for i, txt in enumerate(values):
        ax.annotate(f"{txt:.1f}", (names[i], values[i]), xytext=(0, 10), 
                    textcoords='offset points', ha='center', fontweight='bold', fontsize=9)

    plt.subplots_adjust(top=0.85, bottom=0.30, left=0.1, right=0.85)
    _add_branding(fig)
    return _plot_base64(fig)

def plot_price_bar_chart_base64(df: pd.DataFrame, title_location: str, industrial_type: str) -> str:
    names = _get_circled_names(df)
    values = df["Giá số"].tolist()
    num_items = len(names)

    fig_width = max(14, num_items * 0.5) 
    fig, ax = plt.subplots(figsize=(fig_width, 9))
    
    bars = ax.bar(names, values, color="#1f77b4", width=0.6, zorder=3)
    ax.grid(axis='y', linestyle='--', alpha=0.5, zorder=0)

    ax.set_ylabel("Giá thuê (USD/m²/năm)", fontsize=13, fontweight='bold')
    ax.set_title(f"GIÁ THUÊ ĐẤT {industrial_type.upper()}\nTẠI {title_location.upper()}", 
                 fontsize=18, fontweight='bold', pad=30, color='#333333')
    
    ax.set_xticklabels(names, rotation=90, ha='center', fontsize=10)
    
    # Chỉ hiển thị giá trị, KHÔNG vẽ vòng tròn đè lên nữa (vì đã có ở tên trục)
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{height:.1f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 5), textcoords="offset points",
                    ha='center', va='bottom', fontweight='bold', fontsize=9)

    plt.subplots_adjust(top=0.85, bottom=0.35, left=0.1, right=0.9)
    _add_branding(fig)
    return _plot_base64(fig)

def plot_area_bar_chart_base64(df: pd.DataFrame, title_location: str, industrial_type: str) -> str:
    names = _get_circled_names(df)
    values = df["Diện tích số"].tolist()
    num_items = len(names)

    fig_width = max(14, num_items * 0.5)
    fig, ax = plt.subplots(figsize=(fig_width, 9))
    
    bars = ax.bar(names, values, color="#2ca02c", width=0.6, zorder=3)
    ax.grid(axis='y', linestyle='--', alpha=0.5, zorder=0)
    
    ax.set_ylabel("Diện tích (ha)", fontsize=13, fontweight='bold')
    ax.set_title(f"DIỆN TÍCH {industrial_type.upper()}\nTẠI {title_location.upper()}", 
                 fontsize=18, fontweight='bold', pad=30, color='#333333')
    
    ax.set_xticklabels(names, rotation=90, ha='center', fontsize=10)
    
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{int(height)}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 5), textcoords="offset points",
                    ha='center', va='bottom', fontweight='bold', fontsize=9)

    plt.subplots_adjust(top=0.85, bottom=0.35, left=0.1, right=0.9)
    _add_branding(fig)
    return _plot_base64(fig)

def plot_dual_bar_chart_base64(df: pd.DataFrame, title_location: str, industrial_type: str) -> str:
    names = _get_circled_names(df)
    prices = df["Giá số"].fillna(0).tolist()
    areas = df["Diện tích số"].fillna(0).tolist()
    num_items = len(names)
    
    fig_width = max(14, num_items * 0.5)
    fig, ax1 = plt.subplots(figsize=(fig_width, 9))
    
    x = range(len(names))
    width = 0.35

    bars1 = ax1.bar([i - width/2 for i in x], prices, width, label='Giá thuê', color='#1f77b4', zorder=3)
    ax1.set_ylabel('Giá thuê (USD/m²/năm)', color='#1f77b4', fontsize=13, fontweight='bold')
    ax1.tick_params(axis='y', labelcolor='#1f77b4')
    ax1.grid(axis='y', linestyle='--', alpha=0.5, zorder=0)
    
    ax2 = ax1.twinx()
    bars2 = ax2.bar([i + width/2 for i in x], areas, width, label='Diện tích', color='#2ca02c', zorder=3)
    ax2.set_ylabel('Diện tích (ha)', color='#2ca02c', fontsize=13, fontweight='bold')
    ax2.tick_params(axis='y', labelcolor='#2ca02c')

    ax1.set_title(f"TỔNG QUAN GIÁ & DIỆN TÍCH {industrial_type.upper()}\nTẠI {title_location.upper()}", 
                  fontsize=18, fontweight='bold', pad=30, color='#333333')
    ax1.set_xticks(x)
    ax1.set_xticklabels(names, rotation=90, ha='center', fontsize=10)

    for bar in bars1:
        if bar.get_height() > 0:
            ax1.annotate(f'{bar.get_height():.0f}',
                         xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                         xytext=(0, 3), textcoords="offset points",
                         ha='center', va='bottom', fontsize=8, color='#1f77b4', fontweight='bold')
            
    for bar in bars2:
        if bar.get_height() > 0:
            ax2.annotate(f'{int(bar.get_height())}',
                         xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                         xytext=(0, 3), textcoords="offset points",
                         ha='center', va='bottom', fontsize=9, color='#2ca02c', fontweight='bold')

    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines + lines2, labels + labels2, loc='upper left')

    plt.subplots_adjust(top=0.85, bottom=0.35, left=0.1, right=0.9)
    _add_branding(fig)
    return _plot_base64(fig)