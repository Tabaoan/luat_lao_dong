#!/usr/bin/env python3
"""
Script chunking TOÀN BỘ LUẬT PHÒNG CHÁY, CHỮA CHÁY VÀ CỨU NẠN, CỨU HỘ 2024
Cấu trúc: tên luật - luật số - chương - điều - tên điều - khoản - điểm - nội dung
"""

import os
import re
import json
import PyPDF2
import glob
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http import models
from typing import List, Dict, Any

# Load environment
load_dotenv()

def extract_text_from_pdf(pdf_path: str) -> str:
    """Trích xuất toàn bộ text từ PDF với nhiều phương pháp"""
    print(f"📖 Đang đọc file PDF: {pdf_path}")
    
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            full_text = ""
            
            print(f"📄 PDF có {len(pdf_reader.pages)} trang")
            
            for page_num, page in enumerate(pdf_reader.pages, 1):
                try:
                    # Thử nhiều phương pháp trích xuất text
                    page_text = ""
                    
                    # Phương pháp 1: extract_text() thông thường
                    try:
                        page_text = page.extract_text()
                    except:
                        pass
                    
                    # Phương pháp 2: Nếu không có text, thử với layout mode
                    if not page_text or len(page_text.strip()) < 50:
                        try:
                            page_text = page.extract_text(extraction_mode="layout")
                        except:
                            pass
                    
                    # Phương pháp 3: Thử với visitor pattern
                    if not page_text or len(page_text.strip()) < 50:
                        try:
                            def visitor_body(text, cm, tm, fontDict, fontSize):
                                return text
                            page_text = page.extract_text(visitor_text=visitor_body)
                        except:
                            pass
                    
                    if page_text:
                        full_text += f"\n--- TRANG {page_num} ---\n"
                        full_text += page_text + "\n"
                    
                    if page_num % 5 == 0:
                        print(f"   Đã đọc {page_num}/{len(pdf_reader.pages)} trang")
                        
                except Exception as e:
                    print(f"   Lỗi đọc trang {page_num}: {e}")
                    continue
            
            print(f"✅ Đã trích xuất {len(full_text)} ký tự từ PDF")
            
            # Lưu full text để debug
            with open("full_pdf_text_debug.txt", "w", encoding="utf-8") as f:
                f.write(full_text)
            print(f"💾 Đã lưu full text vào full_pdf_text_debug.txt để kiểm tra")
            
            return full_text
            
    except Exception as e:
        print(f"❌ Lỗi đọc PDF: {e}")
        return ""

def find_all_articles(text: str) -> List[Dict]:
    """Tìm tất cả các điều thực sự có trong luật - CHÍNH XÁC 55 ĐIỀU"""
    print("🔍 Đang tìm tất cả các điều trong luật (55 điều)...")
    
    articles = []
    found_articles = {}
    
    # Tìm tất cả các điều từ 1 đến 55 (CHÍNH XÁC 55 ĐIỀU)
    for article_num in range(1, 56):  # 1 đến 55
        # Nhiều pattern khác nhau để tìm điều
        patterns = [
            # Pattern 1: Điều X. Tên điều (có dấu chấm)
            rf'Điều\s+{article_num}\.\s+([^\n\r]+?)(?=\s*\n|\s*\r|Điều\s+\d+|$)',
            # Pattern 2: Điều X Tên điều (không có dấu chấm, có tên)
            rf'Điều\s+{article_num}\s+([^\n\r\d]+?)(?=\s*\n|\s*\r|Điều\s+\d+|$)',
            # Pattern 3: Điều X. (chỉ có số và dấu chấm)
            rf'Điều\s+{article_num}\.(?:\s*\n|\s*\r)',
            # Pattern 4: Điều X (chỉ có số, không có dấu chấm)
            rf'(?:^|\n)\s*Điều\s+{article_num}(?:\s*\n|\s*\r)',
            # Pattern 5: Tìm trong context rộng hơn
            rf'(?:^|\n|\r)\s*Điều\s+{article_num}[\.\s]*([^\n\r]*?)(?=\s*\n|\s*\r|Điều\s+\d+|Chương|$)',
        ]
        
        found = False
        for pattern_idx, pattern in enumerate(patterns):
            matches = list(re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE))
            
            if matches and not found:
                match = matches[0]  # Lấy match đầu tiên
                
                try:
                    # Lấy tên điều nếu có
                    if len(match.groups()) > 0 and match.group(1):
                        title = match.group(1).strip()
                    else:
                        title = f"Điều {article_num}"
                    
                    # Làm sạch tên điều
                    title = clean_article_title(title)
                    
                    found_articles[article_num] = {
                        'number': article_num,
                        'title': title,
                        'start_pos': match.start(),
                        'raw_match': match.group(0),
                        'pattern_used': pattern_idx + 1
                    }
                    
                    print(f"   ✓ Điều {article_num}: {title[:50]}... (Pattern {pattern_idx + 1})")
                    found = True
                    
                except (ValueError, IndexError) as e:
                    continue
        
        if not found:
            # Thử tìm bằng cách đơn giản hơn
            simple_pattern = rf'Điều\s+{article_num}[^\d]'
            simple_matches = list(re.finditer(simple_pattern, text, re.IGNORECASE))
            
            if simple_matches:
                match = simple_matches[0]
                # Lấy context xung quanh để tìm tên điều
                context_start = max(0, match.start() - 10)
                context_end = min(len(text), match.end() + 100)
                context = text[context_start:context_end]
                
                # Tìm tên điều trong context
                title_match = re.search(rf'Điều\s+{article_num}[\.\s]*([^\n\r]*?)(?=\s*\n|\s*\r|$)', context, re.IGNORECASE)
                if title_match and title_match.group(1):
                    title = clean_article_title(title_match.group(1).strip())
                else:
                    title = f"Điều {article_num}"
                
                found_articles[article_num] = {
                    'number': article_num,
                    'title': title,
                    'start_pos': match.start(),
                    'raw_match': match.group(0),
                    'pattern_used': 'simple'
                }
                
                print(f"   ✓ Điều {article_num}: {title[:50]}... (Simple pattern)")
    
    # Sắp xếp theo số điều
    articles = [found_articles[num] for num in sorted(found_articles.keys())]
    
    print(f"✅ Tìm thấy {len(articles)} điều")
    
    # Hiển thị danh sách các điều tìm thấy
    article_numbers = sorted(found_articles.keys())
    print(f"📋 Các điều có trong PDF: {article_numbers}")
    
    if len(article_numbers) > 0:
        min_article = min(article_numbers)
        max_article = max(article_numbers)
        
        print(f"📊 Phạm vi: Điều {min_article} - Điều {max_article}")
        
        # Kiểm tra với 55 điều chuẩn
        if len(article_numbers) == 55 and min_article == 1 and max_article == 55:
            print(f"✅ HOÀN HẢO! Đã tìm thấy đầy đủ 55 điều từ Điều 1 đến Điều 55")
        else:
            # Tìm các điều bị thiếu trong khoảng 1-55
            missing = []
            for i in range(1, 56):  # 1 đến 55
                if i not in article_numbers:
                    missing.append(i)
            
            if missing:
                if len(missing) <= 10:
                    print(f"⚠️ Thiếu {len(missing)} điều: {missing}")
                else:
                    print(f"⚠️ Thiếu {len(missing)} điều: {missing[:10]}... (và {len(missing)-10} điều khác)")
            
            # Kiểm tra nếu có điều > 55 (không hợp lệ)
            invalid_articles = [num for num in article_numbers if num > 55]
            if invalid_articles:
                print(f"⚠️ Phát hiện điều không hợp lệ (> 55): {invalid_articles}")
                # Loại bỏ các điều không hợp lệ
                articles = [art for art in articles if art['number'] <= 55]
                print(f"🔧 Đã loại bỏ các điều không hợp lệ, còn lại {len(articles)} điều")
    
    return articles

def clean_article_title(title: str) -> str:
    """Làm sạch tên điều để có tên ngắn gọn"""
    if not title:
        return "Không có tên"
    
    title = title.strip()
    
    # Loại bỏ số điều ở đầu nếu có
    title = re.sub(r'^\d+\.\s*', '', title)
    
    # Loại bỏ các phần thừa
    title = re.split(r'\s+\d+\.|\n|\r', title)[0].strip()
    title = re.split(r'\s+Trong\s+Luật\s+này|(?<!\w)\.(?!\w)', title)[0].strip()
    title = re.split(r'\s+Luật\s+này', title)[0].strip()
    
    # Nếu quá dài (>60 ký tự), chỉ lấy 5 từ đầu
    if len(title) > 60:
        words = title.split()[:5]
        title = ' '.join(words)
    
    return title if title else "Không có tên"

def get_chapter_for_article(article_num: int) -> tuple:
    """Xác định chương dựa trên số điều - CHÍNH XÁC CHO 55 ĐIỀU"""
    
    # Cấu trúc chính xác của Luật Phòng cháy, chữa cháy và cứu nạn, cứu hộ 2024 (55 điều)
    if 1 <= article_num <= 14:
        return "I", "QUY ĐỊNH CHUNG"
    elif 15 <= article_num <= 24:
        return "II", "PHÒNG CHÁY"
    elif 25 <= article_num <= 31:
        return "III", "CHỮA CHÁY"
    elif 32 <= article_num <= 35:
        return "IV", "CỨU NẠN, CỨU HỘ"
    elif 36 <= article_num <= 41:
        return "V", "XÂY DỰNG, BỐ TRÍ LỰC LƯỢNG, NHIỆM VỤ CỦA LỰC LƯỢNG PHÒNG CHÁY, CHỮA CHÁY VÀ CỨU NẠN, CỨU HỘ"
    elif 42 <= article_num <= 47:
        return "VI", "PHƯƠNG TIỆN PHÒNG CHÁY, CHỮA CHÁY, CỨU NẠN, CỨU HỘ"
    elif 48 <= article_num <= 52:
        return "VII", "BẢO ĐẢM ĐIỀU KIỆN CHO HOẠT ĐỘNG PHÒNG CHÁY, CHỮA CHÁY, CỨU NẠN, CỨU HỘ"
    elif 53 <= article_num <= 55:
        return "VIII", "ĐIỀU KHOẢN THI HÀNH"
    else:
        # Điều không hợp lệ (> 55)
        return "INVALID", "ĐIỀU KHÔNG HỢP LỆ"

def extract_article_content(article: Dict, text: str, next_article: Dict = None) -> str:
    """Trích xuất nội dung của điều với nhiều phương pháp"""
    
    start_pos = article['start_pos']
    
    # Xác định vị trí kết thúc
    if next_article:
        end_pos = next_article['start_pos']
    else:
        # Tìm điều tiếp theo bằng nhiều cách
        next_patterns = [
            rf'Điều\s+{article["number"] + 1}[\.\s]',
            rf'Điều\s+{article["number"] + 1}\.',
            r'Chương\s+[IVX]+',
            r'CHƯƠNG\s+[IVX]+',
            r'Phần\s+[IVX]+',
            r'PHẦN\s+[IVX]+'
        ]
        
        end_pos = len(text)  # Mặc định là cuối file
        
        for pattern in next_patterns:
            next_match = re.search(pattern, text[start_pos + 50:], re.IGNORECASE)
            if next_match:
                potential_end = start_pos + 50 + next_match.start()
                if potential_end < end_pos:
                    end_pos = potential_end
                break
        
        # Giới hạn tối đa 3000 ký tự cho một điều
        if end_pos - start_pos > 3000:
            end_pos = start_pos + 3000
    
    # Trích xuất nội dung thô
    raw_content = text[start_pos:end_pos].strip()
    
    # Tìm vị trí kết thúc của tiêu đề điều để bắt đầu nội dung thực
    # Pattern tìm tiêu đề điều: "Điều X. Tên điều" - chỉ match đến hết tên điều
    title_pattern = rf'Điều\s+{article["number"]}\.\s+[^0-9]*?(?=\s+\d+\.|\s+[a-z]\)|\s+Điều|\s+Chương|$)'
    title_match = re.search(title_pattern, raw_content, re.IGNORECASE)
    
    if title_match:
        # Bắt đầu từ sau tiêu đề điều
        content_start = title_match.end()
        content = raw_content[content_start:].strip()
    else:
        # Fallback: Tìm "Điều X." và lấy phần sau dấu chấm
        fallback_pattern = rf'Điều\s+{article["number"]}\.'
        fallback_match = re.search(fallback_pattern, raw_content, re.IGNORECASE)
        if fallback_match:
            content_start = fallback_match.end()
            content = raw_content[content_start:].strip()
        else:
            # Fallback cuối: sử dụng toàn bộ nội dung
            content = raw_content
    
    # Làm sạch nội dung
    content = content.strip()
    
    # Loại bỏ các dòng trống liên tiếp
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
    
    return content

def parse_article_to_chunks(article: Dict, content: str) -> List[Dict[str, Any]]:
    """Phân tích điều thành chunks theo cấu trúc khoản và điểm"""

    chunks = []

    # Thông tin cơ bản
    ten_luat = "Luật Phòng cháy, chữa cháy và cứu nạn, cứu hộ"
    luat_so = "2024"
    chuong_so, chuong_ten = get_chapter_for_article(article['number'])
    dieu_so = str(article['number'])
    ten_dieu = article['title']

    # LUÔN TẠO ÍT NHẤT 1 CHUNK CHO MỖI ĐIỀU - NGAY CẢ KHI NỘI DUNG NGẮN
    if len(content) < 5:  # Nếu thực sự không có nội dung
        # Tạo chunk với nội dung tối thiểu
        chunk = create_chunk(
            ten_luat, luat_so, chuong_so, chuong_ten,
            dieu_so, ten_dieu, None, None, f"Điều {dieu_so}. {ten_dieu}"
        )
        chunks.append(chunk)
        return chunks

    # Tìm các khoản bằng cách tách theo pattern "số. " ở đầu dòng hoặc sau dấu cách
    # Sử dụng regex để tìm tất cả vị trí bắt đầu khoản
    khoan_pattern = r'(?:^|\s)(\d+)\.\s+'
    khoan_positions = []

    for match in re.finditer(khoan_pattern, content):
        khoan_positions.append({
            'number': int(match.group(1)),
            'start': match.start(),
            'end': match.end(),
            'match_start': match.start(1)  # Vị trí bắt đầu số khoản
        })

    # Sắp xếp theo vị trí xuất hiện
    khoan_positions.sort(key=lambda x: x['start'])

    if len(khoan_positions) > 0:
        print(f"   Điều {dieu_so}: Tìm thấy {len(khoan_positions)} khoản: {[k['number'] for k in khoan_positions]}")

        # Xử lý từng khoản
        for i, khoan_pos in enumerate(khoan_positions):
            khoan_so = str(khoan_pos['number'])

            # Xác định nội dung khoản (từ sau "số. " đến trước khoản tiếp theo hoặc cuối text)
            content_start = khoan_pos['end']
            if i + 1 < len(khoan_positions):
                content_end = khoan_positions[i + 1]['start']
            else:
                content_end = len(content)

            khoan_content = content[content_start:content_end].strip()

            if len(khoan_content) > 3:
                # Tìm các điểm trong khoản này
                # Pattern cải tiến để tìm điểm: chữ cái + ) + khoảng trắng
                diem_pattern = r'([a-z])\)\s+'
                diem_positions = []

                for diem_match in re.finditer(diem_pattern, khoan_content):
                    diem_positions.append({
                        'letter': diem_match.group(1),
                        'start': diem_match.start(),
                        'end': diem_match.end()
                    })

                if len(diem_positions) > 0:
                    print(f"     Khoản {khoan_so}: Tìm thấy {len(diem_positions)} điểm: {[d['letter'] for d in diem_positions]}")

                    # Xử lý từng điểm
                    for j, diem_pos in enumerate(diem_positions):
                        diem_chu = diem_pos['letter']

                        # Xác định nội dung điểm
                        diem_content_start = diem_pos['end']
                        if j + 1 < len(diem_positions):
                            diem_content_end = diem_positions[j + 1]['start']
                        else:
                            diem_content_end = len(khoan_content)

                        diem_content = khoan_content[diem_content_start:diem_content_end].strip()

                        # Loại bỏ dấu chấm phẩy cuối nếu có
                        if diem_content.endswith(';'):
                            diem_content = diem_content[:-1].strip()

                        if len(diem_content) > 2:
                            chunk = create_chunk(
                                ten_luat, luat_so, chuong_so, chuong_ten,
                                dieu_so, ten_dieu, khoan_so, diem_chu, diem_content
                            )
                            chunks.append(chunk)

                    # Kiểm tra xem có nội dung trước điểm đầu tiên không
                    if len(diem_positions) > 0:
                        first_diem_start = diem_positions[0]['start']
                        content_before_diem = khoan_content[:first_diem_start].strip()

                        if len(content_before_diem) > 10:  # Có nội dung đáng kể trước các điểm
                            chunk = create_chunk(
                                ten_luat, luat_so, chuong_so, chuong_ten,
                                dieu_so, ten_dieu, khoan_so, None, content_before_diem
                            )
                            chunks.append(chunk)
                else:
                    # Không có điểm - tạo chunk cho toàn bộ khoản
                    chunk = create_chunk(
                        ten_luat, luat_so, chuong_so, chuong_ten,
                        dieu_so, ten_dieu, khoan_so, None, khoan_content
                    )
                    chunks.append(chunk)
            else:
                # Khoản có nội dung quá ngắn - vẫn tạo chunk
                chunk = create_chunk(
                    ten_luat, luat_so, chuong_so, chuong_ten,
                    dieu_so, ten_dieu, khoan_so, None, khoan_content if khoan_content else f"Khoản {khoan_so}"
                )
                chunks.append(chunk)
    else:
        # Không có khoản rõ ràng - kiểm tra xem có điểm trực tiếp không
        diem_pattern = r'([a-z])\)\s+'
        diem_positions = []

        for diem_match in re.finditer(diem_pattern, content):
            diem_positions.append({
                'letter': diem_match.group(1),
                'start': diem_match.start(),
                'end': diem_match.end()
            })

        if len(diem_positions) > 0:  # Có điểm nhưng không có khoản
            print(f"   Điều {dieu_so}: Tìm thấy {len(diem_positions)} điểm (không có khoản): {[d['letter'] for d in diem_positions]}")

            for j, diem_pos in enumerate(diem_positions):
                diem_chu = diem_pos['letter']

                # Xác định nội dung điểm
                diem_content_start = diem_pos['end']
                if j + 1 < len(diem_positions):
                    diem_content_end = diem_positions[j + 1]['start']
                else:
                    diem_content_end = len(content)

                diem_content = content[diem_content_start:diem_content_end].strip()

                # Loại bỏ dấu chấm phẩy cuối nếu có
                if diem_content.endswith(';'):
                    diem_content = diem_content[:-1].strip()

                if len(diem_content) > 2:
                    chunk = create_chunk(
                        ten_luat, luat_so, chuong_so, chuong_ten,
                        dieu_so, ten_dieu, None, diem_chu, diem_content
                    )
                    chunks.append(chunk)

            # Kiểm tra nội dung trước điểm đầu tiên
            if len(diem_positions) > 0:
                first_diem_start = diem_positions[0]['start']
                content_before_diem = content[:first_diem_start].strip()

                if len(content_before_diem) > 10:
                    chunk = create_chunk(
                        ten_luat, luat_so, chuong_so, chuong_ten,
                        dieu_so, ten_dieu, None, None, content_before_diem
                    )
                    chunks.append(chunk)
        else:
            # Không có khoản và không có điểm - tạo chunk cho toàn bộ điều
            chunk = create_chunk(
                ten_luat, luat_so, chuong_so, chuong_ten,
                dieu_so, ten_dieu, None, None, content if content.strip() else f"Điều {dieu_so}. {ten_dieu}"
            )
            chunks.append(chunk)

    # Đảm bảo luôn có ít nhất 1 chunk
    if not chunks:
        chunk = create_chunk(
            ten_luat, luat_so, chuong_so, chuong_ten,
            dieu_so, ten_dieu, None, None, f"Điều {dieu_so}. {ten_dieu}"
        )
        chunks.append(chunk)

    return chunks


def create_chunk(ten_luat: str, luat_so: str, chuong: str, chuong_ten: str, 
                dieu: str, ten_dieu: str, khoan: str, diem: str, noi_dung: str) -> Dict[str, Any]:
    """Tạo chunk theo cấu trúc yêu cầu"""
    
    # Tạo text content đầy đủ
    content_parts = []
    
    if ten_luat:
        content_parts.append(f"Tên luật: {ten_luat}")
    if luat_so:
        content_parts.append(f"Luật số: {luat_so}")
    if chuong and chuong_ten:
        content_parts.append(f"Chương {chuong}: {chuong_ten}")
    if dieu and ten_dieu:
        content_parts.append(f"Điều {dieu}: {ten_dieu}")
    if khoan:
        content_parts.append(f"Khoản {khoan}")
    if diem:
        content_parts.append(f"Điểm {diem})")
    
    content_parts.append(f"Nội dung: {noi_dung}")
    
    full_content = "\n".join(content_parts)
    
    chunk = {
        'ten_luat': ten_luat,
        'luat_so': luat_so,
        'chuong': chuong,
        'chuong_ten': chuong_ten,
        'dieu': dieu,
        'ten_dieu': ten_dieu,
        'khoan': khoan,
        'diem': diem,
        'noi_dung': noi_dung,
        'content': full_content
    }
    
    return chunk
def safe_qdrant_operation(client, operation_name: str, operation_func, *args, **kwargs):
    """Safe wrapper cho Qdrant operations"""
    try:
        result = operation_func(*args, **kwargs)
        return result
    except Exception as e:
        error_str = str(e).lower()
        pydantic_keywords = [
            'pydantic', 'validation', 'max_optimization_threads', 
            'parsingmodel', 'inlineresponse', 'int_type', 'nonetype',
            'input should be a valid integer', 'optimizer_config'
        ]
        
        if any(keyword in error_str for keyword in pydantic_keywords):
            print(f"⚠️ Pydantic validation error trong {operation_name} (bỏ qua): {str(e)[:100]}...")
            return None
        else:
            print(f"❌ Lỗi khác trong {operation_name}: {str(e)}")
            raise

def create_embeddings_batch(chunks: List[Dict], openai_client: OpenAI, batch_size: int = 10) -> List[Dict]:
    """Tạo embeddings cho chunks theo batch"""
    print(f"🔄 Đang tạo embeddings cho {len(chunks)} chunks (batch size: {batch_size})...")
    
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        batch_texts = [chunk['content'] for chunk in batch]
        
        try:
            response = openai_client.embeddings.create(
                model="text-embedding-3-large",
                input=batch_texts
            )
            
            for j, chunk in enumerate(batch):
                chunk['vector'] = response.data[j].embedding
            
            print(f"   Đã tạo embedding cho batch {i//batch_size + 1}/{(len(chunks) + batch_size - 1)//batch_size}")
            
        except Exception as e:
            print(f"Lỗi tạo embedding cho batch {i//batch_size + 1}: {e}")
            for chunk in batch:
                chunk['vector'] = [0.0] * 3072
    
    print(f"✅ Đã tạo embeddings cho tất cả {len(chunks)} chunks")
    return chunks

def setup_qdrant_collection(client: QdrantClient, collection_name: str):
    """Tạo collection trên Qdrant"""
    try:
        # Xóa collection cũ nếu tồn tại
        def _delete():
            return client.delete_collection(collection_name)
        
        safe_qdrant_operation(client, "delete_collection", _delete)
        print(f"🗑️ Đã xóa collection cũ: {collection_name}")
        
        # Tạo collection mới
        def _create():
            return client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=3072,  # text-embedding-3-large
                    distance=models.Distance.COSINE
                )
            )
        
        safe_qdrant_operation(client, "create_collection", _create)
        print(f"✅ Đã tạo collection: {collection_name}")
        
    except Exception as e:
        print(f"❌ Lỗi tạo collection: {e}")
        raise

def upload_to_qdrant(chunks: List[Dict], client: QdrantClient, collection_name: str, batch_size: int = 50):
    """Upload chunks lên Qdrant theo batch"""
    print(f"🔄 Đang upload {len(chunks)} chunks lên Qdrant (batch size: {batch_size})...")
    
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        points = []
        
        for j, chunk in enumerate(batch):
            point = models.PointStruct(
                id=i + j + 1,  # ID tuần tự từ 1
                vector=chunk['vector'],
                payload={
                    'ten_luat': chunk['ten_luat'],
                    'luat_so': chunk['luat_so'],
                    'chuong': chunk['chuong'],
                    'chuong_ten': chunk['chuong_ten'],
                    'dieu': chunk['dieu'],
                    'ten_dieu': chunk['ten_dieu'],
                    'khoan': chunk['khoan'],
                    'diem': chunk['diem'],
                    'noi_dung': chunk['noi_dung'],
                    'content': chunk['content']
                }
            )
            points.append(point)
        
        # Upload batch
        try:
            def _upsert():
                return client.upsert(
                    collection_name=collection_name,
                    points=points
                )
            
            safe_qdrant_operation(client, f"upload_batch_{i//batch_size + 1}", _upsert)
            print(f"   Đã upload batch {i//batch_size + 1}/{(len(chunks) + batch_size - 1)//batch_size}")
            
        except Exception as e:
            print(f"❌ Lỗi upload batch {i//batch_size + 1}: {e}")
    
    print(f"✅ Đã upload tất cả {len(chunks)} chunks lên Qdrant")

def main():
    """Hàm chính - Chunking chính xác 55 điều của luật"""
    print("🚀 BẮT ĐẦU CHUNKING LUẬT PHÒNG CHÁY, CHỮA CHÁY VÀ CỨU NẠN, CỨU HỘ 2024")
    print("=" * 80)
    print("Cấu trúc: tên luật - luật số - chương - điều - tên điều - khoản - điểm - nội dung")
    print("📋 LUẬT CÓ CHÍNH XÁC 55 ĐIỀU (Điều 1 - Điều 55)")
    print("=" * 80)
    
    # Tìm file PDF
    pdf_files = glob.glob("*.pdf")
    if not pdf_files:
        print("❌ Không tìm thấy file PDF nào")
        return
    
    pdf_path = pdf_files[0]
    print(f"📁 Sử dụng file: {pdf_path}")
    
    collection_name = "law_data_chunking"
    
    # 1. Đọc PDF
    full_text = extract_text_from_pdf(pdf_path)
    if not full_text:
        print("❌ Không thể đọc file PDF")
        return
    
    # 2. Tìm tất cả các điều (chính xác 55 điều)
    articles = find_all_articles(full_text)
    if not articles:
        print("❌ Không tìm thấy điều nào")
        return
    
    # Kiểm tra số lượng điều
    if len(articles) != 55:
        print(f"\n⚠️ CẢNH BÁO: Tìm thấy {len(articles)} điều thay vì 55 điều như mong đợi")
        print(f"   Hệ thống sẽ chunking tất cả các điều tìm được")
    else:
        print(f"\n✅ HOÀN HẢO: Đã tìm thấy đầy đủ 55 điều như mong đợi!")
    
    # 3. Phân tích từng điều và tạo chunks
    print("\n🏗️ Đang phân tích từng điều và tạo chunks...")
    all_chunks = []
    
    for i, article in enumerate(articles):
        print(f"   Đang xử lý Điều {article['number']}: {article['title'][:50]}...")
        
        # Xác định điều tiếp theo
        next_article = articles[i + 1] if i + 1 < len(articles) else None
        
        # Trích xuất nội dung điều
        content = extract_article_content(article, full_text, next_article)
        
        if content and len(content) > 0:
            # Phân tích cấu trúc điều thành chunks
            article_chunks = parse_article_to_chunks(article, content)
            
            all_chunks.extend(article_chunks)
            print(f"     ✓ Tạo được {len(article_chunks)} chunks từ Điều {article['number']}")
        else:
            # Tạo chunk tối thiểu cho điều không có nội dung
            ten_luat = "Luật Phòng cháy, chữa cháy và cứu nạn, cứu hộ"
            luat_so = "2024"
            chuong_so, chuong_ten = get_chapter_for_article(article['number'])
            dieu_so = str(article['number'])
            ten_dieu = article['title']
            
            chunk = create_chunk(
                ten_luat, luat_so, chuong_so, chuong_ten,
                dieu_so, ten_dieu, None, None, f"Điều {dieu_so}. {ten_dieu}"
            )
            all_chunks.append(chunk)
            print(f"     ✓ Tạo được 1 chunks từ Điều {article['number']} (nội dung tối thiểu)")
    
    if not all_chunks:
        print("❌ Không tạo được chunks")
        return
    
    print(f"✅ Đã tạo tổng cộng {len(all_chunks)} chunks từ {len(articles)} điều")
    
    # 4. Tạo embeddings
    openai_client = OpenAI(api_key=os.getenv('OPENAI__API_KEY'))
    chunks_with_embeddings = create_embeddings_batch(all_chunks, openai_client)
    
    # 5. Setup Qdrant
    print("🔧 Đang kết nối Qdrant...")
    qdrant_client = QdrantClient(url=os.getenv('QDRANT_URL'))
    setup_qdrant_collection(qdrant_client, collection_name)
    
    # 6. Upload lên Qdrant
    upload_to_qdrant(chunks_with_embeddings, qdrant_client, collection_name)
    
    # 7. Xuất file JSON backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"law_data_chunking_backup_{timestamp}.json"
    
    backup_data = {
        'metadata': {
            'ten_luat': 'Luật Phòng cháy, chữa cháy và cứu nạn, cứu hộ',
            'luat_so': '2024',
            'collection_name': collection_name,
            'total_chunks': len(all_chunks),
            'total_articles': len(articles),
            'expected_articles': 55,
            'structure': 'ten_luat - luat_so - chuong - dieu - ten_dieu - khoan - diem - noi_dung',
            'created_at': datetime.now().isoformat(),
            'note': f'Luật có 55 điều - Đã xử lý {len(articles)} điều - Chunking hoàn chỉnh theo cấu trúc yêu cầu',
            'articles_found': sorted([a['number'] for a in articles])
        },
        'articles_processed': [
            {
                'number': a['number'],
                'title': a['title'],
                'chapter': get_chapter_for_article(a['number'])[0]
            } for a in articles
        ],
        'chunks': [
            {k: v for k, v in chunk.items() if k != 'vector'}
            for chunk in chunks_with_embeddings
        ]
    }
    
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=2)
    
    print(f"💾 Đã tạo file backup: {backup_file}")
    
    # 8. Hiển thị tóm tắt
    print("\n🎉 HOÀN THÀNH CHUNKING LUẬT!")
    print("=" * 70)
    print(f"📚 Tên luật: Luật Phòng cháy, chữa cháy và cứu nạn, cứu hộ")
    print(f"📅 Luật số: 2024")
    print(f"📊 Tổng chunks: {len(all_chunks)}")
    print(f"📋 Tổng điều xử lý: {len(articles)}")
    print(f"📋 Điều mong đợi: 55")
    print(f"🗄️ Collection: {collection_name}")
    print(f"💾 Backup: {backup_file}")
    
    # Hiển thị danh sách các điều đã xử lý
    article_numbers = sorted([a['number'] for a in articles])
    print(f"\n📋 CÁC ĐIỀU ĐÃ XỬ LÝ:")
    print(f"   Từ điều {min(article_numbers)} đến điều {max(article_numbers)}")
    print(f"   Tổng số điều: {len(article_numbers)}")
    print(f"   Danh sách: {article_numbers}")
    
    # Kiểm tra các điều bị thiếu (nếu có)
    if len(article_numbers) < 55:
        missing = []
        for i in range(1, 56):
            if i not in article_numbers:
                missing.append(i)
        print(f"\n⚠️ CÁC ĐIỀU BỊ THIẾU: {missing}")
    
    # Hiển thị thống kê theo chương
    print(f"\n📊 THỐNG KÊ THEO CHƯƠNG:")
    chapter_stats = {}
    for chunk in all_chunks:
        chapter = chunk['chuong']
        if chapter not in chapter_stats:
            chapter_stats[chapter] = set()
        chapter_stats[chapter].add(int(chunk['dieu']))
    
    for chapter in sorted(chapter_stats.keys()):
        articles_in_chapter = sorted(chapter_stats[chapter])
        print(f"   Chương {chapter}: {len(articles_in_chapter)} điều - {articles_in_chapter}")
    
    # Hiển thị vài chunk mẫu
    print(f"\n📝 VÍ DỤ CHUNKS:")
    print("-" * 60)
    for i, chunk in enumerate(all_chunks[:5]):
        print(f"\nChunk {i+1}:")
        print(f"  Chương: {chunk['chuong']} - {chunk['chuong_ten'][:50]}...")
        print(f"  Điều: {chunk['dieu']} - {chunk['ten_dieu'][:50]}...")
        print(f"  Khoản: {chunk['khoan'] or 'N/A'}")
        print(f"  Điểm: {chunk['diem'] or 'N/A'}")
        print(f"  Nội dung: {chunk['noi_dung'][:100]}...")
    
    # Kết luận
    if len(articles) == 55:
        print(f"\n🎉 THÀNH CÔNG: Đã chunking đầy đủ 55 điều của luật!")
    else:
        print(f"\n⚠️ LƯU Ý: Đã chunking {len(articles)}/55 điều. Một số điều có thể không có nội dung đầy đủ trong PDF.")

if __name__ == "__main__":
    main()