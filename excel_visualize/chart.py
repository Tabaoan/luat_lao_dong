import matplotlib.pyplot as plt
import io
import base64
import os
from PIL import Image
from datetime import datetime
import pytz
import numpy as np
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401


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

    - alpha: độ trong suốt logo (0-1)
    - scale: logo chiếm bao nhiêu % chiều rộng ảnh (vd 0.08 = 8%)
    - padding: khoảng cách tới mép (px)
    """
    logo_path = os.path.join(os.path.dirname(__file__), "assets", "company_logos.png")

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
        0.5,          # căn giữa
        0.03,         # sát đáy
        footer_text,
        ha="center",
        va="center",
        fontsize=15,
        color="black"
    )


# =========================
# 4️⃣ Vẽ biểu đồ 3D so sánh giá thuê đất (base64)
# =========================
def plot_price_bar_chart_base64(df, province: str, industrial_type: str) -> str:
    df = df.copy()

    # Chuẩn hóa tên
    df["Tên rút gọn"] = df["Tên"].apply(lambda x: _clean_name(x, province))

    # ✅ Đồng bộ: data_adapter đã tạo sẵn "Giá số"
    df = df.dropna(subset=["Giá số"])
    df["Giá số"] = df["Giá số"].astype(float)

    # Sort tăng dần
    df = df.sort_values(by="Giá số", ascending=True)

    names = df["Tên rút gọn"].tolist()
    prices = df["Giá số"].tolist()

    fig = plt.figure(figsize=(20, 7))
    ax = fig.add_subplot(111, projection="3d")

    n = len(names)
    xs = np.arange(n)
    ys = np.zeros(n)
    zs = np.zeros(n)

    dx = np.full(n, 0.6)  # độ rộng theo X
    dy = np.full(n, 0.6)  # độ dày theo Y
    dz = np.array(prices, dtype=float)

    # Vẽ cột 3D
    ax.bar3d(xs, ys, zs, dx, dy, dz, shade=True)

    # Nhãn trục X
    if n > 0:
        ax.set_xticks(xs + dx[0] / 2)
        ax.set_xticklabels(names, rotation=90, ha="center")
    else:
        ax.set_xticks([])

    # Ẩn trục Y cho đỡ rối
    ax.set_yticks([])
    ax.set_ylabel("")

    ax.set_zlabel("USD / m² / năm")

    ax.set_title(
        f"BIỂU ĐỒ SO SÁNH GIÁ THUÊ ĐẤT {industrial_type.upper()} TỈNH {province.upper()}",
        fontsize=16,
        fontweight="bold",
        pad=15
    )

    # Góc nhìn 3D (chỉnh theo ý bạn)
    ax.view_init(elev=20, azim=-60)

    # Trục Z bắt đầu từ 0
    max_price = float(np.max(dz)) if n > 0 else 0
    ax.set_zlim(0, max_price * 1.15 if max_price > 0 else 1)

    # Chừa chỗ cho nhãn + footer
    fig.subplots_adjust(bottom=0.50)

    # Footer (giờ VN)
    _add_footer(fig)

    # Render ra PNG bytes
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)

    png_bytes = buffer.getvalue()

    # Dán logo lên PNG
    png_bytes = _overlay_logo_on_png_bytes(
        png_bytes,
        alpha=0.9,
        scale=0.08,
        padding=20
    )

    return base64.b64encode(png_bytes).decode("utf-8")


# =========================
# 5️⃣ Vẽ biểu đồ 3D so sánh tổng diện tích (base64)
# =========================
def plot_area_bar_chart_base64(df, province: str, industrial_type: str) -> str:
    df = df.copy()

    df["Tên rút gọn"] = df["Tên"].apply(lambda x: _clean_name(x, province))

    # Chuẩn hóa diện tích (data_adapter đã parse float)
    df = df.dropna(subset=["Tổng diện tích"])
    df["Tổng diện tích"] = df["Tổng diện tích"].astype(float)

    df = df.sort_values(by="Tổng diện tích", ascending=True)

    names = df["Tên rút gọn"].tolist()
    areas = df["Tổng diện tích"].tolist()

    fig = plt.figure(figsize=(20, 7))
    ax = fig.add_subplot(111, projection="3d")

    n = len(names)
    xs = np.arange(n)
    ys = np.zeros(n)
    zs = np.zeros(n)

    dx = np.full(n, 0.6)
    dy = np.full(n, 0.6)
    dz = np.array(areas, dtype=float)

    ax.bar3d(xs, ys, zs, dx, dy, dz, shade=True)

    if n > 0:
        ax.set_xticks(xs + dx[0] / 2)
        ax.set_xticklabels(names, rotation=90, ha="center")
    else:
        ax.set_xticks([])

    ax.set_yticks([])
    ax.set_ylabel("")

    ax.set_zlabel("Diện tích (ha)")

    ax.set_title(
        f"BIỂU ĐỒ SO SÁNH TỔNG DIỆN TÍCH {industrial_type.upper()} TỈNH {province.upper()}",
        fontsize=16,
        fontweight="bold",
        pad=15
    )

    ax.view_init(elev=20, azim=-60)

    max_area = float(np.max(dz)) if n > 0 else 0
    ax.set_zlim(0, max_area * 1.15 if max_area > 0 else 1)

    fig.subplots_adjust(bottom=0.50)

    _add_footer(fig)

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)

    png_bytes = buffer.getvalue()

    png_bytes = _overlay_logo_on_png_bytes(
        png_bytes,
        alpha=0.9,
        scale=0.08,
        padding=20
    )

    return base64.b64encode(png_bytes).decode("utf-8")
