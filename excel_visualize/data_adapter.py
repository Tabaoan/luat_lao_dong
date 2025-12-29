def extract_price_data_by_province(excel_handler, province: str):
    df = excel_handler.df

    df_filtered = df[
        df["Tỉnh/Thành phố"].str.lower() == province.lower()
    ][["Tên", "Giá thuê đất"]].dropna()

    return df_filtered

def extract_price_data(
    excel_handler,
    province: str,
    industrial_type: str
):
    df = excel_handler.df.copy()

    # Chuẩn hoá chuỗi
    df["Loại_norm"] = (
        df["Loại"]
        .astype(str)
        .str.lower()
        .str.strip()
    )

    # Mapping logic
    if industrial_type == "Cụm công nghiệp":
        type_mask = df["Loại_norm"].str.contains(
            r"cụm|ccn", regex=True
        )
    elif industrial_type == "Khu công nghiệp":
        type_mask = df["Loại_norm"].str.contains(
            r"khu|kcn", regex=True
        )
    else:
        return df.iloc[0:0]

    df_filtered = df[
        (df["Tỉnh/Thành phố"].str.lower().str.strip() == province.lower()) &
        type_mask
    ][["Tên", "Giá thuê đất"]].dropna()

    return df_filtered