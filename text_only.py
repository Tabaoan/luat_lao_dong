import fitz  # PyMuPDF
import re
import json
import os

# ===================== CONFIG =====================

PDF_PATH = r"C:\Users\tabao\OneDrive\Desktop\Quyết định-36-2025-QĐ-TTg.pdf"
OUTPUT_JSON = "quyet_dinh_36_by_sections_01_99.json"

# ===================== TABLE HEURISTIC =====================

def is_table_block(text: str) -> bool:
    text = text.strip()

    if len(text) < 20:
        return True

    if re.search(r"\s{3,}", text):
        return True

    if len(re.findall(r"\b\d{3,5}\b", text)) >= 3:
        return True

    lines = text.splitlines()
    numeric_lines = sum(
        1 for l in lines
        if re.fullmatch(r"[A-Z]?\s*\d{1,5}", l.strip())
    )

    return numeric_lines >= 3

# ===================== STEP 1: EXTRACT CLEAN TEXT =====================

def extract_full_clean_text(pdf_path: str) -> str:
    pdf = fitz.open(pdf_path)
    parts = []

    for page in pdf:
        blocks = page.get_text("blocks")
        for block in blocks:
            text = block[4].strip()
            if not text:
                continue
            if is_table_block(text):
                continue
            parts.append(text)

    return "\n\n".join(parts)

# ===================== STEP 2: SPLIT BY 01–99 =====================

def split_by_main_sections(clean_text: str):
    """
    Chia nội dung theo các đầu mục 01 → 99
    """
    pattern = re.compile(r"(?=\n\d{2}\s*:)")

    chunks = pattern.split("\n" + clean_text)
    sections = {}

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue

        header_match = re.match(r"(\d{2})\s*:\s*(.+)", chunk)
        if not header_match:
            continue

        code = header_match.group(1)
        title = header_match.group(2).splitlines()[0].strip()

        sections[code] = {
            "section_code": code,
            "section_title": title,
            "text": chunk
        }

    return sections

# ===================== STEP 3: SAVE JSON =====================

def save_sections_to_json(pdf_path: str, output_json: str):
    clean_text = extract_full_clean_text(pdf_path)

    if not clean_text:
        raise RuntimeError("❌ Không có nội dung sau khi lọc bảng")

    sections = split_by_main_sections(clean_text)

    data = {
        "source": os.path.basename(pdf_path),
        "document": "Quyết định 36/2025/QĐ-TTg",
        "content_type": "economic_system_sections_01_99",
        "total_sections": len(sections),
        "sections": sections
    }

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ Đã lưu {len(sections)} đầu mục (01–99) vào file JSON:")
    print(f"   {output_json}")

# ===================== RUN =====================

if __name__ == "__main__":
    save_sections_to_json(PDF_PATH, OUTPUT_JSON)
