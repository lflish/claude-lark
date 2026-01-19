#!/bin/bash

# 读取版本号
if [ -f VERSION ]; then
  VERSION=$(cat VERSION | tr -d '[:space:]')
else
  echo "错误: VERSION 文件不存在"
  exit 1
fi

# 生成时间戳 (格式: YYYYMMDD)
TIMESTAMP=$(date +%Y%m%d)

# 镜像名称
IMAGE_NAME="claude-bot"

# 构建标签
VERSION_TAG="v${VERSION}"
VERSION_TIME_TAG="v${VERSION}-${TIMESTAMP}"

echo "=========================================="
echo "构建 Claude 飞书机器人 Docker 镜像"
echo "=========================================="
echo "版本: ${VERSION}"
echo "时间戳: ${TIMESTAMP}"
echo ""
echo "将创建以下标签:"
echo "  - ${IMAGE_NAME}:${VERSION_TAG}"
echo "  - ${IMAGE_NAME}:${VERSION_TIME_TAG}"
echo "  - ${IMAGE_NAME}:latest"
echo "=========================================="
echo ""

# 构建镜像并打上多个标签
docker build \
  -t ${IMAGE_NAME}:${VERSION_TAG} \
  -t ${IMAGE_NAME}:${VERSION_TIME_TAG} \
  -t ${IMAGE_NAME}:latest \
  .

if [ $? -eq 0 ]; then
  echo ""
  echo "=========================================="
  echo "✅ 构建成功！"
  echo "=========================================="
  echo "镜像标签:"
  echo "  - ${IMAGE_NAME}:${VERSION_TAG}"
  echo "  - ${IMAGE_NAME}:${VERSION_TIME_TAG}"
  echo "  - ${IMAGE_NAME}:latest"
  echo ""
  echo "查看镜像: docker images ${IMAGE_NAME}"
  echo "运行容器: ./run.sh"
else
  echo ""
  echo "❌ 构建失败"
  exit 1
fi
