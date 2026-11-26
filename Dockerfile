FROM python:3.10-slim

# 让 GHCR 上的镜像能指回仓库(否则 package 页面是孤立的)
LABEL org.opencontainers.image.source="https://github.com/wushiyi105-jpg/jiadian"
LABEL org.opencontainers.image.description="家电 · 报修诊断:先自查,再估价,决定修还是换"

WORKDIR /app

COPY . .

RUN pip install -e .

EXPOSE 8000

CMD ["python", "-m", "jiadian", "web", "--host", "0.0.0.0"]
