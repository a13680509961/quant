# 量化工作台 Docker 镜像（根目录版：供 Koyeb/HF Spaces 等平台自动识别）
# 构建：docker build -t quant-studio .
# 运行：docker run -d -p 8000:8000 --name quant-studio --restart=always quant-studio
FROM python:3.12-slim

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir numpy pandas

EXPOSE 8000
CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "8000", "--no-browser"]
