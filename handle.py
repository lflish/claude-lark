"""Claude Agent HTTP 客户端封装模块"""

import os
import json
import requests
from threading import Lock
from typing import Optional
from pathlib import Path

# HTTP 后端配置
CLAUDE_AGENT_URL = os.getenv("CLAUDE_AGENT_URL", "http://localhost:8000")
CLAUDE_AGENT_TIMEOUT = int(os.getenv("CLAUDE_AGENT_TIMEOUT", "120"))

# 会话映射存储配置
SESSION_STORE_DIR = os.getenv("SESSION_STORE_DIR", "/tmp/lark")
SESSION_STORE_FILE = os.path.join(SESSION_STORE_DIR, "session_mapping.json")
_MAX_SESSIONS = 1000  # 最多保存1000个会话
STORAGE_VERSION = "2.0"  # 存储格式版本号
_MAX_RECENT_MESSAGES = 3  # 每个会话保留的最近消息数

# 新的会话存储结构
# {
#   "version": "2.0",
#   "sessions": {
#     "session_id": {
#       "root_id": "om_xxx",
#       "recent": ["om_yyy", "om_zzz"]
#     }
#   }
# }
_session_store: dict = {"version": STORAGE_VERSION, "sessions": {}}
_message_to_session_cache: dict = {}  # 内存缓存: message_id -> session_id
_session_lock = Lock()
_initialized = False


def _ensure_store_dir():
    """确保存储目录存在"""
    Path(SESSION_STORE_DIR).mkdir(parents=True, exist_ok=True)


def _migrate_old_format(old_data: dict) -> dict:
    """
    迁移旧格式到新格式
    旧格式: {"mappings": [["msg_id", "session_id"], ...]}
    新格式: {"version": "2.0", "sessions": {...}}
    """
    print("🔄 检测到旧格式数据，开始迁移...")

    # 备份旧文件
    backup_file = SESSION_STORE_FILE + ".backup"
    try:
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(old_data, f, ensure_ascii=False, indent=2)
        print(f"✅ 已备份旧数据到: {backup_file}")
    except Exception as e:
        print(f"⚠️ 备份失败: {str(e)}")

    # 转换数据结构
    new_store = {"version": STORAGE_VERSION, "sessions": {}}
    mappings = old_data.get('mappings', [])

    # 按 session_id 分组
    session_messages = {}
    for msg_id, sess_id in mappings:
        if sess_id not in session_messages:
            session_messages[sess_id] = []
        session_messages[sess_id].append(msg_id)

    # 构建新格式
    for sess_id, msg_ids in session_messages.items():
        # 第一条消息作为 root_id（保守策略）
        root_id = msg_ids[0] if msg_ids else None
        # 最后3条作为 recent
        recent = msg_ids[-_MAX_RECENT_MESSAGES:] if len(msg_ids) > 0 else []

        new_store["sessions"][sess_id] = {
            "root_id": root_id,
            "recent": recent
        }

    total_sessions = len(new_store["sessions"])
    total_messages = sum(len(msgs) for msgs in session_messages.values())
    saved_messages = sum(
        1 + len(s["recent"]) for s in new_store["sessions"].values()
    )
    print(f"📊 迁移完成: {total_sessions} 个会话, "
          f"{total_messages} 条消息 -> {saved_messages} 条消息")

    return new_store


def _rebuild_cache():
    """重建内存缓存"""
    global _message_to_session_cache
    _message_to_session_cache.clear()

    sessions = _session_store.get("sessions", {})
    for session_id, session_data in sessions.items():
        # 缓存 root_id
        root_id = session_data.get("root_id")
        if root_id:
            _message_to_session_cache[root_id] = session_id

        # 缓存 recent 消息
        recent = session_data.get("recent", [])
        for msg_id in recent:
            _message_to_session_cache[msg_id] = session_id


def _load_session_store():
    """从文件加载会话映射"""
    global _session_store, _initialized

    if _initialized:
        return

    _ensure_store_dir()

    try:
        if os.path.exists(SESSION_STORE_FILE):
            with open(SESSION_STORE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 检测格式版本
            if 'version' in data and data['version'] == STORAGE_VERSION:
                # 新格式
                _session_store = data
                session_count = len(_session_store.get("sessions", {}))
                print(f"✅ 已加载 {session_count} 个会话 (v{STORAGE_VERSION})")
            elif 'mappings' in data:
                # 旧格式，需要迁移
                _session_store = _migrate_old_format(data)
                # 迁移后立即保存
                _save_session_store()
            else:
                # 未知格式
                print("⚠️ 未知的存储格式，使用新格式")
                _session_store = {"version": STORAGE_VERSION, "sessions": {}}
        else:
            print("📁 会话映射文件不存在，将创建新文件")
            _session_store = {"version": STORAGE_VERSION, "sessions": {}}

    except Exception as e:
        print(f"⚠️ 加载会话映射失败: {str(e)}，使用空映射")
        _session_store = {"version": STORAGE_VERSION, "sessions": {}}

    # 构建内存缓存
    _rebuild_cache()
    cache_size = len(_message_to_session_cache)
    print(f"📦 内存缓存已构建: {cache_size} 条消息映射")

    _initialized = True


def _save_session_store():
    """保存会话映射到文件"""
    _ensure_store_dir()

    try:
        with open(SESSION_STORE_FILE, 'w', encoding='utf-8') as f:
            json.dump(_session_store, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 保存会话映射失败: {str(e)}")


def _add_recent_message(session_id: str, message_id: str):
    """
    添加消息到 recent 数组，保持最多 _MAX_RECENT_MESSAGES 条

    Args:
        session_id: 会话ID
        message_id: 消息ID
    """
    sessions = _session_store.get("sessions", {})

    if session_id not in sessions:
        sessions[session_id] = {"root_id": None, "recent": []}

    recent = sessions[session_id].get("recent", [])

    # 如果消息已存在，移到末尾
    if message_id in recent:
        recent.remove(message_id)
        recent.append(message_id)
    else:
        # 添加到末尾
        recent.append(message_id)
        # 保持最多 N 条
        if len(recent) > _MAX_RECENT_MESSAGES:
            recent.pop(0)

    sessions[session_id]["recent"] = recent
    _session_store["sessions"] = sessions

    # 更新内存缓存
    _message_to_session_cache[message_id] = session_id


def _set_root_id(session_id: str, root_id: str):
    """
    设置会话的 root_id

    Args:
        session_id: 会话ID
        root_id: 根消息ID
    """
    sessions = _session_store.get("sessions", {})

    if session_id not in sessions:
        sessions[session_id] = {"root_id": root_id, "recent": []}
    else:
        sessions[session_id]["root_id"] = root_id

    _session_store["sessions"] = sessions

    # 更新内存缓存
    _message_to_session_cache[root_id] = session_id


def _cleanup_old_sessions():
    """清理过期的会话，保持最多 _MAX_SESSIONS 个"""
    sessions = _session_store.get("sessions", {})

    if len(sessions) <= _MAX_SESSIONS:
        return

    # 简单策略：删除最旧的会话（按session_id排序）
    session_ids = sorted(sessions.keys())
    to_remove = len(sessions) - _MAX_SESSIONS

    for i in range(to_remove):
        sess_id = session_ids[i]
        session_data = sessions[sess_id]

        # 从缓存中删除相关消息
        root_id = session_data.get("root_id")
        if root_id and root_id in _message_to_session_cache:
            del _message_to_session_cache[root_id]

        for msg_id in session_data.get("recent", []):
            if msg_id in _message_to_session_cache:
                del _message_to_session_cache[msg_id]

        # 删除会话
        del sessions[sess_id]

        # 尝试关闭后端会话
        try:
            client = get_client()
            client.close_session(sess_id)
        except Exception:
            pass

    _session_store["sessions"] = sessions
    print(f"🧹 已清理 {to_remove} 个旧会话")


class ClaudeAgentClient:
    """Claude Agent HTTP 客户端"""

    def __init__(self, base_url: str = None, timeout: int = None):
        self.base_url = (base_url or CLAUDE_AGENT_URL).rstrip('/')
        self.timeout = timeout or CLAUDE_AGENT_TIMEOUT
        self.session = requests.Session()

    def create_session(self, user_id: str, subdir: str = None,
                       metadata: dict = None) -> dict:
        """
        创建新会话

        Args:
            user_id: 用户ID
            subdir: 子目录（可选）
            metadata: 自定义元数据（可选）

        Returns:
            dict: 会话信息
        """
        url = f"{self.base_url}/api/v1/sessions"
        payload = {"user_id": user_id}

        if subdir:
            payload["subdir"] = subdir
        if metadata:
            payload["metadata"] = metadata

        try:
            response = self.session.post(
                url, json=payload, timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"创建会话失败: {str(e)}")

    def get_session(self, session_id: str) -> dict:
        """
        获取会话信息

        Args:
            session_id: 会话ID

        Returns:
            dict: 会话信息
        """
        url = f"{self.base_url}/api/v1/sessions/{session_id}"

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"获取会话失败: {str(e)}")

    def resume_session(self, session_id: str) -> dict:
        """
        恢复会话

        Args:
            session_id: 会话ID

        Returns:
            dict: 会话信息
        """
        url = f"{self.base_url}/api/v1/sessions/{session_id}/resume"

        try:
            response = self.session.post(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"恢复会话失败: {str(e)}")

    def close_session(self, session_id: str) -> bool:
        """
        关闭会话

        Args:
            session_id: 会话ID

        Returns:
            bool: 是否成功
        """
        url = f"{self.base_url}/api/v1/sessions/{session_id}"

        try:
            response = self.session.delete(url, timeout=self.timeout)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            print(f"关闭会话失败: {str(e)}")
            return False

    def chat(self, session_id: str, message: str) -> dict:
        """
        发送消息（同步）

        Args:
            session_id: 会话ID
            message: 用户消息

        Returns:
            dict: 回复信息
        """
        url = f"{self.base_url}/api/v1/chat"
        payload = {
            "session_id": session_id,
            "message": message
        }

        try:
            response = self.session.post(
                url, json=payload, timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"发送消息失败: {str(e)}")

    def chat_stream(self, session_id: str, message: str):
        """
        发送消息（流式）

        Args:
            session_id: 会话ID
            message: 用户消息

        Yields:
            dict: SSE 事件
        """
        url = f"{self.base_url}/api/v1/chat/stream"
        payload = {
            "session_id": session_id,
            "message": message
        }

        try:
            response = self.session.post(
                url,
                json=payload,
                timeout=self.timeout,
                stream=True
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        yield data
        except requests.exceptions.RequestException as e:
            raise Exception(f"流式发送消息失败: {str(e)}")

    def health_check(self) -> bool:
        """
        健康检查

        Returns:
            bool: 服务是否健康
        """
        url = f"{self.base_url}/health"

        try:
            response = self.session.get(url, timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False


# 全局客户端实例
_client: Optional[ClaudeAgentClient] = None


def get_client() -> ClaudeAgentClient:
    """获取全局客户端实例"""
    global _client
    if _client is None:
        _client = ClaudeAgentClient()
    return _client


def init_session_store():
    """初始化会话存储（程序启动时调用）"""
    _load_session_store()


def get_or_create_session(message_id: str, user_id: str) -> str:
    """
    获取或创建会话（已废弃，保留用于兼容性）

    建议使用 get_session_id() 和 save_session_mapping() 代替

    Args:
        message_id: 飞书消息ID（用于关联会话）
        user_id: 用户ID

    Returns:
        str: claude-agent-http 的 session_id
    """
    _load_session_store()

    # 尝试从缓存获取
    session_id = get_session_id(message_id)

    if session_id:
        # 检查会话是否仍然有效
        try:
            client = get_client()
            client.get_session(session_id)
            return session_id
        except Exception:
            # 会话已失效，将创建新会话
            pass

    # 创建新会话
    client = get_client()
    session_info = client.create_session(user_id=user_id)
    session_id = session_info["session_id"]

    # 保存映射
    save_session_mapping(message_id, session_id, is_root=True)

    return session_id


def link_session(new_message_id: str,
                 parent_message_id: str) -> Optional[str]:
    """
    将新消息链接到父消息的会话（已废弃，保留用于兼容性）

    建议使用 get_session_id() 和 save_session_mapping() 代替

    Args:
        new_message_id: 新消息ID
        parent_message_id: 父消息ID

    Returns:
        str: 关联的 session_id，如果没有则返回 None
    """
    _load_session_store()

    session_id = get_session_id(parent_message_id)
    if session_id:
        save_session_mapping(new_message_id, session_id, is_root=False)
        return session_id

    return None


def get_session_id(message_id: str) -> Optional[str]:
    """
    获取消息关联的会话ID

    Args:
        message_id: 飞书消息ID

    Returns:
        str: session_id，如果没有则返回 None
    """
    _load_session_store()

    with _session_lock:
        # 优先从内存缓存查找
        if message_id in _message_to_session_cache:
            return _message_to_session_cache[message_id]

    return None


def save_session_mapping(message_id: str, session_id: str,
                         is_root: bool = False) -> None:
    """
    保存消息ID与会话ID的映射

    Args:
        message_id: 飞书消息ID
        session_id: claude-agent-http 的 session_id
        is_root: 是否为 root_id（对话根消息）
    """
    _load_session_store()

    with _session_lock:
        # 检查是否已经在缓存中
        existing_session = _message_to_session_cache.get(message_id)

        if existing_session == session_id and not is_root:
            # 映射已存在且相同，跳过
            return

        # 更新会话数据
        if is_root:
            _set_root_id(session_id, message_id)
        else:
            _add_recent_message(session_id, message_id)

        # 清理旧会话
        _cleanup_old_sessions()

        # 保存到文件
        _save_session_store()


def get_session_count() -> int:
    """获取当前会话数量"""
    _load_session_store()
    return len(_session_store.get("sessions", {}))


def ask_claude_sync(user_prompt: str, user_id: str = "default",
                    session_id: str = None) -> dict:
    """
    同步调用 Claude Agent HTTP 接口

    Args:
        user_prompt: 用户的问题
        user_id: 用户ID（用于创建会话）
        session_id: 已有的会话ID（可选，如果不提供则创建新会话）

    Returns:
        dict: 包含 AI 回复和统计信息的字典
        {
            'content': str,          # AI 回复内容
            'session_id': str,       # 会话 ID
            'timestamp': str,        # 时间戳
            'error': str or None     # 错误信息
        }
    """
    result = {
        'content': '',
        'session_id': None,
        'timestamp': None,
        'error': None
    }

    try:
        client = get_client()

        # 如果没有提供 session_id，创建新会话
        if not session_id:
            session_info = client.create_session(user_id=user_id)
            session_id = session_info["session_id"]
            print(f"创建新会话: {session_id}")

        result['session_id'] = session_id

        # 发送消息
        response = client.chat(session_id=session_id, message=user_prompt)

        result['content'] = response.get('text', '')
        result['timestamp'] = response.get('timestamp')

        # 如果有 tool_calls，可以记录下来
        tool_calls = response.get('tool_calls', [])
        if tool_calls:
            print(f"工具调用: {len(tool_calls)} 次")

    except Exception as e:
        result['error'] = str(e)
        result['content'] = f"调用 Claude Agent HTTP 时出错: {str(e)}"

    return result


# 测试代码
if __name__ == "__main__":
    print("=" * 60)
    print("测试 Claude Agent HTTP 客户端...")
    print("=" * 60)

    # 初始化会话存储
    init_session_store()
    print(f"当前会话映射数量: {get_session_count()}")

    # 检查服务健康状态
    client = get_client()
    if not client.health_check():
        print(f"警告: Claude Agent HTTP 服务不可用 ({CLAUDE_AGENT_URL})")
        print("请确保 claude-agent-http 服务已启动")
        exit(1)

    print(f"✅ 服务健康检查通过: {CLAUDE_AGENT_URL}")

    # 测试创建会话和发送消息
    result = ask_claude_sync("你好，请介绍一下你自己。", user_id="test_user")

    print("\n【AI 回复】")
    print(f"内容: {result['content']}")
    print("\n【会话信息】")
    print(f"会话ID: {result['session_id']}")
    print(f"时间戳: {result['timestamp']}")
    if result['error']:
        print(f"错误: {result['error']}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
