import matplotlib.pyplot as plt
import io
import base64

def plot_price_bar_chart_base64(
    df,
    province: str,
    industrial_type: str
) -> str:

    plt.figure(figsize=(10, 5))
    plt.bar(df["Tên"], df["Giá thuê đất"])
    plt.xticks(rotation=45, ha="right")
    plt.xlabel(industrial_type)
    plt.ylabel("Giá thuê đất")
    plt.title(f"So sánh giá thuê đất {industrial_type} – {province}")
    plt.tight_layout()

    buffer = io.BytesIO()
    plt.savefig(buffer, format="png", dpi=150)
    plt.close()

    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")
