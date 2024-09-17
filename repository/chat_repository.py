import os
from redis.asyncio import Redis
from motor.motor_asyncio import AsyncIOMotorClient
from uuid import uuid4

# 환경 변수에서 호스트 및 포트 정보 가져오기
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", "6379"))
mongodb_host = os.getenv("MONGO_HOST", "localhost")
mongodb_port = int(os.getenv("MONGO_PORT", "27017"))

# Redis 및 MongoDB 클라이언트 초기화
redis = Redis(host=redis_host, port=redis_port, decode_responses=True)
mongo_client = AsyncIOMotorClient(f"mongodb://{mongodb_host}:{mongodb_port}/")
chat_db = mongo_client["chat_database"]  # MongoDB에서 사용할 데이터베이스


# 사용자를 채팅방에 추가
async def add_user_to_room(room_id: str, user_id: str):
    await redis.sadd(f"room:{room_id}:users", user_id)


# 사용자를 채팅방에서 제거
async def remove_user_from_room(room_id: str, user_id: str):
    await redis.srem(f"room:{room_id}:users", user_id)


# 메시지를 Redis에 저장하고 발행
async def save_message(room_id: str, message: str):
    await redis.rpush(f"room:{room_id}:messages", message)


async def publish_message(room_id: str, message: str):
    await redis.publish(f"room:{room_id}", message)


# 채팅방 사용자 정보를 가져오고 만료시간을 설정
async def set_room_user_expiration(room_id: str):
    await redis.expire(f"room:{room_id}:users", 1800)  # 30분 TTL 설정


# 채팅방 목록을 가져오기 위한 메소드
async def get_chat_rooms():
    room_keys = await redis.keys("room:*:users")
    rooms = []

    for key in room_keys:
        room_id = key.split(":")[1]
        user_count = await redis.scard(key)
        latest_message = await redis.lrange(f"room:{room_id}:messages", -1, -1)
        rooms.append(
            {
                "room_id": room_id,
                "user_count": user_count,
                "latest_message": latest_message[0] if latest_message else None,
            }
        )

    # 30분 내 접속자 수로 정렬
    rooms.sort(key=lambda x: x["user_count"], reverse=True)
    return rooms


# MongoDB에 채팅방 추가
async def create_chat_room(title: str):
    room = {"title": title}
    result = await chat_db.chat_rooms.insert_one(room)
    return str(result.inserted_id)


# MongoDB에서 채팅방 정보 조회
async def get_chat_room(room_id: str):
    return await chat_db.chat_rooms.find_one({"_id": room_id})


# MongoDB에서 채팅방의 메시지 가져오기
async def get_messages(room_id: str, limit: int = 50):
    return (
        await chat_db.messages.find({"room_id": room_id})
        .sort("timestamp", -1)
        .limit(limit)
        .to_list(length=limit)
    )
