import matplotlib.pyplot as plt
import io
import base64
import os
from PIL import Image
from datetime import datetime
import pytz


# =========================
# 1️⃣ Làm sạch tên khu / cụm
# =========================
def _clean_name(name: str, province: str) -> str:
    n = str(name).lower()
    for kw in [
        "khu công nghiệp",
        "cụm công nghiệp",
        str(province).lower()
    ]:
        n = n.replace(kw, "")
    return n.strip().title()


# =========================
# ✅ NEW: Vẽ số thứ tự bọc tròn dưới trục X
# =========================
def _add_circled_index_under_ticks(ax, n_items: int, y_offset: float = -0.16, fontsize: int = 10):
    """
    Vẽ số thứ tự (1..n) bọc bởi hình tròn, nằm dưới tick label ở trục X.

    - y_offset: vị trí theo hệ trục X (0 = tại trục, âm = xuống dưới)
    """
    for i in range(n_items):
        ax.text(
            i,
            y_offset,
            str(i + 1),
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=fontsize,
            bbox=dict(
                boxstyle="circle,pad=0.25",
                facecolor="white",
                edgecolor="black",
                linewidth=1.2
            ),
            clip_on=False
        )


# =========================
# 2️⃣ Dán logo vào ảnh PNG (ăn chắc)
# =========================
def _overlay_logo_on_png_bytes(
    png_bytes: bytes,
    alpha: float = 0.9,
    scale: float = 0.08,
    padding: int = 20
) -> bytes:
    """
    Dán logo vào góc phải trên của ảnh PNG đã render từ matplotlib.
    """
    logo_path = os.path.join(os.path.dirname(__file__), "assets", "company_logos.png")

    if not os.path.exists(logo_path):
        return png_bytes

    try:
        base_img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        logo = Image.open(logo_path).convert("RGBA")
    except Exception:
        return png_bytes

    new_w = max(1, int(base_img.size[0] * scale))
    ratio = new_w / logo.size[0]
    new_h = max(1, int(logo.size[1] * ratio))
    logo = logo.resize((new_w, new_h), Image.LANCZOS)

    if alpha < 1.0:
        r, g, b, a = logo.split()
        a = a.point(lambda p: int(p * alpha))
        logo = Image.merge("RGBA", (r, g, b, a))

    x = base_img.size[0] - new_w - padding
    y = padding

    base_img.paste(logo, (x, y), logo)

    out = io.BytesIO()
    base_img.convert("RGB").save(out, format="PNG")
    return out.getvalue()


def _overlay_qr_on_png_bytes(
    png_bytes: bytes,
    alpha: float = 1.0,
    scale: float = 0.12,
    padding: int = 20
) -> bytes:
    """
    Dán QR code vào góc phải dưới của ảnh PNG.
    """
    qr_path = os.path.join(os.path.dirname(__file__), "assets", "chatiip.png")

    if not os.path.exists(qr_path):
        return png_bytes

    try:
        base_img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        qr = Image.open(qr_path).convert("RGBA")
    except Exception:
        return png_bytes

    new_w = max(1, int(base_img.size[0] * scale))
    ratio = new_w / qr.size[0]
    new_h = max(1, int(qr.size[1] * ratio))
    qr = qr.resize((new_w, new_h), Image.LANCZOS)

    if alpha < 1.0:
        r, g, b, a = qr.split()
        a = a.point(lambda p: int(p * alpha))
        qr = Image.merge("RGBA", (r, g, b, a))

    x = base_img.size[0] - new_w - padding
    y = base_img.size[1] - new_h - padding

    base_img.paste(qr, (x, y), qr)

    out = io.BytesIO()
    base_img.convert("RGB").save(out, format="PNG")
    return out.getvalue()


# =========================
# 3️⃣ Footer (giờ Việt Nam)
# =========================
def _add_footer(fig):
    tz_vn = pytz.timezone("Asia/Ho_Chi_Minh")
    now = datetime.now(tz_vn)

    footer_text = (
        f"Biểu đồ được tạo bởi ChatIIP.com lúc "
        f"{now.hour:02d} giờ {now.minute:02d} phút "
        f"ngày {now.day:02d} tháng {now.month:02d} năm {now.year}, "
        f"dữ liệu lấy từ IIPMap.com"
    )

    fig.text(
        0.5,
        0.03,
        footer_text,
        ha="center",
        va="center",
        fontsize=15,
        color="black"
    )


# =========================
# 4️⃣ Vẽ biểu đồ so sánh giá thuê đất (base64)
# =========================
def plot_price_bar_chart_base64(df, province: str, industrial_type: str) -> str:
    df = df.copy()

    df["Tên rút gọn"] = df["Tên"].apply(lambda x: _clean_name(x, province))

    df = df.dropna(subset=["Giá số"])
    df["Giá số"] = df["Giá số"].astype(float)

    df = df.sort_values(by="Giá số", ascending=True)

    names = df["Tên rút gọn"].tolist()
    prices = df["Giá số"].tolist()

    fig, ax = plt.subplots(figsize=(20, 7))
    bars = ax.bar(range(len(names)), prices, width=0.6)

    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=90, ha="center")

    ax.set_ylabel("USD / m² / chu kì thuê")
    ax.set_title(
        f"BIỂU ĐỒ SO SÁNH GIÁ THUÊ ĐẤT {industrial_type.upper()} TỈNH {province.upper()}",
        fontsize=16,
        fontweight="bold",
        pad=15
    )

    max_price = max(prices) if prices else 0
    ax.set_ylim(0, max_price * 1.15 if max_price > 0 else 1)

    for bar in bars:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            height,
            f"{int(height)}",
            ha="center",
            va="bottom",
            fontsize=9
        )

    # ✅ NEW: số thứ tự bọc tròn dưới tên
    _add_circled_index_under_ticks(ax, len(names), y_offset=-0.16, fontsize=10)

    # ✅ Chừa chỗ nhiều hơn vì có thêm vòng tròn
    fig.subplots_adjust(bottom=0.60)

    _add_footer(fig)

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)

    png_bytes = buffer.getvalue()
    png_bytes = _overlay_logo_on_png_bytes(png_bytes, alpha=0.9, scale=0.08, padding=20)
    png_bytes = _overlay_qr_on_png_bytes(png_bytes, alpha=1.0, scale=0.08, padding=20)

    return base64.b64encode(png_bytes).decode("utf-8")


# =========================
# 5️⃣ Vẽ biểu đồ so sánh tổng diện tích (base64)
# =========================
def plot_area_bar_chart_base64(df, province: str, industrial_type: str) -> str:
    df = df.copy()

    df["Tên rút gọn"] = df["Tên"].apply(lambda x: _clean_name(x, province))

    df = df.dropna(subset=["Tổng diện tích"])
    df["Tổng diện tích"] = df["Tổng diện tích"].astype(float)

    df = df.sort_values(by="Tổng diện tích", ascending=True)

    names = df["Tên rút gọn"].tolist()
    areas = df["Tổng diện tích"].tolist()

    fig, ax = plt.subplots(figsize=(20, 7))
    bars = ax.bar(range(len(names)), areas, width=0.6, color="green")

    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=90, ha="center")

    ax.set_ylabel("Diện tích (ha)")
    ax.set_title(
        f"BIỂU ĐỒ SO SÁNH TỔNG DIỆN TÍCH {industrial_type.upper()} TỈNH {province.upper()}",
        fontsize=16,
        fontweight="bold",
        pad=15
    )

    max_area = max(areas) if areas else 0
    ax.set_ylim(0, max_area * 1.15 if max_area > 0 else 1)

    for bar in bars:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            height,
            f"{int(height)}",
            ha="center",
            va="bottom",
            fontsize=9
        )

    # ✅ NEW: số thứ tự bọc tròn dưới tên
    _add_circled_index_under_ticks(ax, len(names), y_offset=-0.16, fontsize=10)

    fig.subplots_adjust(bottom=0.60)

    _add_footer(fig)

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)

    png_bytes = buffer.getvalue()
    png_bytes = _overlay_logo_on_png_bytes(png_bytes, alpha=0.9, scale=0.08, padding=20)
    png_bytes = _overlay_qr_on_png_bytes(png_bytes, alpha=1.0, scale=0.08, padding=20)

    return base64.b64encode(png_bytes).decode("utf-8")


# =========================
# 6️⃣ Vẽ 2 biểu đồ giá (2 tỉnh) xếp dọc (base64)
# =========================
def plot_price_bar_chart_two_provinces_base64(
    df1,
    province1: str,
    df2,
    province2: str,
    industrial_type: str
) -> str:
    df1 = df1.copy()
    df2 = df2.copy()

    df1["Tên rút gọn"] = df1["Tên"].apply(lambda x: _clean_name(x, province1))
    df2["Tên rút gọn"] = df2["Tên"].apply(lambda x: _clean_name(x, province2))

    df1 = df1.dropna(subset=["Giá số"])
    df2 = df2.dropna(subset=["Giá số"])
    df1["Giá số"] = df1["Giá số"].astype(float)
    df2["Giá số"] = df2["Giá số"].astype(float)

    df1 = df1.sort_values(by="Giá số", ascending=True)
    df2 = df2.sort_values(by="Giá số", ascending=True)

    names1, prices1 = df1["Tên rút gọn"].tolist(), df1["Giá số"].tolist()
    names2, prices2 = df2["Tên rút gọn"].tolist(), df2["Giá số"].tolist()

    fig, axes = plt.subplots(nrows=2, ncols=1, figsize=(22, 14))
    ax1, ax2 = axes

    bars1 = ax1.bar(range(len(names1)), prices1, width=0.6)
    ax1.set_xticks(range(len(names1)))
    ax1.set_xticklabels(names1, rotation=90, ha="center")
    ax1.set_ylabel("USD / m² / năm")
    ax1.set_title(f"{industrial_type.upper()} - {province1.upper()}",
                  fontsize=14, fontweight="bold", pad=10)

    bars2 = ax2.bar(range(len(names2)), prices2, width=0.6)
    ax2.set_xticks(range(len(names2)))
    ax2.set_xticklabels(names2, rotation=90, ha="center")
    ax2.set_ylabel("USD / m² / chu kì thuê")
    ax2.set_title(f"{industrial_type.upper()} - {province2.upper()}",
                  fontsize=14, fontweight="bold", pad=10)

    max_all = max((max(prices1) if prices1 else 0), (max(prices2) if prices2 else 0))
    ax1.set_ylim(0, max_all * 1.15 if max_all > 0 else 1)
    ax2.set_ylim(0, max_all * 1.15 if max_all > 0 else 1)

    for b in bars1:
        h = b.get_height()
        ax1.text(b.get_x() + b.get_width() / 2, h, f"{int(h)}", ha="center", va="bottom", fontsize=9)

    for b in bars2:
        h = b.get_height()
        ax2.text(b.get_x() + b.get_width() / 2, h, f"{int(h)}", ha="center", va="bottom", fontsize=9)

    # ✅ NEW: số thứ tự bọc tròn dưới tên (mỗi subplot)
    _add_circled_index_under_ticks(ax1, len(names1), y_offset=-0.16, fontsize=10)
    _add_circled_index_under_ticks(ax2, len(names2), y_offset=-0.16, fontsize=10)

    fig.suptitle(
        f"BIỂU ĐỒ SO SÁNH GIÁ THUÊ ĐẤT {industrial_type.upper()} GIỮA 2 TỈNH",
        fontsize=16,
        fontweight="bold",
        y=0.98
    )

    # ✅ chừa chỗ nhiều hơn vì có thêm vòng tròn
    fig.subplots_adjust(hspace=0.70, bottom=0.24, top=0.92)

    _add_footer(fig)

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)

    png_bytes = buffer.getvalue()
    png_bytes = _overlay_logo_on_png_bytes(png_bytes, alpha=0.9, scale=0.08, padding=20)
    png_bytes = _overlay_qr_on_png_bytes(png_bytes, alpha=1.0, scale=0.08, padding=20)

    return base64.b64encode(png_bytes).decode("utf-8")


# =========================
# 7️⃣ Vẽ 2 biểu đồ diện tích (2 tỉnh) xếp dọc (base64)
# =========================
def plot_area_bar_chart_two_provinces_base64(
    df1,
    province1: str,
    df2,
    province2: str,
    industrial_type: str
) -> str:
    df1 = df1.copy()
    df2 = df2.copy()

    df1["Tên rút gọn"] = df1["Tên"].apply(lambda x: _clean_name(x, province1))
    df2["Tên rút gọn"] = df2["Tên"].apply(lambda x: _clean_name(x, province2))

    df1 = df1.dropna(subset=["Tổng diện tích"])
    df2 = df2.dropna(subset=["Tổng diện tích"])
    df1["Tổng diện tích"] = df1["Tổng diện tích"].astype(float)
    df2["Tổng diện tích"] = df2["Tổng diện tích"].astype(float)

    df1 = df1.sort_values(by="Tổng diện tích", ascending=True)
    df2 = df2.sort_values(by="Tổng diện tích", ascending=True)

    names1, areas1 = df1["Tên rút gọn"].tolist(), df1["Tổng diện tích"].tolist()
    names2, areas2 = df2["Tên rút gọn"].tolist(), df2["Tổng diện tích"].tolist()

    fig, axes = plt.subplots(nrows=2, ncols=1, figsize=(22, 14))
    ax1, ax2 = axes

    bars1 = ax1.bar(range(len(names1)), areas1, width=0.6, color="green")
    ax1.set_xticks(range(len(names1)))
    ax1.set_xticklabels(names1, rotation=90, ha="center")
    ax1.set_ylabel("Diện tích (ha)")
    ax1.set_title(f"{industrial_type.upper()} - {province1.upper()}",
                  fontsize=14, fontweight="bold", pad=10)

    bars2 = ax2.bar(range(len(names2)), areas2, width=0.6, color="green")
    ax2.set_xticks(range(len(names2)))
    ax2.set_xticklabels(names2, rotation=90, ha="center")
    ax2.set_ylabel("Diện tích (ha)")
    ax2.set_title(f"{industrial_type.upper()} - {province2.upper()}",
                  fontsize=14, fontweight="bold", pad=10)

    max_all = max((max(areas1) if areas1 else 0), (max(areas2) if areas2 else 0))
    ax1.set_ylim(0, max_all * 1.15 if max_all > 0 else 1)
    ax2.set_ylim(0, max_all * 1.15 if max_all > 0 else 1)

    for b in bars1:
        h = b.get_height()
        ax1.text(b.get_x() + b.get_width() / 2, h, f"{int(h)}", ha="center", va="bottom", fontsize=9)

    for b in bars2:
        h = b.get_height()
        ax2.text(b.get_x() + b.get_width() / 2, h, f"{int(h)}", ha="center", va="bottom", fontsize=9)

    # ✅ NEW: số thứ tự bọc tròn dưới tên (mỗi subplot)
    _add_circled_index_under_ticks(ax1, len(names1), y_offset=-0.16, fontsize=10)
    _add_circled_index_under_ticks(ax2, len(names2), y_offset=-0.16, fontsize=10)

    fig.suptitle(
        f"BIỂU ĐỒ SO SÁNH DIỆN TÍCH {industrial_type.upper()} GIỮA 2 TỈNH",
        fontsize=16,
        fontweight="bold",
        y=0.98
    )

    fig.subplots_adjust(hspace=0.70, bottom=0.24, top=0.92)

    _add_footer(fig)

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)

    png_bytes = buffer.getvalue()
    png_bytes = _overlay_logo_on_png_bytes(png_bytes, alpha=0.9, scale=0.08, padding=20)
    png_bytes = _overlay_qr_on_png_bytes(png_bytes, alpha=1.0, scale=0.08, padding=20)

    return base64.b64encode(png_bytes).decode("utf-8")
