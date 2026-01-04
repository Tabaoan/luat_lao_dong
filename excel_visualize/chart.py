import matplotlib.pyplot as plt
import io
import base64
from typing import Optional
import os
from PIL import Image


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
# 2️⃣ Parse giá về số
# =========================
def _parse_price(value) -> Optional[float]:
    """
    - '120 USD/m²/năm' -> 120
    - '85-95 USD/m²/năm' -> 90
    """
    if value is None:
        return None

    s = str(value).lower()
    for kw in ["usd/m²/năm", "usd/m2/năm", "usd"]:
        s = s.replace(kw, "")
    s = s.strip()

    # Trường hợp khoảng giá
    if "-" in s:
        try:
            a, b = s.split("-")
            return (float(a.strip()) + float(b.strip())) / 2
        except Exception:
            return None

    try:
        return float(s)
    except Exception:
        return None


# =========================
# 3️⃣ Dán logo vào ảnh PNG (ăn chắc)
# =========================
def _overlay_logo_on_png_bytes(
    png_bytes: bytes,
    alpha: float = 0.9,
    scale: float = 0.12,
    padding: int = 20
) -> bytes:
    """
    Dán logo vào góc phải trên của ảnh PNG đã render từ matplotlib.

    - alpha: độ trong suốt logo (0-1)
    - scale: logo chiếm bao nhiêu % chiều rộng ảnh (vd 0.12 = 12%)
    - padding: khoảng cách tới mép (px)
    """
    logo_path = os.path.join(os.path.dirname(__file__), "assets", "company_logos.png")

    # Debug nhanh nếu cần:
    # print("[LOGO PATH]", logo_path)
    # print("[LOGO EXISTS]", os.path.exists(logo_path))

    if not os.path.exists(logo_path):
        return png_bytes

    try:
        base_img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        logo = Image.open(logo_path).convert("RGBA")
    except Exception:
        return png_bytes

    # Resize logo theo chiều rộng ảnh
    new_w = max(1, int(base_img.size[0] * scale))
    ratio = new_w / logo.size[0]
    new_h = max(1, int(logo.size[1] * ratio))
    logo = logo.resize((new_w, new_h), Image.LANCZOS)

    # Apply alpha (giảm độ đậm của logo)
    if alpha < 1.0:
        r, g, b, a = logo.split()
        a = a.point(lambda p: int(p * alpha))
        logo = Image.merge("RGBA", (r, g, b, a))

    # Vị trí góc phải trên
    x = base_img.size[0] - new_w - padding
    y = padding

    # Paste logo (dùng chính alpha channel của logo)
    base_img.paste(logo, (x, y), logo)

    # Xuất lại PNG bytes
    out = io.BytesIO()
    base_img.convert("RGB").save(out, format="PNG")
    return out.getvalue()


# =========================
# 4️⃣ Vẽ biểu đồ so sánh giá thuê đất (base64)
# =========================
def plot_price_bar_chart_base64(df, province: str, industrial_type: str) -> str:
    df = df.copy()

    # Chuẩn hóa tên
    df["Tên rút gọn"] = df["Tên"].apply(lambda x: _clean_name(x, province))

    # Chuẩn hóa giá
    df["Giá số"] = df["Giá thuê đất"].apply(_parse_price)
    df = df.dropna(subset=["Giá số"])

    # Sort tăng dần
    df = df.sort_values(by="Giá số", ascending=True)

    names = df["Tên rút gọn"].tolist()
    prices = df["Giá số"].tolist()

    fig, ax = plt.subplots(figsize=(20, 7))

    bars = ax.bar(range(len(names)), prices, width=0.6)

    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=90, ha="center")

    ax.set_xlabel("Khu / Cụm công nghiệp")
    ax.set_ylabel("USD / m² / năm")
    ax.set_title(f"So sánh giá thuê đất {industrial_type} – {province}")

    # Trục Y bắt đầu từ 0
    max_price = max(prices) if prices else 0
    ax.set_ylim(0, max_price * 1.15 if max_price > 0 else 1)

    # Hiển thị giá trên đầu cột
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

    # Tránh đè chữ
    fig.subplots_adjust(bottom=0.35)

    # Render ra PNG bytes
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)

    png_bytes = buffer.getvalue()

    # Dán logo lên PNG (ăn chắc)
    png_bytes = _overlay_logo_on_png_bytes(
        png_bytes,
        alpha=0.9,
        scale=0.08,
        padding=20
    )

    return base64.b64encode(png_bytes).decode("utf-8")


# =========================
# 5️⃣ Vẽ biểu đồ so sánh tổng diện tích (base64)
# =========================
def plot_area_bar_chart_base64(df, province: str, industrial_type: str) -> str:
    df = df.copy()

    df["Tên rút gọn"] = df["Tên"].apply(lambda x: _clean_name(x, province))

    # Chuẩn hóa diện tích
    df = df.dropna(subset=["Tổng diện tích"])
    df = df.sort_values(by="Tổng diện tích", ascending=True)

    names = df["Tên rút gọn"].tolist()
    areas = df["Tổng diện tích"].astype(float).tolist()

    fig, ax = plt.subplots(figsize=(20, 7))

    bars = ax.bar(
        range(len(names)),
        areas,
        width=0.6,
        color="green"
    )

    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=90, ha="center")

    ax.set_xlabel("Khu / Cụm công nghiệp")
    ax.set_ylabel("Diện tích (ha)")
    ax.set_title(f"So sánh tổng diện tích {industrial_type} – {province}")

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

    fig.subplots_adjust(bottom=0.35)

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)

    png_bytes = buffer.getvalue()

    # Dán logo lên PNG (ăn chắc)
    png_bytes = _overlay_logo_on_png_bytes(
        png_bytes,
        alpha=0.9,
        scale=0.12,
        padding=20
    )

    return base64.b64encode(png_bytes).decode("utf-8")
