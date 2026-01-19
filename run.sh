#!/bin/bash

# 读取版本号
if [ -f VERSION ]; then
  VERSION=$(cat VERSION | tr -d '[:space:]')
  DEFAULT_TAG="v${VERSION}"
else
  DEFAULT_TAG="latest"
fi

# 支持通过参数指定镜像标签
IMAGE_TAG=${1:-$DEFAULT_TAG}
IMAGE_NAME="claude-bot"

# 加载 .env 文件中的环境变量
if [ -f .env ]; then
  echo "正在加载 .env 文件..."
  export $(grep -v '^#' .env | xargs)
else
  echo "警告: .env 文件不存在，使用默认配置"
fi

# 停止并删除旧容器
docker stop claude-bot 2>/dev/null
docker rm claude-bot 2>/dev/null

# 飞书应用配置（如果 .env 中未设置，则使用默认值）
export APP_ID=${APP_ID:-"cli_xxxxx"}
export APP_SECRET=${APP_SECRET:-"xxxxx"}

# Claude Agent HTTP 后端配置
export CLAUDE_AGENT_URL=${CLAUDE_AGENT_URL:-"http://localhost:8000"}
export CLAUDE_AGENT_TIMEOUT=${CLAUDE_AGENT_TIMEOUT:-120}

# 会话映射存储目录
# 容器内固定路径
CONTAINER_SESSION_DIR="/data/claude-lark"
# 宿主机路径（可在 .env 中配置）
LOCAL_SESSION_DIR=${LOCAL_SESSION_DIR:-"~/.claude-lark"}

# 展开波浪号
LOCAL_SESSION_DIR="${LOCAL_SESSION_DIR/#\~/$HOME}"

# 确保本地存储目录存在
mkdir -p ${LOCAL_SESSION_DIR}

echo "=========================================="
echo "启动 Claude 飞书机器人"
echo "=========================================="
echo "  镜像: ${IMAGE_NAME}:${IMAGE_TAG}"
echo "  APP_ID: ${APP_ID:0:10}..."
echo "  CLAUDE_AGENT_URL: ${CLAUDE_AGENT_URL}"
echo "  容器内路径: ${CONTAINER_SESSION_DIR}"
echo "  宿主机路径: ${LOCAL_SESSION_DIR}"
echo "=========================================="
echo ""

# 检查镜像是否存在
if ! docker images ${IMAGE_NAME}:${IMAGE_TAG} | grep -q ${IMAGE_TAG}; then
  echo "❌ 错误: 镜像 ${IMAGE_NAME}:${IMAGE_TAG} 不存在"
  echo "请先运行: ./build.sh"
  exit 1
fi

docker run -d \
  --name claude-bot \
  --network host \
  -e APP_ID=${APP_ID} \
  -e APP_SECRET=${APP_SECRET} \
  -e CLAUDE_AGENT_URL=${CLAUDE_AGENT_URL} \
  -e CLAUDE_AGENT_TIMEOUT=${CLAUDE_AGENT_TIMEOUT} \
  -e SESSION_STORE_DIR=${CONTAINER_SESSION_DIR} \
  -v ${LOCAL_SESSION_DIR}:${CONTAINER_SESSION_DIR} \
  --restart unless-stopped \
  ${IMAGE_NAME}:${IMAGE_TAG}

if [ $? -eq 0 ]; then
  echo ""
  echo "✅ 容器启动成功！"
  echo ""
  echo "查看日志: docker logs -f claude-bot"
  echo "停止容器: docker stop claude-bot"
else
  echo ""
  echo "❌ 容器启动失败"
  exit 1
fi
