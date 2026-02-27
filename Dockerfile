
FROM python:3.11.4

# 2. Thiết lập thư mục làm việc
WORKDIR /app

# 3. Cài đặt các thư viện hệ thống cần thiết (nếu có dùng OpenCV hoặc các thư viện C)

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 4. Copy file requirements trước để tận dụng Docker Cache
COPY requirements.txt .

# 5. Nâng cấp pip và cài đặt dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 6. Copy toàn bộ mã nguồn vào container
# Docker sẽ tự động loại bỏ các file đã liệt kê trong .dockerignore
COPY . .

# 7. Thiết lập biến môi trường (Tùy chọn)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 8. Mở cổng 8000 cho ứng dụng
EXPOSE 8000

# 9. Lệnh chạy ứng dụng
CMD ["python", "main.py"]