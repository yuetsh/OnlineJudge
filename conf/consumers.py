"""
WebSocket consumers for configuration updates
"""
import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class ConfigConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time configuration updates
    当管理员修改配置后，通过 WebSocket 实时推送配置变化
    """

    async def connect(self):
        """处理 WebSocket 连接"""
        self.user = self.scope["user"]
        
        # 只允许认证用户连接
        if not self.user.is_authenticated:
            await self.close()
            return
        
        # 使用全局配置组名，所有用户都能接收配置更新
        self.group_name = "config_updates"
        
        # 加入配置更新组
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"Config WebSocket connected: user_id={self.user.id}, channel={self.channel_name}")

    async def disconnect(self, close_code):
        """处理 WebSocket 断开连接"""
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
            logger.info(f"Config WebSocket disconnected: user_id={self.user.id}, close_code={close_code}")

    async def receive(self, text_data):
        """
        接收客户端消息
        客户端可以发送心跳包或配置更新请求
        """
        try:
            data = json.loads(text_data)
            message_type = data.get("type")
            
            if message_type == "ping":
                # 响应心跳包
                await self.send(text_data=json.dumps({
                    "type": "pong",
                    "timestamp": data.get("timestamp")
                }))
            elif message_type == "config_update":
                # 处理配置更新请求
                key = data.get("key")
                value = data.get("value")
                if key and value is not None:
                    logger.info(f"User {self.user.id} requested config update: {key}={value}")
                    # 这里可以添加权限检查，只有管理员才能发送配置更新
                    if self.user.is_superuser:
                        # 广播配置更新给所有连接的客户端
                        await self.channel_layer.group_send(
                            self.group_name,
                            {
                                "type": "config_update",
                                "data": {
                                    "type": "config_update",
                                    "key": key,
                                    "value": value
                                }
                            }
                        )
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received from user {self.user.id}")
        except Exception as e:
            logger.error(f"Error handling message from user {self.user.id}: {str(e)}")

    async def config_update(self, event):
        """
        接收来自 channel layer 的配置更新消息并发送给客户端
        这个方法名对应 group_send 中的 type 字段
        """
        try:
            # 从 event 中提取数据并发送给客户端
            await self.send(text_data=json.dumps(event["data"]))
            logger.debug(f"Sent config update to user {self.user.id}: {event['data']}")
        except Exception as e:
            logger.error(f"Error sending config update to user {self.user.id}: {str(e)}")
