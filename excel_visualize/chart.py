import matplotlib.pyplot as plt
import io
import base64
import numpy as np


def _clean_name(name: str, province: str) -> str:
    n = name.lower()
    for kw in [
        "khu công nghiệp",
        "cụm công nghiệp",
        province.lower()
    ]:
        n = n.replace(kw, "")
    return n.strip().title()


def plot_price_bar_chart_base64(
    df,
    province: str,
    industrial_type: str
) -> str:

    # =========================
    # 1️⃣ Chuẩn hóa & sort
    # =========================
    df = df.copy()

    df["Tên rút gọn"] = df["Tên"].apply(
        lambda x: _clean_name(x, province)
    )

    df = df.sort_values(by="Giá thuê đất", ascending=True)

    names = df["Tên rút gọn"].tolist()
    prices = df["Giá thuê đất"].tolist()

    min_price = min(prices)
    max_price = max(prices)

    # =========================
    # 2️⃣ Vị trí X – giãn cột
    # =========================
    x = np.arange(len(names)) * 1.3

    plt.figure(figsize=(18, 6))

    bars = plt.bar(
        x,
        prices,
        width=0.6
    )

    # 👇 TÊN KHU / CỤM ĐỂ DỌC
    plt.xticks(
        x,
        names,
        rotation=90,
        ha="center",
        fontsize=9
    )

    plt.xlabel("Khu / Cụm công nghiệp")
    plt.ylabel("USD / m² / năm")

    plt.title(
        f"So sánh giá thuê đất {industrial_type} – {province}"
    )

    # =========================
    # 3️⃣ ÉP TRỤC Y BẮT ĐẦU TỪ 0
    # =========================
    plt.ylim(0, max_price * 1.15)

    yticks = sorted(set([0, min_price] + list(plt.yticks()[0])))
    plt.yticks(yticks)

    # =========================
    # 4️⃣ Hiển thị GIÁ (CHỈ SỐ)
    # =========================
    for bar, price in zip(bars, prices):
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max_price * 0.01,
            f"{int(price)}",
            ha="center",
            va="bottom",
            fontsize=9
        )

    plt.tight_layout()

    # =========================
    # 5️⃣ Xuất base64
    # =========================
    buffer = io.BytesIO()
    plt.savefig(buffer, format="png", dpi=150)
    plt.close()

    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")
