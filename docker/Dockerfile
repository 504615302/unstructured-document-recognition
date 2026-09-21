# 基于官方 Python 3.10 镜像
FROM python:3.10.19-slim

# 安装 LibreOffice（soffice）
RUN apt-get update && apt-get install -y libreoffice && apt-get clean

# 如果有 requirements.txt，可以改为：
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple