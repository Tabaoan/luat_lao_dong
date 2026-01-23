import re
import json
from pathlib import Path

# ================== CONFIG ==================
INPUT_JSON = r"pdf_full_content.json"   # đổi sang path máy bạn nếu chạy local
OUTPUT_JSON = "pdf_structured_by_toc.json"

# ================== UTILS ==================
def load_full_text(json_path: str) -> str:
    """
    Hỗ trợ cả 2 dạng:
    - dict: {"content": "..."}
    - list: [{"content": "..."}, ...]
    """
    data = json.load(open(json_path, "r", encoding="utf-8"))

    if isinstance(data, dict) and "content" in data:
        return data["content"] or ""

    if isinstance(data, list):
        # nếu list các page dict => nối lại
        parts = []
        for item in data:
            if isinstance(item, dict) and "content" in item:
                parts.append(item["content"] or "")
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)

    raise TypeError("JSON không đúng format: cần dict có key 'content' hoặc list các phần tử có 'content'.")

def clean_flat(text: str) -> str:
    """
    Flatten whitespace để không phụ thuộc vào newline (vì PDF extract bị vỡ dòng).
    """
    if not text:
        return ""
    text = re.sub(r"-\s*\n", "", text)     # bỏ gạch nối xuống dòng
    text = re.sub(r"\s+", " ", text)       # mọi whitespace -> 1 space
    return text.strip()

# ================== STEP 1: SPLIT TOC / BODY ==================
def split_toc_and_body(clean_text: str):
    m_toc = re.search(r"\bMỤC\s+LỤC\b", clean_text, flags=re.IGNORECASE)
    if not m_toc:
        raise RuntimeError("Không tìm thấy 'MỤC LỤC' trong văn bản.")

    toc_start = m_toc.start()

    # tìm "LỜI NÓI ĐẦU" trong phần sau TOC:
    # - ở TOC: "LỜI NÓI ĐẦU 5" (sau nó là số)
    # - ở BODY: "LỜI NÓI ĐẦU Phần lớn..." (sau nó không phải số)
    body_start = None
    for m in re.finditer(r"LỜI\s+NÓI\s+ĐẦU", clean_text[toc_start:], flags=re.IGNORECASE):
        abs_pos = toc_start + m.start()
        after = clean_text[abs_pos + (m.end() - m.start()):]
        if not re.match(r"\s*\d+\b", after):  # không có số trang ngay sau => body
            body_start = abs_pos
            break

    if body_start is None:
        raise RuntimeError("Tìm thấy 'MỤC LỤC' nhưng không xác định được điểm bắt đầu BODY (LỜI NÓI ĐẦU).")

    toc_text = clean_text[toc_start:body_start].strip()
    body_text = clean_text[body_start:].strip()
    return toc_text, body_text

# ================== STEP 2: PARSE TOC KEYS ==================
# Chỉ bắt:
# - "1." "2." ... (chapter)
# - "1.1" "2.1.3" ... (section)
# - "LỜI NÓI ĐẦU"
TOC_KEY_RE = re.compile(r"\bLỜI\s+NÓI\s+ĐẦU\b|\b\d+\.\d+(?:\.\d+)*\b|\b\d+\.")

def parse_toc_items(toc_text: str):
    matches = list(TOC_KEY_RE.finditer(toc_text))
    if not matches:
        raise RuntimeError("Không parse được mục nào từ MỤC LỤC (TOC_KEY_RE không match).")

    items = []
    for i, m in enumerate(matches):
        raw_key = toc_text[m.start():m.end()].strip()

        # normalize key
        if re.fullmatch(r"LỜI\s+NÓI\s+ĐẦU", raw_key, flags=re.IGNORECASE):
            key = "LỜI NÓI ĐẦU"
        else:
            key = raw_key[:-1] if raw_key.endswith(".") else raw_key

        seg_start = m.end()
        seg_end = matches[i + 1].start() if i + 1 < len(matches) else len(toc_text)
        seg = toc_text[seg_start:seg_end].strip()

        # bỏ số trang ở cuối segment (nếu có)
        seg = re.sub(r"\s+\d{1,4}\s*$", "", seg).strip()
        seg = re.sub(r"\s+", " ", seg)

        title = "LỜI NÓI ĐẦU" if key == "LỜI NÓI ĐẦU" else seg
        if title:
            items.append({"key": key, "title": title})

    # dedup theo key (giữ item đầu tiên)
    seen = set()
    dedup = []
    for it in items:
        if it["key"] in seen:
            continue
        seen.add(it["key"])
        dedup.append(it)

    return dedup

# ================== STEP 3: FIND HEADINGS IN BODY ==================
def find_positions_in_body(body_text: str, toc_items):
    positions = []

    for it in toc_items:
        key = it["key"]

        if key == "LỜI NÓI ĐẦU":
            # tránh match "LỜI NÓI ĐẦU 5" kiểu TOC (ở body thì sau nó không phải số)
            pat = re.compile(r"\bLỜI\s+NÓI\s+ĐẦU\b(?!\s+\d)", re.IGNORECASE)
        else:
            # key "1" => match "1. " ; key "1.1" => match "1.1 "
            if "." in key:
                pat = re.compile(rf"(?:^|\s){re.escape(key)}\s+", re.IGNORECASE)
            else:
                pat = re.compile(rf"(?:^|\s){re.escape(key)}\.\s+", re.IGNORECASE)

        m = pat.search(body_text)
        if m:
            positions.append({
                "id": key,
                "title": it["title"],
                "start": m.start()
            })

    positions.sort(key=lambda x: x["start"])
    return positions

# ================== STEP 4: CHUNK ==================
def chunk_by_positions(body_text: str, positions):
    out = []
    for i, p in enumerate(positions):
        start = p["start"]
        end = positions[i + 1]["start"] if i + 1 < len(positions) else len(body_text)
        content = body_text[start:end].strip()
        if not content:
            continue
        out.append({
            "id": p["id"],
            "title": p["title"],
            "content": content
        })
    return out

# ================== MAIN ==================
if __name__ == "__main__":
    raw = load_full_text(INPUT_JSON)
    clean = clean_flat(raw)

    toc_text, body_text = split_toc_and_body(clean)
    toc_items = parse_toc_items(toc_text)

    positions = find_positions_in_body(body_text, toc_items)
    if not positions:
        raise RuntimeError("Parse được TOC nhưng không tìm thấy heading tương ứng trong BODY.")

    sections = chunk_by_positions(body_text, positions)

    result = {
        "input": str(INPUT_JSON),
        "toc_items_total": len(toc_items),
        "sections_found": len(sections),
        "sections": sections
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ DONE: {len(sections)} sections saved to {OUTPUT_JSON}")
