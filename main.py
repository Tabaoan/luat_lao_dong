# main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import os
import uvicorn
from typing import Optional, Any, Dict
from pathlib import Path
import json
import inspect
import uuid
from datetime import datetime
import re
import unicodedata

from starlette.concurrency import run_in_threadpool

from mst.router import is_mst_query
from mst.handler import handle_mst_query
from law_db_query.handler import handle_law_count_query

from excel_visualize import (
    is_excel_visualize_intent,
    handle_excel_visualize
)

from excel_query.excel_query import ExcelQueryHandler

# 🎯 IMPORT KCN DETAIL QUERY
try:
    from kcn_detail_query import process_kcn_detail_query
    KCN_DETAIL_AVAILABLE = True
    print("✅ KCN Detail Query module loaded")
except ImportError as e:
    KCN_DETAIL_AVAILABLE = False
    print(f"⚠️ KCN Detail Query not available: {e}")
    def process_kcn_detail_query(*args, **kwargs):
        return None


# ===============================
# Province Zoom Handler - Tích hợp từ province_zoom.py
# ===============================
class ProvinceZoomHandler:
    def __init__(self, geojson_path: str = "map_ui/vn_provinces_34.geojson"):
        self.geojson_path = geojson_path
        self.provinces_data = None
        self.load_provinces_data()
    
    def load_provinces_data(self):
        """Load dữ liệu tỉnh thành từ geojson file"""
        try:
            geojson_file = Path(self.geojson_path)
            if not geojson_file.exists():
                print(f"⚠️ Không tìm thấy file: {self.geojson_path}")
                return
                
            with open(geojson_file, 'r', encoding='utf-8') as f:
                self.provinces_data = json.load(f)
            
            print(f"✅ Đã load {len(self.provinces_data['features'])} tỉnh thành từ {self.geojson_path}")
            
        except Exception as e:
            print(f"❌ Lỗi load provinces data: {e}")
            self.provinces_data = None
    
    def normalize_name(self, name: str) -> str:
        """Chuẩn hóa tên tỉnh để so sánh"""
        if not name:
            return ""
        
        # Loại bỏ dấu tiếng Việt và ký tự đặc biệt
        normalized = unicodedata.normalize('NFD', str(name))
        no_accents = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
        
        # Chỉ giữ lại chữ cái và số, loại bỏ "TP", "Thành phố"
        clean = re.sub(r'[^a-zA-Z0-9]', '', no_accents)
        clean = re.sub(r'(tp|thanhpho)', '', clean, flags=re.IGNORECASE)
        
        return clean.lower()
    
    def find_province_by_name(self, province_name: str) -> Optional[Dict]:
        """Tìm tỉnh trong geojson data theo tên với logic matching linh hoạt"""
        if not self.provinces_data:
            return None
        
        target = self.normalize_name(province_name)
        
        # Thử exact match trước
        for feature in self.provinces_data['features']:
            properties = feature.get('properties', {})
            name = properties.get('name', '')
            
            if self.normalize_name(name) == target:
                return feature
        
        # Thử partial match (contains)
        for feature in self.provinces_data['features']:
            properties = feature.get('properties', {})
            name = properties.get('name', '')
            normalized_name = self.normalize_name(name)
            
            # Kiểm tra 2 chiều: target in name hoặc name in target
            if target and normalized_name and (target in normalized_name or normalized_name in target):
                return feature
        
        return None
    
    def calculate_bounds(self, geometry: Dict) -> Optional[tuple]:
        """Tính bounds (min_lng, min_lat, max_lng, max_lat) từ geometry"""
        try:
            coordinates = []
            
            if geometry['type'] == 'Polygon':
                coordinates = geometry['coordinates'][0]
            elif geometry['type'] == 'MultiPolygon':
                for polygon in geometry['coordinates']:
                    coordinates.extend(polygon[0])
            else:
                return None
            
            if not coordinates:
                return None
            
            # Tính min/max lng/lat
            lngs = [coord[0] for coord in coordinates]
            lats = [coord[1] for coord in coordinates]
            
            return (min(lngs), min(lats), max(lngs), max(lats))
            
        except Exception as e:
            print(f"❌ Lỗi tính bounds: {e}")
            return None
    
    def get_province_zoom_bounds(self, province_name: str) -> Optional[Dict]:
        """Lấy thông tin zoom bounds cho tỉnh"""
        feature = self.find_province_by_name(province_name)
        if not feature:
            return None
        
        geometry = feature.get('geometry')
        if not geometry:
            return None
        
        bounds = self.calculate_bounds(geometry)
        if not bounds:
            return None
        
        min_lng, min_lat, max_lng, max_lat = bounds
        
        # Tính center
        center_lng = (min_lng + max_lng) / 2
        center_lat = (min_lat + max_lat) / 2
        
        # Tính zoom level dựa trên kích thước bounds
        lng_diff = max_lng - min_lng
        lat_diff = max_lat - min_lat
        max_diff = max(lng_diff, lat_diff)
        
        # Zoom level logic - Tăng cao hơn để thấy chi tiết thành phố
        if max_diff > 2:
            zoom_level = 11
        elif max_diff > 1:
            zoom_level = 12
        elif max_diff > 0.5:
            zoom_level = 13
        elif max_diff > 0.2:
            zoom_level = 14
        else:
            zoom_level = 15
        
        return {
            "province_name": feature['properties']['name'],
            "bounds": bounds,
            "center": [center_lng, center_lat],
            "zoom_level": zoom_level,
            "geometry": geometry
        }

# Global instance
province_zoom_handler = ProvinceZoomHandler()

def get_province_zoom_info(province_name: str) -> Optional[Dict]:
    """Hàm tiện ích để lấy thông tin zoom province"""
    return province_zoom_handler.get_province_zoom_bounds(province_name)


# ===============================
# Import Chatbot từ app.py
# ===============================
try:
    import app  # app.py: LangChain chatbot + vectordb + llm + emb + excel_handler + sheet funcs
    CHATBOT_AVAILABLE = True
    print("✅ Đã import thành công module 'app'")
except ImportError as e:
    app = None
    CHATBOT_AVAILABLE = False
    print(f"⚠️ Could not import 'app' module. Error: {e}")


# ===============================
# Helper: parse JSON string từ pipeline
# ===============================
def try_parse_json_string(s: Any):
    """
    Nếu s là JSON string thì parse ra dict/list; không thì trả None.
    """
    if not isinstance(s, str):
        return None
    t = s.strip()
    if not t:
        return None
    if (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]")):
        try:
            return json.loads(t)
        except Exception:
            return None
    return None


# ===============================
# Lấy các hằng số từ app.py
# ===============================
CONTACT_TRIGGER_RESPONSE = None
if CHATBOT_AVAILABLE and hasattr(app, "CONTACT_TRIGGER_RESPONSE"):
    CONTACT_TRIGGER_RESPONSE = app.CONTACT_TRIGGER_RESPONSE
    print("✅ Đã load CONTACT_TRIGGER_RESPONSE từ app.py")
else:
    CONTACT_TRIGGER_RESPONSE = (
        "Anh/chị vui lòng để lại tên và số điện thoại, chuyên gia của IIP sẽ liên hệ "
        "và giải đáp các yêu cầu của anh/chị ạ."
    )
    print("⚠️ Sử dụng CONTACT_TRIGGER_RESPONSE mặc định")


# ===============================
# Kiểm tra Google Sheet availability
# ===============================
SHEET_AVAILABLE = False
try:
    if CHATBOT_AVAILABLE and hasattr(app, "save_contact_info") and hasattr(app, "is_valid_phone"):
        SHEET_AVAILABLE = True
        print("✅ Google Sheet functions đã sẵn sàng từ app.py")
    else:
        print("⚠️ Google Sheet functions not found in app.py")
except Exception as e:
    print(f"⚠️ Error checking Google Sheet availability: {e}")


# --- Khai báo Model cho dữ liệu đầu vào ---
class Question(BaseModel):
    question: str
    phone: Optional[str] = None
    session_id: Optional[str] = None  
    name: Optional[str] = None
    url: Optional[str] = None


class ContactInfo(BaseModel):
    original_question: str
    phone: str
    name: Optional[str] = None


# ---------------------------------------
# 1️⃣ Khởi tạo FastAPI App + bật CORS
# ---------------------------------------
app_fastapi = FastAPI(
    title="Chatbot Luật Lao động API",
    description="API cho mô hình chatbot",
    version="1.0.0"
)

origins = ["*"]

app_fastapi.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------
# 🎨 Mount Static Files và Templates
# ---------------------------------------
app_fastapi.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ---------------------------------------
# 2️⃣ Init ExcelQueryHandler (KCN/CCN)
# ---------------------------------------
BASE_DIR = Path(__file__).resolve().parent

EXCEL_FILE_PATH = str(BASE_DIR / "data" / "IIPMap_FULL_63_COMPLETE.xlsx")
GEOJSON_IZ_PATH = str(BASE_DIR / "map_ui" / "industrial_zones.geojson")

excel_kcn_handler = ExcelQueryHandler(
    excel_path=EXCEL_FILE_PATH,
    geojson_path=GEOJSON_IZ_PATH
)


# ---------------------------------------
# 3️⃣ Route trang chủ và API status
# ---------------------------------------
@app_fastapi.get("/", response_class=HTMLResponse, summary="Trang chủ ChatIIP UI")
async def home_ui(request: Request):
    """Trang chủ với giao diện chatbot đầy đủ"""
    return templates.TemplateResponse("index.html", {"request": request})

@app_fastapi.get("/api", summary="API Status - Kiểm tra trạng thái API")
async def api_status():
    vectordb_status = "Unknown"
    if CHATBOT_AVAILABLE:
        try:
            stats = app.get_vectordb_stats()
            if stats.get("exists", False):
                vectordb_status = f"Ready ({stats.get('total_documents', 0)} docs)"
            else:
                vectordb_status = "Empty or Not Found"
        except Exception as e:
            vectordb_status = f"Error: {str(e)}"

    return {
        "message": "✅ Chatbot Luật Lao động API đang hoạt động.",
        "usage": "Gửi POST tới /chat với JSON { 'question': 'Câu hỏi của bạn' }",
        "chatbot_status": "Available" if CHATBOT_AVAILABLE else "Not Available",
        "vectordb_status": vectordb_status,
        "sheet_status": "Available" if SHEET_AVAILABLE else "Not Available",
        "contact_trigger": CONTACT_TRIGGER_RESPONSE,
        "excel_file_exists": Path(EXCEL_FILE_PATH).exists(),
        "geojson_file_exists": Path(GEOJSON_IZ_PATH).exists(),
    }


# ---------------------------------------
# 4️⃣ Route chính: /chat (POST)
# ---------------------------------------
@app_fastapi.post("/chat", summary="Trả lời câu hỏi từ Chatbot (có lịch sử theo session_id)")
async def predict(data: Question, request: Request):
    question = (data.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Thiếu trường 'question' hoặc câu hỏi bị rỗng.")

    # ✅ Lấy session_id giống main_local
    session = (
        (data.session_id or "").strip()
        or (request.headers.get("X-Session-Id") or "").strip()
    )
    if not session:
        session = f"anon-{uuid.uuid4()}"

    try:
        answer: Optional[str] = None
        requires_contact = False

        # ===============================
        # 0️⃣ LAW COUNT – SQL FIRST
        # ===============================
        payload = handle_law_count_query(question)
        if isinstance(payload, dict) and payload.get("intent") == "law_count":
            if not CHATBOT_AVAILABLE or not hasattr(app, "chatbot"):
                return {
                    "answer": "Backend chưa sẵn sàng (không import được app.py/chatbot).",
                    "requires_contact": False,
                    "session_id": session
                }

            response = await run_in_threadpool(
                app.chatbot.invoke,
                {"message": question, "law_count": payload["total_laws"]},
                config={"configurable": {"session_id": session}}
            )

            parsed = try_parse_json_string(response)
            if isinstance(parsed, dict) and parsed.get("type") == "flowchart":
                return {
                    "answer": "Đây là flowchart do ChatIIP tạo cho bạn:",
                    "type": "flowchart",
                    "payload": {
                        "format": parsed.get("format", "mermaid"),
                        "code": parsed.get("code", ""),
                        "explanation": parsed.get("explanation", "")
                    },
                    "requires_contact": False,
                    "session_id": session
                }

            return {"answer": response, "requires_contact": False, "session_id": session}

        # ===============================
        # 1️⃣ MST INTENT (ƯU TIÊN CAO NHẤT)
        # ===============================
        if is_mst_query(question):
            if not CHATBOT_AVAILABLE:
                return {
                    "answer": "Backend chưa sẵn sàng (không import được app.py).",
                    "requires_contact": False,
                    "session_id": session
                }

            mst_answer = await run_in_threadpool(
                handle_mst_query,
                message=question,
                llm=app.llm,
                embedding=app.emb
            )
            return {"answer": mst_answer, "requires_contact": False, "session_id": session}

        # ===============================
        # 2️⃣ EXCEL VISUALIZE
        # ===============================
        if is_excel_visualize_intent(question):
            if not CHATBOT_AVAILABLE:
                return {
                    "answer": "Backend chưa sẵn sàng ",
                    "requires_contact": False,
                    "session_id": session
                }

            excel_result = await run_in_threadpool(
                handle_excel_visualize,
                message=question,
                #excel_handler=app.excel_handler
            )
            return {
                "answer": "Đây là biểu đồ do Chatiip tạo cho bạn: ",
                "type": "excel_visualize",
                "payload": excel_result,
                "requires_contact": False,
                "session_id": session
            }

        # ===============================
        # 3️⃣ KCN DETAIL QUERY - ƯU TIÊN CAO
        # ===============================
        if KCN_DETAIL_AVAILABLE:
            llm = app.llm if CHATBOT_AVAILABLE and hasattr(app, 'llm') else None
            embedding = app.emb if CHATBOT_AVAILABLE and hasattr(app, 'emb') else None
            
            kcn_detail_result = process_kcn_detail_query(question, llm=llm, embedding=embedding)
            if kcn_detail_result:
                if kcn_detail_result["type"] == "kcn_detail":
                    # Tạo response với thông tin chi tiết, tọa độ chính xác và RAG analysis
                    return {
                        "answer": kcn_detail_result,
                        "type": "kcn_detail", 
                        "requires_contact": False,
                        "session_id": session
                    }
                elif kcn_detail_result["type"] == "kcn_detail_not_found":
                    return {
                        "answer": kcn_detail_result["message"],
                        "type": "text",
                        "requires_contact": False,
                        "session_id": session
                    }

        # ===============================
        # 4️⃣ EXCEL KCN/CCN (BẢNG + TỌA ĐỘ) - ƯU TIÊN TRƯỚC LLM
        # ===============================
        handled, excel_payload = await run_in_threadpool(
            excel_kcn_handler.process_query,
            question,
            True  # return_json=True
        )

        if handled and excel_payload:
            try:
                excel_obj = json.loads(excel_payload) if isinstance(excel_payload, str) else excel_payload
            except Exception:
                excel_obj = {"error": "ExcelQuery trả về dữ liệu không hợp lệ."}

            # Nếu có lỗi yêu cầu làm rõ (thiếu tỉnh/thiếu loại)
            if isinstance(excel_obj, dict) and excel_obj.get("error"):
                return {
                    "answer": excel_obj,
                    "type": "excel_query",
                    "map_intent": None,
                    "requires_contact": False,
                    "session_id": session
                }

            iz_list = []
            if isinstance(excel_obj, dict):
                for r in excel_obj.get("data", []) or []:
                    coords = r.get("coordinates")
                    if isinstance(coords, list) and len(coords) == 2:
                        iz_list.append({
                            "name": r.get("Tên", ""),
                            "kind": r.get("Loại", excel_obj.get("type")),
                            "address": r.get("Địa chỉ", ""),
                            "coordinates": coords
                        })

            province = excel_obj.get("province") if isinstance(excel_obj, dict) else None
            
            # 🎯 LẤY PROVINCE ZOOM INFO
            province_zoom = None
            if province and province != "TOÀN QUỐC":
                province_zoom = get_province_zoom_info(province)
                if province_zoom:
                    print(f"✅ Đã lấy province zoom cho {province}: zoom level {province_zoom['zoom_level']}")

            if province and province != "TOÀN QUỐC":
                map_intent = {
                    "type": "province",
                    "province": province,
                    "iz_list": iz_list,
                    "kind": excel_obj.get("type"),
                    "province_zoom": province_zoom  # 🎯 THÊM PROVINCE ZOOM
                }
            else:
                map_intent = {
                    "type": "points",
                    "iz_list": iz_list,
                    "kind": excel_obj.get("type") if isinstance(excel_obj, dict) else None,
                    "province_zoom": province_zoom  # 🎯 THÊM PROVINCE ZOOM (có thể null)
                }

            return {
                "answer": excel_obj,
                "type": "excel_query",
                "map_intent": map_intent,
                "requires_contact": False,
                "session_id": session
            }

        # ===============================
        # 5️⃣ FALLBACK: gọi chatbot thật (RAG/PDF pipeline)
        # ===============================
        if CHATBOT_AVAILABLE and hasattr(app, "chatbot") and hasattr(app.chatbot, "invoke"):
            try:
                if inspect.iscoroutinefunction(app.chatbot.invoke):
                    response = await app.chatbot.invoke(
                        {"message": question},
                        config={"configurable": {"session_id": session}}
                    )
                else:
                    response = await run_in_threadpool(
                        app.chatbot.invoke,
                        {"message": question},
                        config={"configurable": {"session_id": session}}
                    )

                if isinstance(response, dict) and "output" in response:
                    answer = response["output"]
                elif isinstance(response, str):
                    answer = response
                else:
                    answer = f"Lỗi: Chatbot trả về định dạng không mong muốn: {repr(response)}"

                # ✅ Parse flowchart JSON nếu có
                parsed = try_parse_json_string(answer)
                if isinstance(parsed, dict) and parsed.get("type") == "flowchart":
                    return {
                        "answer": "Đây là flowchart do ChatIIP tạo cho bạn:",
                        "type": "flowchart",
                        "payload": {
                            "format": parsed.get("format", "mermaid"),
                            "code": parsed.get("code", ""),
                            "explanation": parsed.get("explanation", "")
                        },
                        "requires_contact": False,
                        "session_id": session
                    }

                if answer and answer.strip() == CONTACT_TRIGGER_RESPONSE.strip():
                    requires_contact = True

            except Exception as invoke_error:
                print(f"❌ Lỗi khi gọi chatbot.invoke: {invoke_error}")
                answer = "Xin lỗi, đã xảy ra lỗi khi xử lý câu hỏi của bạn."
        else:
            answer = (
                f"(Chatbot mô phỏng - LỖI BACKEND: Không tìm thấy đối tượng app.chatbot) "
                f"Bạn hỏi: '{question}'"
            )

        # ===============================
        # 5️⃣ Nếu người dùng gửi phone ngay từ đầu (tuỳ chọn)
        # ===============================
        if data.phone and SHEET_AVAILABLE and CHATBOT_AVAILABLE:
            try:
                await run_in_threadpool(
                    app.save_contact_info,
                    question,
                    data.phone,
                    data.name or ""
                )
            except Exception as sheet_error:
                print(f"⚠️ Lỗi ghi Google Sheet: {sheet_error}")

        return {
            "answer": answer,
            "requires_contact": requires_contact,
            "session_id": session
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ LỖI CHATBOT: {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý Chatbot: {str(e)}")


# ---------------------------------------
# 5️⃣ Route: /submit-contact (POST)
# ---------------------------------------
@app_fastapi.post("/submit-contact", summary="Gửi thông tin liên hệ sau khi chatbot yêu cầu")
async def submit_contact(data: ContactInfo):
    if not SHEET_AVAILABLE or not CHATBOT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Google Sheet không khả dụng.")

    phone = (data.phone or "").strip()
    if not app.is_valid_phone(phone):
        raise HTTPException(status_code=400, detail="Số điện thoại không hợp lệ.")

    try:
        await run_in_threadpool(
            app.save_contact_info,
            data.original_question,
            phone,
            data.name or ""
        )

        return {
            "success": True,
            "message": "Cảm ơn anh/chị! Chuyên gia của IIP sẽ liên hệ với anh/chị trong thời gian sớm nhất.",
            "contact_saved": {
                "question": data.original_question,
                "phone": phone,
                "name": data.name or ""
            }
        }

    except Exception as e:
        print(f"❌ Lỗi khi lưu thông tin liên hệ: {e}")
        raise HTTPException(status_code=500, detail=f"Không thể lưu thông tin liên hệ. Lỗi: {str(e)}")


# ---------------------------------------
# 6️⃣ Route: /status (GET)
# ---------------------------------------
@app_fastapi.get("/status", summary="Kiểm tra trạng thái chi tiết của hệ thống")
async def get_status():
    if not CHATBOT_AVAILABLE:
        return {
            "chatbot": "Not Available",
            "vectordb": "Unknown",
            "google_sheet": "Unknown",
            "error": "Module app.py không được import thành công"
        }

    vectordb_info: Dict[str, Any] = {}
    try:
        stats = app.get_vectordb_stats()
        vectordb_info = {
            "status": "Ready" if stats.get("exists", False) else "Not Ready",
            "index_name": stats.get("name", "Unknown"),
            "total_documents": stats.get("total_documents", 0),
            "dimension": stats.get("dimension", 0),
            "exists": stats.get("exists", False)
        }
    except Exception as e:
        vectordb_info = {"status": "Error", "error": str(e)}

    sheet_info = {
        "status": "Available" if SHEET_AVAILABLE else "Not Available",
        "sheet_id": os.getenv("GOOGLE_SHEET_ID", "Not configured")
    }

    return {
        "chatbot": "Available",
        "vectordb": vectordb_info,
        "google_sheet": sheet_info,
        "trigger_response": CONTACT_TRIGGER_RESPONSE,
        "excel_file": EXCEL_FILE_PATH,
        "geojson_file": GEOJSON_IZ_PATH
    }

# Điền ra cuộc lịch sử hội thoại

@app_fastapi.get("/history/{session_id}", summary="Lấy lịch sử hội thoại")
async def get_chat_history(session_id: str):
    if not CHATBOT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Chatbot not available")

    try:
        history = app.get_history(session_id)
        messages = []

        for m in history.messages:
            messages.append({
                "role": m.type,   # human / ai / system
                "content": m.content
            })

        return {
            "session_id": session_id,
            "messages": messages
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------
# 🎯 ROUTE XUẤT JSON VỚI TỌA ĐỘ VÀ PROVINCE ZOOM
# ---------------------------------------
@app_fastapi.post("/export-json", summary="Xuất dữ liệu JSON với tọa độ và province zoom")
async def export_json(data: Question):
    question = (data.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Thiếu câu hỏi")

    try:
        # Xử lý query giống như /chat nhưng chỉ trả JSON
        handled, excel_payload = await run_in_threadpool(
            excel_kcn_handler.process_query,
            question,
            True
        )

        if not handled or not excel_payload:
            raise HTTPException(status_code=404, detail="Không tìm thấy dữ liệu phù hợp")

        try:
            excel_obj = json.loads(excel_payload) if isinstance(excel_payload, str) else excel_payload
        except Exception:
            raise HTTPException(status_code=500, detail="Dữ liệu không hợp lệ")

        if isinstance(excel_obj, dict) and excel_obj.get("error"):
            raise HTTPException(status_code=400, detail=excel_obj["error"])

        # Thêm province zoom info
        province = excel_obj.get("province")
        if province and province != "TOÀN QUỐC":
            province_zoom = get_province_zoom_info(province)
            if province_zoom:
                excel_obj["province_zoom"] = province_zoom

        # Tạo filename ASCII-safe
        import re
        import unicodedata
        
        def make_ascii_filename(text):
            # Normalize unicode và loại bỏ dấu
            normalized = unicodedata.normalize('NFD', text)
            ascii_text = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
            # Chỉ giữ lại ký tự ASCII an toàn
            safe_text = re.sub(r'[^\w\-_]', '_', ascii_text)
            return safe_text
        
        province_name = make_ascii_filename(province) if province else "Unknown"
        type_name = make_ascii_filename(excel_obj.get("type", "KCN"))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Export_{province_name}_{type_name}_{timestamp}.json"

        # Trả về JSON file
        from fastapi.responses import JSONResponse
        
        return JSONResponse(
            content=excel_obj,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi xuất JSON: {str(e)}")

@app_fastapi.post("/export-chart-json", summary="Xuất dữ liệu biểu đồ JSON với tọa độ")
async def export_chart_json(data: Question):
    question = (data.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Thiếu câu hỏi")

    try:
        # Xử lý excel visualize
        if not is_excel_visualize_intent(question):
            raise HTTPException(status_code=400, detail="Không phải câu hỏi về biểu đồ")

        excel_result = await run_in_threadpool(
            handle_excel_visualize,
            message=question
        )

        if excel_result.get("type") == "error":
            raise HTTPException(status_code=400, detail=excel_result.get("message", "Lỗi tạo biểu đồ"))

        # Tạo filename ASCII-safe
        import re
        import unicodedata
        
        def make_ascii_filename(text):
            # Normalize unicode và loại bỏ dấu
            normalized = unicodedata.normalize('NFD', text)
            ascii_text = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
            # Chỉ giữ lại ký tự ASCII an toàn
            safe_text = re.sub(r'[^\w\-_]', '_', ascii_text)
            return safe_text
        
        province_name = make_ascii_filename(excel_result.get("province", "Unknown"))
        metric = excel_result.get("metric", "chart")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Chart_{province_name}_{metric}_{timestamp}.json"

        # Trả về JSON file
        from fastapi.responses import JSONResponse
        
        return JSONResponse(
            content=excel_result,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi xuất JSON biểu đồ: {str(e)}")

# ---------------------------------------
# 🗺️ ROUTES CHO INTERACTIVE MAP CHATBOT
# ---------------------------------------

# Global variable để lưu map intent
_current_map_intent = None

@app_fastapi.post("/chatbot", summary="API cho chatbot trong interactive map")
async def chatbot_for_map(data: Question):
    """API tương thích với chatbot trong interactive_satellite_map.html"""
    global _current_map_intent
    
    question = (data.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Thiếu câu hỏi")

    # ✅ Lấy session_id
    session = data.session_id or f"map-{uuid.uuid4()}"

    try:
        answer = None
        map_intent = None

        # ===============================
        # 1️⃣ MST INTENT
        # ===============================
        if is_mst_query(question):
            if not CHATBOT_AVAILABLE:
                return {"answer": "Backend chưa sẵn sàng", "map_intent": None}

            mst_answer = await run_in_threadpool(
                handle_mst_query,
                message=question,
                llm=app.llm,
                embedding=app.emb
            )
            return {"answer": mst_answer, "map_intent": None}

        # ===============================
        # 2️⃣ EXCEL KCN/CCN (BẢNG + TỌA ĐỘ)
        # ===============================
        handled, excel_payload = await run_in_threadpool(
            excel_kcn_handler.process_query,
            question,
            True
        )

        if handled and excel_payload:
            try:
                excel_obj = json.loads(excel_payload) if isinstance(excel_payload, str) else excel_payload
            except Exception:
                excel_obj = {"error": "ExcelQuery trả về dữ liệu không hợp lệ."}

            if isinstance(excel_obj, dict) and excel_obj.get("error"):
                return {"answer": excel_obj, "map_intent": None}

            # Tạo map_intent cho interactive map
            province = excel_obj.get("province")
            if province and province != "TOÀN QUỐC":
                # Tạo iz_list từ data
                iz_list = []
                for item in excel_obj.get("data", []):
                    coords = item.get("coordinates")
                    if coords and len(coords) == 2:
                        iz_list.append({
                            "name": item.get("Tên", ""),
                            "kind": item.get("Loại", ""),
                            "address": item.get("Địa chỉ", ""),
                            "coordinates": coords
                        })

                # 🎯 LẤY PROVINCE ZOOM INFO
                province_zoom = get_province_zoom_info(province)
                
                map_intent = {
                    "type": "province",
                    "province": province,
                    "iz_list": iz_list,
                    "province_zoom": province_zoom  # 🎯 THÊM PROVINCE ZOOM
                }

                # Nếu chỉ có 1 kết quả, zoom vào zone cụ thể
                if len(iz_list) == 1:
                    zone = iz_list[0]
                    map_intent = {
                        "type": "zone",
                        "zone_name": zone["name"],
                        "coordinates": zone["coordinates"],
                        "province_zoom": province_zoom  # 🎯 THÊM PROVINCE ZOOM
                    }

            # Lưu map_intent để polling
            _current_map_intent = map_intent

            return {"answer": excel_obj, "map_intent": map_intent}

        # ===============================
        # 3️⃣ FALLBACK: gọi chatbot thật
        # ===============================
        if CHATBOT_AVAILABLE and hasattr(app, "chatbot"):
            try:
                response = await run_in_threadpool(
                    app.chatbot.invoke,
                    {"message": question},
                    config={"configurable": {"session_id": session}}
                )

                if isinstance(response, dict) and "output" in response:
                    answer = response["output"]
                elif isinstance(response, str):
                    answer = response
                else:
                    answer = f"Lỗi: Chatbot trả về định dạng không mong muốn"

            except Exception as e:
                answer = f"Lỗi xử lý: {str(e)}"
        else:
            answer = f"Chatbot không khả dụng. Bạn hỏi: '{question}'"

        return {"answer": answer, "map_intent": map_intent}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý: {str(e)}")

@app_fastapi.get("/map_intent_poll", summary="Polling map intent cho interactive map")
async def map_intent_poll():
    """API để interactive map poll map intent"""
    global _current_map_intent
    
    if _current_map_intent:
        intent = _current_map_intent
        _current_map_intent = None  # Clear sau khi trả về
        return intent
    else:
        return {"status": "empty"}

@app_fastapi.post("/map_intent", summary="Set map intent cho interactive map")
async def set_map_intent(intent_data: dict):
    """API để set map intent từ bên ngoài"""
    global _current_map_intent
    _current_map_intent = intent_data
    return {"status": "success"}

# ---------------------------------------
# 7️⃣ Run server
# ---------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app_fastapi", host="0.0.0.0", port=port, log_level="info", reload=True)
