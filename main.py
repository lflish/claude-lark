"""飞书 Claude 机器人主程序"""

import lark_oapi as lark
from lark_oapi.api.im.v1 import *
import json
import os
import threading
import time
from queue import Queue
from handle import (
    ask_claude_sync,
    get_session_id,
    save_session_mapping,
    get_client,
    init_session_store,
    get_session_count,
    SESSION_STORE_DIR
)


# 消息处理队列
message_queue = Queue()


def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    """立即响应飞书，将消息放入处理队列"""
    try:
        # 基本消息类型检查
        if data.event.message.message_type != "text":
            msg_id = data.event.message.message_id
            print(f"消息 {msg_id} 不是文本消息，跳过")
            return

        # 立即将消息放入队列，不阻塞响应
        message_queue.put(data)
        msg_id = data.event.message.message_id
        queue_size = message_queue.qsize()
        print(f"消息 {msg_id} 已加入处理队列，队列长度: {queue_size}")

        # 函数立即返回，飞书收到200响应，避免重复发送

    except Exception as e:
        print(f"消息队列入队失败: {str(e)}")


def process_single_message(data: P2ImMessageReceiveV1) -> None:
    """实际的消息处理逻辑"""
    message_id = data.event.message.message_id
    msg = data.event.message
    parent_id = msg.parent_id if hasattr(msg, 'parent_id') else None
    root_id = msg.root_id if hasattr(msg, 'root_id') else None

    print(f"开始处理消息: {message_id}")
    print(f"  - parent_id: {parent_id}")
    print(f"  - root_id: {root_id}")

    # 解析消息
    if data.event.message.message_type == "text":
        user_message = json.loads(data.event.message.content)["text"]
    else:
        send_response(data, "请发送文本消息")
        return

    print(f"收到消息内容: {user_message}")

    # 判断是否为群聊消息
    chat_type = data.event.message.chat_type

    # 如果是群聊，检查是否@了机器人
    if chat_type == "group":
        # 检查 mentions 字段
        mentions = (data.event.message.mentions
                    if hasattr(data.event.message, 'mentions') else None)

        if not mentions:
            print("群聊消息未@机器人，忽略")
            return

        # 检查是否@了当前机器人
        bot_mentioned = False
        for mention in mentions:
            # mention.id 包含机器人的 ID
            if hasattr(mention, 'id') and mention.id:
                # 获取机器人自己的 ID
                mention_id = (mention.id.app_id
                              if hasattr(mention.id, 'app_id') else None)
                if mention_id == lark.APP_ID:
                    bot_mentioned = True
                    break

        if not bot_mentioned:
            print("群聊消息未@本机器人，忽略")
            return

        print("检测到@机器人，开始处理...")

        # 移除消息中的@标记，只保留实际问题内容
        if mentions:
            for mention in mentions:
                mention_key = (mention.key
                               if hasattr(mention, 'key') else None)
                if mention_key and mention_key in user_message:
                    user_message = (
                        user_message.replace(mention_key, '').strip()
                    )

    # 私聊消息直接处理（保持原有逻辑）
    elif chat_type == "p2p":
        print("私聊消息，直接处理")

    # 获取用户ID（优先使用 open_id，其次 union_id，最后使用 unknown）
    sender_id = data.event.sender.sender_id
    user_id = None
    if hasattr(sender_id, 'open_id') and sender_id.open_id:
        user_id = sender_id.open_id
    elif hasattr(sender_id, 'union_id') and sender_id.union_id:
        user_id = sender_id.union_id
    elif hasattr(sender_id, 'user_id') and sender_id.user_id:
        user_id = sender_id.user_id
    else:
        user_id = "unknown"

    # 获取或关联会话
    # 优先使用 root_id（整个回复链的根消息），其次使用 parent_id
    session_id = None

    if root_id:
        session_id = get_session_id(root_id)
        if session_id:
            print(f"使用 root_id 关联的会话: {session_id}")

    if not session_id and parent_id:
        session_id = get_session_id(parent_id)
        if session_id:
            print(f"使用 parent_id 关联的会话: {session_id}")

    if session_id:
        print(f"找到历史会话: {session_id}")
        # 将当前消息也关联到这个会话（作为普通消息）
        save_session_mapping(message_id, session_id, is_root=False)
    else:
        print("未找到历史会话，将创建新会话")

    # 先发送一个"思考中"的提示（可选）
    try:
        if chat_type == "group":
            typing_msg = "🤔 Claude正在思考中，请稍候..."
            send_typing_indicator(data, typing_msg)
    except Exception as e:
        print(f"发送思考提示失败: {str(e)}")

    # 调用 Claude Agent HTTP 获取回复
    try:
        print(f"正在调用 Claude Agent HTTP (用户: {user_id})...")
        result = ask_claude_sync(
            user_prompt=user_message,
            user_id=user_id,
            session_id=session_id
        )

        if result['error']:
            print(f"Claude 调用出错: {result['error']}")
            claude_response = f"抱歉，AI 处理出现错误：{result['error']}"
        else:
            claude_response = result['content']
            preview = claude_response[:100]
            print(f"Claude 回复: {preview}...")

            # 保存会话映射
            if result['session_id']:
                # 如果有 root_id，先更新 root_id 的会话映射
                if root_id:
                    # root_id 是对话的根消息
                    save_session_mapping(root_id, result['session_id'],
                                         is_root=True)

                # 将当前消息ID与会话ID关联（作为最近消息）
                if message_id != root_id:
                    save_session_mapping(message_id, result['session_id'],
                                         is_root=False)

                sess_id = result['session_id']
                print(f"会话映射已保存，session_id: {sess_id}")

    except Exception as e:
        print(f"Claude 调用失败: {str(e)}")
        claude_response = f"抱歉，AI 处理出现异常：{str(e)}"

    # 发送回复（使用引用回复）
    reply_message_id = send_response(data, claude_response)

    # 保存机器人回复消息的会话映射（用户可能会直接回复机器人的消息）
    if reply_message_id and result.get('session_id'):
        save_session_mapping(reply_message_id, result['session_id'],
                             is_root=False)
        msg = f"机器人回复消息ID {reply_message_id} 的会话映射已保存"
        print(msg)

    print(f"消息 {message_id} 处理完成")


def send_typing_indicator(data: P2ImMessageReceiveV1, message: str) -> None:
    """发送处理中提示"""
    try:
        send_response(data, message)
    except Exception as e:
        print(f"发送处理提示失败: {str(e)}")


def process_message_worker():
    """后台工作线程，处理消息队列"""
    print("消息处理工作线程已启动")
    while True:
        try:
            # 从队列中获取消息，超时1秒
            data = message_queue.get(timeout=1)

            # 处理单个消息
            process_single_message(data)

            # 标记任务完成
            message_queue.task_done()

        except Exception as e:
            # 只有非空队列错误才打印
            if "queue.Empty" not in str(type(e)) and "Empty" not in str(e):
                print(f"消息处理出错: {str(e)}")
            continue


def send_response(data: P2ImMessageReceiveV1, response_text: str,
                  max_retries: int = 3) -> str:
    """
    发送回复消息到飞书，带重试机制
    统一使用 reply API 来引用原始消息

    Returns:
        str: 发送成功的消息ID，失败返回 None
    """
    content = json.dumps({"text": response_text})
    message_id = data.event.message.message_id

    for attempt in range(max_retries):
        try:
            # 统一使用 reply API，这样无论是私聊还是群聊都会引用原消息
            request = (
                ReplyMessageRequest.builder()
                .message_id(message_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .content(content)
                    .msg_type("text")
                    .build()
                )
                .build()
            )
            response = client.im.v1.message.reply(request)

            if response.success():
                reply_msg_id = (response.data.message_id
                                if response.data else None)
                chat_type = data.event.message.chat_type
                chat_type_str = '私聊' if chat_type == 'p2p' else '群聊'
                attempt_str = f"{attempt + 1}/{max_retries}"
                print(f"{chat_type_str}消息回复成功 (尝试 {attempt_str})")
                print(f"  - 原消息ID: {message_id}")
                print(f"  - 回复消息ID: {reply_msg_id}")
                return reply_msg_id
            else:
                print(f"消息回复失败: {response.code}, {response.msg}")

        except Exception as e:
            attempt_str = f"{attempt + 1}/{max_retries}"
            print(f"发送消息异常 (尝试 {attempt_str}): {str(e)}")

        # 重试前等待，使用指数退避
        if attempt < max_retries - 1:
            wait_time = 2 ** attempt
            print(f"等待 {wait_time} 秒后重试...")
            time.sleep(wait_time)

    print(f"消息发送最终失败，已重试 {max_retries} 次")
    return None


# 从环境变量读取配置
APP_ID = os.getenv("APP_ID", "")
APP_SECRET = os.getenv("APP_SECRET", "")

if not APP_ID or not APP_SECRET:
    print("警告: APP_ID 或 APP_SECRET 未设置，请检查环境变量")

# 注册事件处理器
event_handler = (
    lark.EventDispatcherHandler.builder("", "")
    .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
    .build()
)

lark.APP_ID = APP_ID
lark.APP_SECRET = APP_SECRET

# 创建客户端
client = (lark.Client.builder()
          .app_id(lark.APP_ID)
          .app_secret(lark.APP_SECRET)
          .build())
wsClient = lark.ws.Client(
    lark.APP_ID,
    lark.APP_SECRET,
    event_handler=event_handler,
    log_level=lark.LogLevel.DEBUG,
)


def main():
    """启动机器人"""
    print("=" * 60)
    print("正在启动 Claude 飞书机器人...")
    print("=" * 60)
    app_id_display = (f"{APP_ID[:10]}..."
                      if len(APP_ID) > 10 else APP_ID)
    print(f"APP_ID: {app_id_display}")
    print(f"APP_SECRET: {'*' * 8}")

    # 获取 Claude Agent HTTP 配置
    claude_agent_url = os.getenv("CLAUDE_AGENT_URL", "http://localhost:8000")
    print(f"CLAUDE_AGENT_URL: {claude_agent_url}")

    # 初始化会话映射存储
    print(f"SESSION_STORE_DIR: {SESSION_STORE_DIR}")
    init_session_store()
    print(f"📂 已加载会话映射，当前数量: {get_session_count()}")

    # 检查 Claude Agent HTTP 服务健康状态
    try:
        agent_client = get_client()
        if agent_client.health_check():
            print("✅ Claude Agent HTTP 服务连接正常")
        else:
            warning_msg = "⚠️ Claude Agent HTTP 服务不可用，请检查服务是否启动"
            print(warning_msg)
    except Exception as e:
        print(f"⚠️ Claude Agent HTTP 服务检查失败: {str(e)}")

    # 启动后台消息处理工作线程
    worker_thread = threading.Thread(
        target=process_message_worker,
        daemon=True
    )
    worker_thread.start()
    print("后台消息处理线程已启动")

    print("=" * 60)
    print("🚀 机器人启动完成！")
    print("✅ 立即响应机制已启用，防止重复消息")
    print("✅ 后台异步处理已启用")
    print("✅ 消息引用回复已启用")
    print("✅ 上下文关联已启用（通过 claude-agent-http 会话管理）")
    print("=" * 60)

    # 启动 WebSocket 连接
    wsClient.start()


if __name__ == "__main__":
    main()
