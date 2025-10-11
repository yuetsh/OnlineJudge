"""
WebSocket utility functions for pushing real-time updates
"""
import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


def push_submission_update(submission_id: str, user_id: int, data: dict):
    """
    推送提交状态更新到指定用户的 WebSocket 连接
    
    Args:
        submission_id: 提交 ID
        user_id: 用户 ID
        data: 要发送的数据，应该包含 type, submission_id, result 等字段
    """
    channel_layer = get_channel_layer()
    
    if channel_layer is None:
        logger.warning("Channel layer is not configured, cannot push submission update")
        return
    
    # 构建组名，与 SubmissionConsumer 中的组名一致
    group_name = f"submission_user_{user_id}"
    
    try:
        # 向指定用户组发送消息
        # type 字段对应 consumer 中的方法名（submission_update）
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "submission_update",  # 对应 SubmissionConsumer.submission_update 方法
                "data": data,
            }
        )
        logger.info(f"Pushed submission update: submission_id={submission_id}, user_id={user_id}, status={data.get('status')}")
    except Exception as e:
        logger.error(f"Failed to push submission update: submission_id={submission_id}, user_id={user_id}, error={str(e)}")


def push_to_user(user_id: int, message_type: str, data: dict):
    """
    向指定用户推送自定义消息
    
    Args:
        user_id: 用户 ID
        message_type: 消息类型
        data: 消息数据
    """
    channel_layer = get_channel_layer()
    
    if channel_layer is None:
        logger.warning("Channel layer is not configured, cannot push message")
        return
    
    group_name = f"submission_user_{user_id}"
    
    try:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "submission_update",
                "data": {
                    "type": message_type,
                    **data
                },
            }
        )
        logger.info(f"Pushed message to user {user_id}: type={message_type}")
    except Exception as e:
        logger.error(f"Failed to push message to user {user_id}: error={str(e)}")


def push_flowchart_evaluation_update(submission_id: str, user_id: int, data: dict):
    """
    推送流程图评分状态更新到指定用户的 WebSocket 连接
    
    Args:
        submission_id: 流程图提交 ID
        user_id: 用户 ID
        data: 要发送的数据，应该包含 type, submission_id, score, grade, feedback 等字段
    """
    channel_layer = get_channel_layer()
    
    if channel_layer is None:
        logger.warning("Channel layer is not configured, cannot push flowchart evaluation update")
        return
    
    # 构建组名，与 SubmissionConsumer 中的组名一致
    group_name = f"submission_user_{user_id}"
    
    try:
        # 向指定用户组发送消息
        # type 字段对应 consumer 中的方法名（flowchart_evaluation_update）
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "flowchart_evaluation_update",  # 对应 SubmissionConsumer.flowchart_evaluation_update 方法
                "data": data,
            }
        )
        logger.info(f"Pushed flowchart evaluation update: submission_id={submission_id}, user_id={user_id}, type={data.get('type')}")
    except Exception as e:
        logger.error(f"Failed to push flowchart evaluation update: submission_id={submission_id}, user_id={user_id}, error={str(e)}")


def push_config_update(key: str, value):
    """
    推送配置更新到所有连接的客户端
    
    Args:
        key: 配置键名
        value: 配置值
    """
    channel_layer = get_channel_layer()
    
    if channel_layer is None:
        logger.warning("Channel layer is not configured, cannot push config update")
        return
    
    # 使用全局配置组名
    group_name = "config_updates"
    
    try:
        # 向所有连接的客户端发送配置更新
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "config_update",
                "data": {
                    "type": "config_update",
                    "key": key,
                    "value": value
                }
            }
        )
        logger.info(f"Pushed config update: {key}={value}")
    except Exception as e:
        logger.error(f"Failed to push config update: {key}={value}, error={str(e)}")
