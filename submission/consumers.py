"""判题状态实时推送的 WebSocket 服务端。

前端在提交代码后通过 WebSocket 接收判题状态，免去轮询。本文件是该协议的
服务端一半，客户端一半在 ojnext/src/shared/composables/websocket.ts，
两边的消息结构必须保持同构，改动任何字段都要同步前端。

协议（均为 JSON 文本帧）：

  客户端 → 服务端
    {"type": "ping", "timestamp": ...}          心跳，服务端回 pong
    {"type": "subscribe", "submission_id": id}  声明关注某次提交

  服务端 → 客户端
    {"type": "pong", "timestamp": ...}
    {"type": "submission_update", "submission_id": id, "result": int, "status": str,
     [判题完成时附带] "time_cost": ms, "memory_cost": KB, "score": int}

submission_update 有两个来源，payload 结构必须一致：
  1. 判题过程中 JudgeDispatcher._push_status 经 utils/websocket.py 的
     push_submission_update 组播（组名 submission_user_<user_id>，按用户分组）；
     utils/websocket.py 的 push_to_user 也借用同一个 handler 推送任意用户消息，
     因此 submission_update 方法名不可改。
  2. 客户端 subscribe 时本 consumer 从 DB 读当前状态直接补发
     （见 _replay_submission_status 的竞态说明）。

status 取值与 JudgeDispatcher 各处 _push_status 调用保持一致：
pending / judging / finished / error（error 即 SYSTEM_ERROR）。
"""

import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

from .models import JudgeStatus, Submission

logger = logging.getLogger(__name__)

# result → status 映射；不在表内的都是终态（AC/WA/TLE/... 均算 finished）
_RESULT_STATUS = {
    JudgeStatus.PENDING: "pending",
    JudgeStatus.JUDGING: "judging",
    JudgeStatus.SYSTEM_ERROR: "error",
}


class SubmissionConsumer(AsyncWebsocketConsumer):
    """按用户分组的判题状态推送连接，仅允许已登录用户。"""

    async def connect(self):
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close()
            return

        # 组名按用户划分：一个用户的所有连接（多标签页）都收到同样的推送
        self.group_name = f"submission_user_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        await self.accept()
        logger.info(f"WebSocket connected: user_id={self.user.id}, channel={self.channel_name}")

    async def disconnect(self, close_code):
        # 未认证连接在 connect 里被拒时没有 group_name
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.info(f"WebSocket disconnected: user_id={self.user.id}, close_code={close_code}")

    async def receive(self, text_data=None, bytes_data=None):
        # 签名必须带 bytes_data：channels 收到二进制帧时以 bytes_data= 调用，
        # 只声明 text_data 会 TypeError 导致连接异常断开。协议只用文本帧，忽略其余。
        if text_data is None:
            return
        try:
            data = json.loads(text_data)
            message_type = data.get("type")

            if message_type == "ping":
                await self.send(text_data=json.dumps({"type": "pong", "timestamp": data.get("timestamp")}))
            elif message_type == "subscribe":
                submission_id = data.get("submission_id")
                if submission_id:
                    logger.info(f"User {self.user.id} subscribed to submission {submission_id}")
                    await self._replay_submission_status(submission_id)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received from user {self.user.id}")
        except Exception as e:
            logger.error(f"Error handling message from user {self.user.id}: {str(e)}")

    async def _replay_submission_status(self, submission_id):
        """订阅时补发该提交的当前状态。

        判题（尤其是毫秒级的 SQL 题）可能在 WebSocket 建连前就完成，
        组播消息不会为未来成员排队，推送已丢失；订阅即补发可关闭这个竞态窗口。
        只查属于当前用户的提交，防止订阅他人提交探测状态。
        """
        try:
            submission = await Submission.objects.aget(id=submission_id, user_id=self.user.id)
        except Submission.DoesNotExist:
            return

        status = _RESULT_STATUS.get(submission.result, "finished")
        payload = {
            "type": "submission_update",
            "submission_id": str(submission.id),
            "result": submission.result,
            "status": status,
        }
        if status == "finished":
            # 与 dispatcher 判题完成推送的 extra 字段保持一致
            payload.update(
                time_cost=submission.statistic_info.get("time_cost"),
                memory_cost=submission.statistic_info.get("memory_cost"),
                score=submission.statistic_info.get("score", 0),
            )
        await self.send(text_data=json.dumps(payload))

    async def submission_update(self, event):
        """channel layer 组播的出口；方法名对应 group_send 的 type 字段，不可改名。"""
        try:
            await self.send(text_data=json.dumps(event["data"]))
            logger.debug(f"Sent submission update to user {self.user.id}: {event['data']}")
        except Exception as e:
            logger.error(f"Error sending submission update to user {self.user.id}: {str(e)}")
