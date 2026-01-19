# 新存储结构部署指南

## 快速开始

新的存储结构（v2.0）已经就绪，可以立即使用。有两种部署方式：

---

## 方式 1: 使用现有数据（自动迁移）✨ 推荐

如果你想保留现有的对话历史：

### 步骤 1: 确保数据目录可写

```bash
# 检查目录权限
ls -la ~/.claude-lark/

# 如果文件属于 root，修改所有者
sudo chown -R $USER:$USER ~/.claude-lark/
```

### 步骤 2: 启动机器人

```bash
# 使用 Docker Compose
docker-compose up -d

# 或直接运行
python main.py
```

### 步骤 3: 观察迁移日志

首次启动时会看到：

```
🔄 检测到旧格式数据，开始迁移...
✅ 已备份旧数据到: ~/.claude-lark/session_mapping.json.backup
📊 迁移完成: 5 个会话, 26 条消息 -> 19 条消息
📦 内存缓存已构建: 18 条消息映射
```

✅ 完成！旧数据已自动迁移，对话历史保留。

---

## 方式 2: 全新开始（推荐）⭐

如果不需要保留旧数据，使用全新的存储：

### 步骤 1: 更新配置

编辑 `.env` 文件：

```bash
# 使用新的存储目录
LOCAL_SESSION_DIR=~/.claude-lark-new
```

或者使用默认目录但清空数据：

```bash
# 删除旧数据（如果有权限）
rm -f ~/.claude-lark/session_mapping.json*

# 或者使用 sudo
sudo rm -f ~/.claude-lark/session_mapping.json*
```

### 步骤 2: 启动机器人

```bash
# 使用 Docker Compose
docker-compose up -d

# 或直接运行
python main.py
```

### 步骤 3: 验证

首次启动时会看到：

```
📁 会话映射文件不存在，将创建新文件
📦 内存缓存已构建: 0 条消息映射
✅ 机器人启动完成！
```

✅ 完成！使用全新的 v2.0 存储结构。

---

## Docker Compose 部署

### 完整配置

```yaml
# docker-compose.yml
version: '3.8'

services:
  claude-agent-http:
    # 从 GitHub 仓库构建，或使用你自己的镜像
    # GitHub: https://github.com/lflish/claude-agent-http
    image: claude-agent-http:latest
    build:
      context: ../claude-agent-http
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      - ./sessions:/app/sessions
    ports:
      - "8000:8000"

  claude-bot:
    build: .
    environment:
      - APP_ID=${APP_ID}
      - APP_SECRET=${APP_SECRET}
      - CLAUDE_AGENT_URL=http://claude-agent-http:8000
    volumes:
      - ${LOCAL_SESSION_DIR:-~/.claude-lark}:/data/claude-lark
    depends_on:
      - claude-agent-http
```

### 启动服务

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f claude-bot

# 重启服务
docker-compose restart claude-bot

# 停止服务
docker-compose down
```

---

## 验证部署

### 1. 检查存储文件

```bash
# 查看存储文件
cat ~/.claude-lark/session_mapping.json | python -m json.tool

# 应该看到 v2.0 格式：
{
  "version": "2.0",
  "sessions": {
    "session_id": {
      "root_id": "om_xxx",
      "recent": ["om_yyy", "om_zzz"]
    }
  }
}
```

### 2. 发送测试消息

在飞书中：
1. 私聊机器人，发送 "你好"
2. 回复刚才的消息，发送 "测试上下文"
3. 检查机器人是否能记住上下文

### 3. 查看会话数据

```bash
# 检查会话数
python -c "
import os, json, sys
os.environ['SESSION_STORE_DIR'] = os.path.expanduser('~/.claude-lark')
sys.path.insert(0, '.')
from handle import init_session_store, get_session_count
init_session_store()
print(f'当前会话数: {get_session_count()}')
"
```

---

## 监控和维护

### 查看日志

```bash
# Docker 日志
docker-compose logs -f claude-bot

# 或直接运行的日志
tail -f /var/log/claude-bot.log
```

### 清理旧会话

会话会自动清理（LRU，最多保留 1000 个），无需手动维护。

### 备份数据

```bash
# 定期备份会话数据
cp ~/.claude-lark/session_mapping.json \
   ~/.claude-lark/backup_$(date +%Y%m%d).json
```

---

## 故障排除

### 权限问题

```bash
# 错误: Permission denied
# 解决: 修改目录权限
sudo chown -R $USER:$USER ~/.claude-lark/
chmod 755 ~/.claude-lark/
```

### 迁移失败

```bash
# 如果迁移出错，恢复备份
cp ~/.claude-lark/session_mapping.json.backup \
   ~/.claude-lark/session_mapping.json
```

### 上下文丢失

检查存储结构：
```bash
# 查看 root_id 是否正确
cat ~/.claude-lark/session_mapping.json | grep -A 5 "session_id"
```

---

## 性能优化建议

### 1. 存储位置

建议使用 SSD 存储会话数据，提升读写速度。

### 2. 缓存预热

如果有大量会话（>100），首次启动可能需要几秒钟构建缓存。

### 3. 定期清理

虽然有自动 LRU 清理，但如果磁盘空间紧张，可以手动清理：

```bash
# 只保留最近 500 个会话
python -c "
import os, json
os.environ['SESSION_STORE_DIR'] = os.path.expanduser('~/.claude-lark')
# ... 清理逻辑 ...
"
```

---

## 回滚到旧版本

如果需要回滚到旧的存储格式：

1. 恢复旧代码：
```bash
git checkout <old-commit>
```

2. 恢复旧数据：
```bash
cp ~/.claude-lark/session_mapping.json.backup \
   ~/.claude-lark/session_mapping.json
```

3. 重启服务：
```bash
docker-compose restart claude-bot
```

---

## 总结

✅ 新存储结构已就绪  
✅ 自动迁移功能完善  
✅ 性能提升显著  
✅ 向后兼容保证  

立即部署，享受更高效的存储和更快的查询速度！🚀

---

*更新时间: 2026-01-18*  
*版本: v2.0*
