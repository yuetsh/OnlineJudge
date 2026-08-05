"""
WebSocket consumers for flowchart evaluation updates
"""

import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class FlowchartConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time flowchart evaluation updates
    当用户提交流程图后，通过 WebSocket 实时接收AI评分状态更新
    """

    async def connect(self):
        """处理 WebSocket 连接"""
        self.user = self.scope["user"]

        # 只允许认证用户连接
        if not self.user.is_authenticated:
            await self.close()
            return

        # 使用用户 ID 作为组名，这样可以向特定用户推送消息
        self.group_name = f"flowchart_user_{self.user.id}"

        # 加入用户专属的组
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        await self.accept()
        logger.info(f"Flowchart WebSocket connected: user_id={self.user.id}, channel={self.channel_name}")

    async def disconnect(self, close_code):
        """处理 WebSocket 断开连接"""
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.info(f"Flowchart WebSocket disconnected: user_id={self.user.id}, close_code={close_code}")

    async def receive(self, text_data):
        """
        接收客户端消息
        客户端可以发送心跳包或订阅特定流程图提交
        """
        try:
            data = json.loads(text_data)
            message_type = data.get("type")

            if message_type == "ping":
                # 响应心跳包
                await self.send(text_data=json.dumps({"type": "pong", "timestamp": data.get("timestamp")}))
            elif message_type == "subscribe":
                # 订阅特定流程图提交的更新
                submission_id = data.get("submission_id")
                if submission_id:
                    logger.info(f"User {self.user.id} subscribed to flowchart submission {submission_id}")
                    # 可以在这里做额外的订阅逻辑
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received from user {self.user.id}")
        except Exception as e:
            logger.error(f"Error handling message from user {self.user.id}: {str(e)}")

    async def flowchart_evaluation_update(self, event):
        """
        接收来自 channel layer 的流程图评分更新消息并发送给客户端
        这个方法名对应 push_flowchart_evaluation_update 中的 type 字段
        """
        try:
            # 从 event 中提取数据并发送给客户端
            await self.send(text_data=json.dumps(event["data"]))
            logger.debug(f"Sent flowchart evaluation update to user {self.user.id}: {event['data']}")
        except Exception as e:
            logger.error(f"Error sending flowchart evaluation update to user {self.user.id}: {str(e)}")
