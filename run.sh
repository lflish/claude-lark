#!/bin/bash

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

echo "启动 Claude 飞书机器人..."
echo "  APP_ID: ${APP_ID:0:10}..."
echo "  CLAUDE_AGENT_URL: ${CLAUDE_AGENT_URL}"
echo "  容器内路径: ${CONTAINER_SESSION_DIR}"
echo "  宿主机路径: ${LOCAL_SESSION_DIR}"

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
  claude-bot:latest

echo "容器已启动，查看日志: docker logs -f claude-bot"
