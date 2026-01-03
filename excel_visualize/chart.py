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
    n = name.lower()
    for kw in [
        "khu công nghiệp",
        "cụm công nghiệp",
        province.lower()
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


def _add_logo_to_figure(fig, alpha=0.85, scale=0.12):
    """
    Thêm logo công ty vào góc phải trên của figure
    """
    logo_path = os.path.join(
        os.path.dirname(__file__),
        "assets",
        "company_logo.png"
    )

    if not os.path.exists(logo_path):
        return  # không có logo thì bỏ qua

    logo = Image.open(logo_path)

    # Resize logo theo tỉ lệ figure
    fig_w, fig_h = fig.get_size_inches() * fig.dpi
    new_width = int(fig_w * scale)
    ratio = new_width / logo.size[0]
    new_height = int(logo.size[1] * ratio)
    logo = logo.resize((new_width, new_height), Image.LANCZOS)

    fig.figimage(
        logo,
        xo=int(fig_w - new_width - 20),
        yo=int(fig_h - new_height - 20),
        alpha=alpha,
        zorder=10
    )
# =========================
# 3️⃣ Vẽ biểu đồ so sánh giá đất theo khu / cụm
# =========================
def plot_price_bar_chart_base64(
    df,
    province: str,
    industrial_type: str
) -> str:

    df = df.copy()

    # Chuẩn hóa tên
    df["Tên rút gọn"] = df["Tên"].apply(
        lambda x: _clean_name(x, province)
    )

    # Chuẩn hóa giá
    df["Giá số"] = df["Giá thuê đất"].apply(_parse_price)
    df = df.dropna(subset=["Giá số"])

    # Sort tăng dần
    df = df.sort_values(by="Giá số", ascending=True)

    names = df["Tên rút gọn"].tolist()
    prices = df["Giá số"].tolist()

    # =========================
    # Vẽ biểu đồ
    # =========================
    fig = plt.figure(figsize=(20, 7))
  # kéo dài biểu đồ

    bars = plt.bar(
        range(len(names)),
        prices,
        width=0.6
    )

    # Trục X: chữ để dọc
    plt.xticks(
        range(len(names)),
        names,
        rotation=90,
        ha="center"
    )

    plt.xlabel("Khu / Cụm công nghiệp")
    plt.ylabel("USD / m² / năm")

    plt.title(
        f"So sánh giá thuê đất {industrial_type} – {province}"
    )

    # Trục Y: bắt đầu từ 0
    max_price = max(prices)
    plt.ylim(0, max_price * 1.15)

    # =========================
    # Hiển thị giá trên đầu cột
    # =========================
    for bar in bars:
        height = bar.get_height()
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            height,
            f"{int(height)}",
            ha="center",
            va="bottom",
            fontsize=9
        )

    # Tránh đè chữ
    plt.subplots_adjust(bottom=0.35)

    # ===== THÊM LOGO =====
    _add_logo_to_figure(fig)

    buffer = io.BytesIO()
    plt.savefig(buffer, format="png", dpi=150)
    plt.close()

    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")

# =========================
# Vẽ biểu đồ so sánh tổng diện tích
# =========================

def plot_area_bar_chart_base64(
    df,
    province: str,
    industrial_type: str
) -> str:

    df = df.copy()

    df["Tên rút gọn"] = df["Tên"].apply(
        lambda x: _clean_name(x, province)
    )

    # Chuẩn hóa diện tích (giả sử đã là số)
    df = df.dropna(subset=["Tổng diện tích"])
    df = df.sort_values(by="Tổng diện tích", ascending=True)

    names = df["Tên rút gọn"].tolist()
    areas = df["Tổng diện tích"].astype(float).tolist()

    plt.figure(figsize=(20, 7))

    bars = plt.bar(
        range(len(names)),
        areas,
        width=0.6,
        color="green"   # 👈 màu xanh lá
    )

    plt.xticks(
        range(len(names)),
        names,
        rotation=90,
        ha="center"
    )

    plt.xlabel("Khu / Cụm công nghiệp")
    plt.ylabel("Diện tích (ha)")

    plt.title(
        f"So sánh tổng diện tích {industrial_type} – {province}"
    )

    # Trục Y bắt đầu từ 0
    max_area = max(areas)
    plt.ylim(0, max_area * 1.15)

    # Hiển thị diện tích trên đầu cột
    for bar in bars:
        height = bar.get_height()
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            height,
            f"{int(height)}",
            ha="center",
            va="bottom",
            fontsize=9
        )

    plt.subplots_adjust(bottom=0.35)

    buffer = io.BytesIO()
    plt.savefig(buffer, format="png", dpi=150)
    plt.close()

    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")
