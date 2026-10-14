FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# تثبيت أدوات rclone و megatools للتوسع التلقائي وإنشاء حسابات السحابة في الخلفية
RUN apt-get update && apt-get install -y --no-install-recommends \
    rclone \
    megatools \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python3", "run.py", "--host", "0.0.0.0", "--port", "8000", "--no-browser"]
