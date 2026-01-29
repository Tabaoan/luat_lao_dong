import pandas as pd
import json
import re
import io
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

# Fallback cho rapidfuzz
try:
    from rapidfuzz import fuzz, process
except ImportError:
    fuzz = None
    process = None

class IIPMapBackend:
    def __init__(self, excel_path: str, geojson_path: str = None):
        try:
            self.df = pd.read_excel(excel_path)
            self.df.columns = self.df.columns.str.strip()
        except Exception as e:
            print(f"❌ Lỗi load Excel: {e}")
            self.df = pd.DataFrame()
            
        self.geojson_map = {}
        
        # Mapping cột chuẩn (giữ nguyên để đảm bảo core function không lỗi)
        self.cols = {
            "province": "Tỉnh/Thành phố", 
            "type": "Loại", 
            "name": "Tên",
            "address": "Địa chỉ", 
            "price": "Giá thuê đất", 
            "area": "Tổng diện tích",
            "industry": "Ngành nghề",
        }
        
        # Load GeoJSON
        if geojson_path and Path(geojson_path).exists():
            try:
                with open(geojson_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for feat in data.get('features', []):
                    props = feat.get('properties', {})
                    geom = feat.get('geometry', {})
                    if props.get('name') and geom.get('coordinates'):
                        norm_name = self._normalize(props['name'])
                        self.geojson_map[norm_name] = geom['coordinates']
            except Exception as e:
                print(f"⚠️ GeoJSON Error: {e}")

        # Pre-process số liệu
        if not self.df.empty:
            self._map_columns_dynamic()
            self.df['price_num'] = self.df[self.cols['price']].apply(self._parse_price)
            self.df['area_num'] = self.df[self.cols['area']].apply(self._parse_area)
            self.df['name_norm'] = self.df[self.cols['name']].astype(str).apply(self._normalize)
            self.df['type_norm'] = self.df[self.cols['type']].astype(str).apply(self._normalize)
            self.df['prov_norm'] = self.df[self.cols['province']].astype(str).apply(self._normalize)

    def _map_columns_dynamic(self):
        """Tìm tên cột gần đúng trong file Excel nếu tên cứng không khớp"""
        for key, val in self.cols.items():
            if val not in self.df.columns:
                for real_col in self.df.columns:
                    if val.lower() in real_col.lower():
                        self.cols[key] = real_col
                        break

    def get_all_columns(self):
        if self.df.empty: return []
        return self.df.columns.tolist()

    def _normalize(self, text):
        return str(text).lower().strip()

    def _extract_number(self, s):
        """Hàm tách số mạnh mẽ từ chuỗi lộn xộn (VD: '&nbsp;60%')"""
        # Thay thế các ký tự lạ thường gặp trong web scraping
        s = s.replace("&nbsp;", "").replace("%", "").replace(",", ".")
        match = re.search(r'(\d+\.?\d*)', s)
        return float(match.group(1)) if match else None

    def _parse_price(self, val):
        if pd.isna(val): return None
        s = str(val).lower().replace("usd", "").replace("/m2/năm", "").replace("/m²/năm", "")
        if "-" in s:
            try:
                parts = s.split("-")
                return (self._extract_number(parts[0]) + self._extract_number(parts[1])) / 2
            except: pass
        return self._extract_number(s)

    def _parse_area(self, val):
        if pd.isna(val): return None
        s = str(val).lower().replace("ha", "").replace("hecta", "")
        return self._extract_number(s)

    def _parse_general_number(self, val):
        """Dùng cho các cột động (Mật độ, Tầng cao...)"""
        if pd.isna(val): return 0
        s = str(val).lower()
        return self._extract_number(s) or 0

    def match_coordinates(self, name: str):
        norm = self._normalize(name)
        if norm in self.geojson_map: return self.geojson_map[norm]
        if process and self.geojson_map:
            match = process.extractOne(norm, list(self.geojson_map.keys()), scorer=fuzz.WRatio)
            if match and match[1] > 85: return self.geojson_map[match[0]]
        return None

    def query_flexible(self, filters: dict):
        df_res = self.df.copy()
        
        # 1. LỌC LOẠI (KCN/CCN)
        zone_type = filters.get("zone_type", "ALL")
        if zone_type != "ALL":
            if zone_type == "KCN":
                df_res = df_res[df_res['type_norm'].str.contains("khu|kcn|ip|iz", regex=True, na=False)]
            elif zone_type == "CCN":
                df_res = df_res[df_res['type_norm'].str.contains("cụm|ccn|cluster", regex=True, na=False)]

        # 2. LỌC SỐ HỌC (Numeric Filters)
        numeric_filters = filters.get("numeric_filters", [])
        for nf in numeric_filters:
            metric = nf.get("col")
            op = nf.get("op")
            val = float(nf.get("val", 0))

            target_col = None
            if metric == "price": target_col = 'price_num'
            elif metric == "area": target_col = 'area_num'
            
            if target_col:
                if op == "<": df_res = df_res[df_res[target_col] < val]
                elif op == ">": df_res = df_res[df_res[target_col] > val]
                elif op == "<=": df_res = df_res[df_res[target_col] <= val]
                elif op == ">=": df_res = df_res[df_res[target_col] >= val]

        # 3. LỌC CÁC CỘT KHÁC (Dynamic Text)
        for col, val in filters.items():
            if col in ["zone_type", "numeric_filters"]: continue
            
            target_col = None
            if col in self.df.columns:
                target_col = col
            else:
                for real_col in self.df.columns:
                    if col.lower() == real_col.lower():
                        target_col = real_col
                        break
            
            if target_col:
                if target_col == self.cols['province']:
                    df_res = df_res[df_res['prov_norm'].str.contains(self._normalize(val), na=False)]
                elif target_col == self.cols['name']:
                    df_res = df_res[df_res['name_norm'].str.contains(self._normalize(val), na=False)]
                else:
                    df_res = df_res[df_res[target_col].astype(str).str.contains(str(val), case=False, na=False)]

        return df_res

    def generate_chart_base64(self, df: pd.DataFrame, title: str, metric_col: str = "dual"):
        if df.empty: return None
        df_plot = df.copy()
        
        # --- Logic Vẽ Biểu Đồ ---
        if metric_col == 'dual':
            df_plot = df_plot.sort_values(['price_num', 'area_num'], ascending=False).head(10)
        elif metric_col == 'area':
            df_plot = df_plot.sort_values('area_num', ascending=False).head(10)
        elif metric_col == 'price':
            df_plot = df_plot.sort_values('price_num', ascending=False).head(10)
        else:
            # --- VẼ BIỂU ĐỒ CỘT ĐỘNG (Bất kỳ cột nào) ---
            real_col = None
            for c in df.columns:
                if metric_col.lower() == c.lower():
                    real_col = c
                    break
            
            if real_col:
                # Tự động parse số từ cột đó (VD: "60%" -> 60)
                temp_col = f"_temp_{real_col}"
                df_plot[temp_col] = df_plot[real_col].apply(self._parse_general_number)
                df_plot = df_plot.sort_values(temp_col, ascending=False).head(10)
            else:
                return None

        df_plot = df_plot.iloc[::-1] # Đảo ngược để vẽ
        names = df_plot[self.cols['name']].tolist()
        
        plt.figure(figsize=(10, 6))
        
        if metric_col == 'dual':
            prices = df_plot['price_num'].fillna(0).tolist()
            plt.barh(names, prices, color='#1f77b4')
            plt.xlabel("Giá thuê (USD/m²/năm)")
        elif metric_col == 'area':
            vals = df_plot['area_num'].fillna(0).tolist()
            plt.barh(names, vals, color='#2ca02c')
            plt.xlabel("Diện tích (ha)")
        elif metric_col == 'price':
            vals = df_plot['price_num'].fillna(0).tolist()
            plt.barh(names, vals, color='#1f77b4')
            plt.xlabel("Giá thuê (USD/m²/năm)")
        else:
            # Vẽ cột động
            vals = df_plot[f"_temp_{real_col}"].fillna(0).tolist()
            plt.barh(names, vals, color='#ff7f0e') # Màu cam
            plt.xlabel(f"{real_col} (Số liệu)")

        plt.title(title, fontsize=12, fontweight='bold')
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()
        return b64