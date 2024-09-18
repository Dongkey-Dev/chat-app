from datetime import datetime, timezone
from bson import ObjectId
from app.db.redis import redis
from app.db.mongodb import chat_db


class ChatService:
    # connected_clients를 클래스 속성으로 관리
    connected_clients = {}

    @staticmethod
    async def add_client(user_id: str, websocket):
        """사용자를 연결된 클라이언트 목록에 추가"""
        ChatService.connected_clients[user_id] = websocket

    @staticmethod
    async def remove_client(user_id: str):
        """사용자를 연결된 클라이언트 목록에서 제거"""
        if user_id in ChatService.connected_clients:
            del ChatService.connected_clients[user_id]

    @staticmethod
    async def save_message(room_id: str, message: str, sender: str):
        """메시지를 Redis 및 MongoDB에 저장"""
        await redis.rpush(f"room:{room_id}:messages", message)
        await chat_db.messages.insert_one(
            {
                "room_id": room_id,
                "message": message,
                "sender": sender,
                "timestamp": datetime.now(timezone.utc),
            }
        )

    @staticmethod
    async def get_all_messages(room_id: str):
        """MongoDB에서 특정 방의 모든 메시지를 타임스탬프 순으로 조회"""
        messages = (
            await chat_db.messages.find({"room_id": room_id})
            .sort("timestamp", 1)
            .to_list(None)
        )
        return [
            {
                "message": message["message"],
                "sender": message["sender"],
                "timestamp": message["timestamp"].isoformat(),
            }
            for message in messages
        ]

    @staticmethod
    async def get_chat_rooms():
        """MongoDB와 Redis를 활용하여 방 목록 조회"""
        rooms = await chat_db.chat_rooms.find().to_list(None)
        room_list = []
        for room in rooms:
            room_id = str(room["_id"])
            user_count = await redis.zscore("chatroom:user_count", room_id)
            latest_message = await chat_db.messages.find_one(
                {"room_id": room_id}, sort=[("timestamp", -1)]
            )
            room_list.append(
                {
                    "room_id": room_id,
                    "title": room.get("title", ""),
                    "user_count": int(user_count) if user_count else 0,
                    "latest_message": (
                        latest_message["message"] if latest_message else None
                    ),
                }
            )
        # 30분 내 접속자 수로 정렬
        room_list.sort(key=lambda x: x["user_count"], reverse=True)
        return room_list

    @staticmethod
    async def create_room(title: str):
        """새로운 방을 MongoDB에 생성"""
        room = {"title": title, "participants": []}
        result = await chat_db.chat_rooms.insert_one(room)
        return str(result.inserted_id)

    @staticmethod
    async def add_user_to_room(room_id: str, user_id: str):
        """Redis와 MongoDB에서 방에 유저 추가"""
        await redis.zadd(f"room:{room_id}:users", {user_id: 9999999999})
        await ChatService.update_room_user_count(room_id)
        await chat_db.chat_rooms.update_one(
            {"_id": ObjectId(room_id)}, {"$addToSet": {"participants": user_id}}
        )

    @staticmethod
    async def remove_user_from_room(room_id: str, user_id: str):
        """Redis와 MongoDB에서 방에서 유저 제거"""
        current_time = datetime.now().timestamp()
        await redis.zadd(f"room:{room_id}:users", {user_id: current_time})
        await ChatService.update_room_user_count(room_id)
        await chat_db.chat_rooms.update_one(
            {"_id": ObjectId(room_id)}, {"$pull": {"participants": user_id}}
        )

    @staticmethod
    async def update_room_user_count(room_id: str):
        """Redis에서 30분 내 활성 사용자 수 업데이트"""
        current_time = datetime.now().timestamp()
        await redis.zremrangebyscore(f"room:{room_id}:users", 0, current_time - 1800)
        user_count = await redis.zcard(f"room:{room_id}:users")
        await redis.zadd("chatroom:user_count", {room_id: user_count})

    @staticmethod
    async def get_room_participants(room_id: str):
        """MongoDB에서 방의 참가자 목록 조회"""
        room = await chat_db.chat_rooms.find_one({"_id": ObjectId(room_id)})
        return room.get("participants", []) if room else []

    @staticmethod
    async def get_user_rooms_from_redis(user_id: str):
        """Redis에서 특정 사용자가 속한 방 목록 조회"""
        room_keys = await redis.keys("room:*:users")
        user_rooms = []
        for room_key in room_keys:
            if await redis.zscore(room_key, user_id):
                room_id = room_key.split(":")[1]
                user_rooms.append(room_id)
        return user_rooms

    @staticmethod
    async def notify_room_participants(room_id: str, message: str, sender: str):
        """방에 있는 모든 참가자에게 메시지를 전송"""
        participants = await ChatService.get_room_participants(room_id)
        for participant_id in participants:
            if participant_id in ChatService.connected_clients:
                await ChatService.connected_clients[participant_id].send_json(
                    {
                        "event": "message",
                        "message": message,
                        "sender": sender,
                        "room_id": room_id,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

    @staticmethod
    async def notify_all_clients(event_data: dict):
        """모든 클라이언트에게 이벤트 알림"""
        for client in ChatService.connected_clients.values():
            await client.send_json(event_data)
