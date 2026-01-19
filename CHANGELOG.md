# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- 🐛 优化会话映射存储：避免重复保存相同的 message_id -> session_id 映射
- 🐛 减少不必要的文件 I/O 操作，提升性能

### Added
- 📖 添加详细的网络配置故障排查指南（Connection refused 问题）
- 📝 在 env.example 中添加 Docker Compose vs run.sh 的 URL 配置说明

### Changed
- ♻️ `save_session_mapping()` 函数：检查映射是否已存在，相同映射只更新 LRU 顺序不保存文件

## [0.3.0] - 2026-01-12

### Fixed
- Docker 卷挂载逻辑：外部路径可配置，内部路径固定
- `run.sh` 自动加载 `.env` 文件功能
- 修正挂载方向：宿主机路径:容器路径

### Changed
- 容器内路径从 `/tmp/lark` 改为 `/data/claude-lark`
- 宿主机路径通过 `LOCAL_SESSION_DIR` 环境变量配置（默认 `~/.claude-lark`）

### Added
- 添加 `LOCAL_SESSION_DIR` 配置项到 `.env` 文件
- 支持波浪号 `~` 自动展开为用户主目录

## [0.2.0] - 2026-01-12

### Changed
- 升级 Docker 基础镜像从 `python:3.11-slim` 到 `python:3.12-slim`

## [0.1.1] - 2026-01-12

### Added
- 添加 MIT License 文件
- 美化 README.md 文档格式

## [0.1.0] - 2026-01-12

### Added
- 初始版本发布
- 集成 Claude AI 的智能飞书机器人
- 支持私聊和群聊（@机器人触发）
- 多轮对话上下文记忆（会话管理）
- 异步消息处理队列（防止重复消息）
- WebSocket 长连接模式
- Docker 和 Docker Compose 部署支持
- 添加 CLAUDE.md 开发指南

### Technical Features
- 基于 `lark-oapi` SDK 实现飞书集成
- 使用 `claude-agent-http` 后端服务
- Session 映射存储（LRU 缓存，最大 1000 个会话）
- 消息重试机制（最多 3 次，指数退避）
- 后端服务健康检查

[Unreleased]: https://github.com/lflish/claude-lark/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/lflish/claude-lark/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/lflish/claude-lark/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/lflish/claude-lark/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/lflish/claude-lark/releases/tag/v0.1.0
