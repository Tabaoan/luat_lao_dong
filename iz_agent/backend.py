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
        
        # Mapping cột chuẩn (tự động tìm nếu không khớp)
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
            
            # Tạo các cột chuẩn hóa cho tìm kiếm - TỰ ĐỘNG NHẬN DIỆN
            # Tìm cột tên
            name_col = None
            for col in self.df.columns:
                if any(keyword in col.lower() for keyword in ['tên', 'name']) and not col.endswith('_num'):
                    name_col = col
                    break
            if name_col:
                self.df['name_norm'] = self.df[name_col].astype(str).apply(self._normalize)
            
            # Tìm cột loại
            type_col = None  
            for col in self.df.columns:
                if any(keyword in col.lower() for keyword in ['loại', 'type', 'kind']):
                    type_col = col
                    break
            if type_col:
                self.df['type_norm'] = self.df[type_col].astype(str).apply(self._normalize)
            
            # Tìm cột tỉnh
            prov_col = None
            for col in self.df.columns:
                if any(keyword in col.lower() for keyword in ['tỉnh', 'thành phố', 'province', 'city']):
                    prov_col = col
                    break
            if prov_col:
                self.df['prov_norm'] = self.df[prov_col].astype(str).apply(self._normalize)
            
            # Tự động tạo các cột số cho tất cả cột có thể chứa số
            self._create_numeric_columns()

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
    
    def _clean_dict_for_json(self, data_dict):
        """Clean dictionary for JSON serialization by handling NaN values"""
        import math
        import pandas as pd
        
        cleaned = {}
        for key, value in data_dict.items():
            # Bỏ qua các cột _num
            if key.endswith('_num'):
                continue
                
            # Xử lý float NaN/Infinity
            if isinstance(value, float):
                if math.isnan(value) or math.isinf(value):
                    cleaned[key] = None
                    continue
            
            # Xử lý pandas NaN
            if pd.isna(value):
                cleaned[key] = None
                continue
                
            # Xử lý string "nan", "inf"
            if isinstance(value, str):
                if value.lower() in ['nan', 'inf', '-inf', 'infinity', '-infinity']:
                    cleaned[key] = None
                    continue
            
            cleaned[key] = value
        return cleaned

    def _extract_number(self, s):
        """Hàm tách số mạnh mẽ từ chuỗi lộn xộn (VD: '&nbsp;60%')"""
        # Thay thế các ký tự lạ thường gặp trong web scraping
        s = s.replace("&nbsp;", "").replace("%", "").replace(",", ".")
        match = re.search(r'(\d+\.?\d*)', s)
        return float(match.group(1)) if match else None

    def _parse_smart(self, val, col_name):
        """Parser đơn giản - tự động nhận diện"""
        if pd.isna(val): return None
        
        s = str(val).lower()
        
        # Giá: có "giá", "price", "usd"
        if any(x in col_name.lower() for x in ['giá', 'price']) or 'usd' in s:
            s = s.replace("usd", "").replace("/m²/năm", "").replace("/m2/năm", "")
            if "-" in s:
                parts = s.split("-")
                try: return (self._extract_number(parts[0]) + self._extract_number(parts[1])) / 2
                except: pass
        
        # Diện tích: có "diện tích", "area", "ha"  
        elif any(x in col_name.lower() for x in ['diện tích', 'area']) or 'ha' in s:
            s = s.replace("ha", "").replace("hecta", "")
        
        # Tất cả: tách số
        return self._extract_number(s) or 0

    def _create_numeric_columns(self):
        """Tạo cột số cho tất cả cột"""
        for col in self.df.columns:
            if col not in ['name_norm', 'type_norm', 'prov_norm']:
                self.df[f"{col}_num"] = self.df[col].apply(lambda x: self._parse_smart(x, col))

    def _get_numeric_column(self, col_name):
        """Tìm cột số - logic thông minh với ưu tiên từ khóa"""
        col_name_lower = col_name.lower()
        
        # 1. Thử trực tiếp với tên cột
        if f"{col_name}_num" in self.df.columns:
            return f"{col_name}_num"
        
        # 2. Ưu tiên tìm cột chính xác với từ khóa đặc biệt
        # Tránh nhầm lẫn giữa "hệ số sử dụng đất" và "diện tích"
        priority_keywords = {
            'lấp đầy': ['lấp đầy', 'occupancy'],
            'sử dụng': ['sử dụng đất', 'sử dụng', 'utilization'],
            'hệ số': ['hệ số', 'tỷ lệ', 'ratio'],
            'diện tích': ['diện tích', 'area'],
            'giá': ['giá', 'price'],
        }
        
        # Tìm nhóm từ khóa phù hợp
        for group_key, keywords in priority_keywords.items():
            if any(kw in col_name_lower for kw in keywords):
                # Tìm cột có chứa từ khóa này
                for real_col in self.df.columns:
                    real_col_lower = real_col.lower()
                    # Kiểm tra cột có chứa từ khóa và có _num
                    if any(kw in real_col_lower for kw in keywords) and f"{real_col}_num" in self.df.columns:
                        # Đảm bảo không nhầm lẫn (vd: "sử dụng đất" không match với "diện tích")
                        if group_key == 'sử dụng' and 'diện tích' in real_col_lower:
                            continue
                        if group_key == 'diện tích' and any(x in real_col_lower for x in ['lấp đầy', 'sử dụng', 'occupancy']):
                            continue
                        return f"{real_col}_num"
        
        # 3. Thử tìm cột tương tự (fuzzy matching - fallback)
        for real_col in self.df.columns:
            if col_name_lower in real_col.lower() and f"{real_col}_num" in self.df.columns:
                return f"{real_col}_num"
        
        # 4. Thử mapping ngược từ tên thân thiện sang tên thật
        for key, real_col_name in self.cols.items():
            if col_name_lower == key.lower() and f"{real_col_name}_num" in self.df.columns:
                return f"{real_col_name}_num"
        
        return None

    def _parse_general_number(self, val):
        """Dùng cho các cột động (Mật độ, Tầng cao...) - DEPRECATED, dùng _parse_smart"""
        if pd.isna(val): return 0
        s = str(val).lower()
        return self._extract_number(s) or 0

    def search_single_zone(self, zone_name: str):
        """Tìm kiếm 1 KCN/CCN cụ thể với logic thông minh"""
        if self.df.empty:
            return {"type": "error", "message": "Không có dữ liệu."}
        
        zone_name_norm = self._normalize(zone_name)
        
        # Tìm cột tên
        name_col = None
        for col in self.df.columns:
            if any(keyword in col.lower() for keyword in ['tên', 'name']) and not col.endswith('_num'):
                name_col = col
                break
        
        if not name_col:
            return {"type": "error", "message": "Không tìm thấy cột tên trong dữ liệu."}
        
        # 1. Tìm exact match (khớp hoàn toàn)
        exact_matches = self.df[self.df['name_norm'] == zone_name_norm]
        if len(exact_matches) == 1:
            return {"type": "single_result", "data": self._clean_dict_for_json(exact_matches.iloc[0].to_dict())}
        
        # 2. Tìm partial match (chứa từ khóa)
        partial_matches = self.df[self.df['name_norm'].str.contains(zone_name_norm, na=False)]
        
        if len(partial_matches) == 0:
            return {"type": "not_found", "message": f"Không tìm thấy KCN/CCN nào có tên chứa '{zone_name}'."}
        
        elif len(partial_matches) == 1:
            return {"type": "single_result", "data": partial_matches.iloc[0].to_dict()}
        
        else:
            # 3. Nhiều kết quả - tạo danh sách lựa chọn
            choices = []
            for idx, row in partial_matches.head(10).iterrows():  # Tối đa 10 lựa chọn
                # Tìm cột tỉnh
                location = "Không rõ"
                for col in self.df.columns:
                    if any(keyword in col.lower() for keyword in ['tỉnh', 'thành phố', 'province']):
                        location = str(row.get(col, "Không rõ"))
                        break
                
                # Tìm cột loại
                zone_type = "Không rõ"
                for col in self.df.columns:
                    if any(keyword in col.lower() for keyword in ['loại', 'type']):
                        zone_type = str(row.get(col, "Không rõ"))
                        break
                
                choices.append({
                    "name": str(row.get(name_col, "")),
                    "location": location,
                    "type": zone_type,
                    "coordinates": self.match_coordinates(str(row.get(name_col, ""))),
                    "full_data": self._clean_dict_for_json(row.to_dict())
                })
            
            return {
                "type": "multiple_choices",
                "message": f"Tìm thấy {len(partial_matches)} KCN/CCN có tên tương tự '{zone_name}'. Bạn đang tìm:",
                "choices": choices,
                "total_found": len(partial_matches)
            }

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

        # 2. LỌC SỐ HỌC (Numeric Filters) - ĐƠN GIẢN
        for nf in filters.get("numeric_filters", []):
            col = nf.get("col")
            op = nf.get("op") 
            val = float(nf.get("val", 0))
            
            numeric_col = self._get_numeric_column(col)
            if numeric_col and numeric_col in self.df.columns:
                if op == "<": df_res = df_res[df_res[numeric_col] < val]
                elif op == ">": df_res = df_res[df_res[numeric_col] > val]
                elif op == "<=": df_res = df_res[df_res[numeric_col] <= val]
                elif op == ">=": df_res = df_res[df_res[numeric_col] >= val]

        # 3. LỌC CÁC CỘT KHÁC - ĐƠN GIẢN
        for col, val in filters.items():
            if col in ["zone_type", "numeric_filters"]: continue
            
            # Tìm cột thật
            real_col = col if col in self.df.columns else None
            if not real_col:
                for c in self.df.columns:
                    if col.lower() == c.lower():
                        real_col = c
                        break
            
            if real_col:
                # Tự động nhận diện cột đặc biệt
                if any(keyword in real_col.lower() for keyword in ['tỉnh', 'thành phố', 'province']):
                    df_res = df_res[df_res['prov_norm'].str.contains(self._normalize(val), na=False)]
                elif any(keyword in real_col.lower() for keyword in ['tên', 'name']) and not real_col.endswith('_num'):
                    df_res = df_res[df_res['name_norm'].str.contains(self._normalize(val), na=False)]
                else:
                    df_res = df_res[df_res[real_col].astype(str).str.contains(str(val), case=False, na=False)]

        return df_res

    def generate_chart_base64(self, df: pd.DataFrame, title: str, metric_col: str = "dual", limit: int = None):
        if df.empty: return None
        df_plot = df.copy()
        
        # Xử lý limit
        if limit == -1:
            # -1 = unlimited, hiển thị tất cả
            limit = len(df_plot)
        elif limit is None:
            # None = default 50 để tránh biểu đồ quá dài
            limit = min(len(df_plot), 50)
        
        # --- Logic Vẽ Biểu Đồ CỘT (BAR CHART) ---
        if metric_col == 'dual':
            # Dual chart: tự động tìm cột giá và diện tích
            price_col = None
            area_col = None
            
            # Tìm cột giá (có chứa từ khóa liên quan)
            for col in df_plot.columns:
                if any(keyword in col.lower() for keyword in ['giá', 'price', 'thuê']) and col.endswith('_num'):
                    price_col = col
                    break
            
            # Tìm cột diện tích (có chứa từ khóa liên quan)  
            for col in df_plot.columns:
                if any(keyword in col.lower() for keyword in ['diện tích', 'area']) and col.endswith('_num'):
                    # Loại trừ các cột về tỷ lệ/hệ số
                    if not any(exclude in col.lower() for exclude in ['lấp đầy', 'sử dụng', 'occupancy', 'tỷ lệ', 'hệ số']):
                        area_col = col
                        break
            
            if price_col and area_col:
                df_plot = df_plot.sort_values([price_col, area_col], ascending=False).head(limit)
            elif price_col:
                df_plot = df_plot.sort_values(price_col, ascending=False).head(limit)
            elif area_col:
                df_plot = df_plot.sort_values(area_col, ascending=False).head(limit)
            else:
                return None
        else:
            # Tìm cột số tương ứng
            numeric_col = self._get_numeric_column(metric_col)
            if numeric_col and numeric_col in df_plot.columns:
                df_plot = df_plot.sort_values(numeric_col, ascending=False).head(limit)
            else:
                return None

        df_plot = df_plot.iloc[::-1] # Đảo ngược để vẽ
        
        # Tự động tìm cột tên để làm label
        name_col = None
        for col in df_plot.columns:
            if any(keyword in col.lower() for keyword in ['tên', 'name']) and not col.endswith('_num'):
                name_col = col
                break
        
        if not name_col:
            name_col = df_plot.columns[0]  # Fallback: dùng cột đầu tiên
            
        names = df_plot[name_col].tolist()
        
        # Điều chỉnh kích thước biểu đồ cho vertical bars (cột dọc)
        width = max(12, len(names) * 0.6)  # Tăng chiều rộng theo số items
        height = 8  # Chiều cao cố định
        plt.figure(figsize=(width, height))
        
        # --- VẼ BIỂU ĐỒ CỘT ---
        if metric_col == 'dual':
            # Tự động tìm cột giá để vẽ
            price_col = None
            for col in df_plot.columns:
                if any(keyword in col.lower() for keyword in ['giá', 'price', 'thuê']) and col.endswith('_num'):
                    price_col = col
                    break
            
            if price_col and price_col in df_plot.columns:
                vals = df_plot[price_col].fillna(0).tolist()
                bars = plt.bar(names, vals, color='#1f77b4')
                plt.ylabel("Giá thuê (USD/m²/năm)")
                # Thêm giá trị lên đầu mỗi cột
                for bar, val in zip(bars, vals):
                    if val > 0:
                        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(vals)*0.01, 
                                f'{val:.0f}', ha='center', va='bottom', fontsize=8)
        else:
            # Vẽ biểu đồ cho bất kỳ cột nào
            numeric_col = self._get_numeric_column(metric_col)
            if numeric_col in df_plot.columns:
                vals = df_plot[numeric_col].fillna(0).tolist()
                
                # Chọn màu dựa trên loại dữ liệu
                if any(keyword in metric_col.lower() for keyword in ['lấp đầy', 'sử dụng', 'occupancy', 'tỷ lệ', 'hệ số']):
                    color = '#ff7f0e'  # Cam cho hệ số/tỷ lệ
                elif any(keyword in metric_col.lower() for keyword in ['diện tích', 'area']):
                    color = '#2ca02c'  # Xanh lá cho diện tích
                elif any(keyword in metric_col.lower() for keyword in ['giá', 'price']):
                    color = '#1f77b4'  # Xanh dương cho giá
                else:
                    color = '#ff7f0e'  # Cam mặc định
                
                bars = plt.bar(names, vals, color=color)
                plt.ylabel(f"{metric_col} (Số liệu)")
                
                # Thêm giá trị lên đầu mỗi cột
                for bar, val in zip(bars, vals):
                    if val > 0:
                        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(vals)*0.01, 
                                f'{val:.1f}', ha='center', va='bottom', fontsize=8)

        plt.title(f"{title} ({len(names)} kết quả)", fontsize=14, fontweight='bold')
        
        # Xoay labels để tránh chồng chéo và cải thiện hiển thị
        plt.xticks(rotation=90, ha='center', fontsize=9)
        plt.xlabel("Khu công nghiệp", fontsize=12)
        
        # Thêm grid để dễ đọc
        plt.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()
        return b64

