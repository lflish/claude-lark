# 使用 Python 3.12 作为基础镜像
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 复制依赖文件
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY main.py .
COPY handle.py .

# 暴露端口（如果需要健康检查）
# EXPOSE 8080

# 设置健康检查（可选）
# HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
#   CMD python -c "import sys; sys.exit(0)"

# 启动应用
CMD ["python", "-u", "main.py"]

