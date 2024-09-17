from datetime import datetime, timezone
import json
from typing import List
from fastapi import (
    BackgroundTasks,
    FastAPI,
    APIRouter,
    Request,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
)
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os
from redis.asyncio import Redis
from motor.motor_asyncio import AsyncIOMotorClient

# FastAPI 애플리케이션 생성
app = FastAPI()
router = APIRouter()
templates = Jinja2Templates(directory="templates")

# 환경 변수 설정
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", "6379"))
mongodb_host = os.getenv("MONGO_HOST", "localhost")
mongodb_port = int(os.getenv("MONGO_PORT", "27017"))
mysql_host = os.getenv("MYSQL_HOST", "localhost")
mysql_port = int(os.getenv("MYSQL_PORT", "3306"))
mysql_user = os.getenv("MYSQL_USER", "root")

# Redis 및 MongoDB 클라이언트 초기화
redis = Redis(host=redis_host, port=redis_port, decode_responses=True)
mongo_client = AsyncIOMotorClient(f"mongodb://{mongodb_host}:{mongodb_port}/")
chat_db = mongo_client["chat_database"]


async def get_ai_generated_user_id():
    # Redis의 "user:id:counter" 키를 사용하여 고유 ID 증가
    user_id = await redis.incr("user:id:counter")
    # user_id를 문자열로 변환하여 반환
    return f"user_{user_id}"


# 사용자 ID를 Redis에서 관리
async def add_user_to_room(room_id: str, user_id: str):
    await redis.sadd(f"room:{room_id}:users", user_id)


async def remove_user_from_room(room_id: str, user_id: str):
    await redis.srem(f"room:{room_id}:users", user_id)


async def save_message(room_id: str, message: str, sender: str):
    await redis.rpush(f"room:{room_id}:messages", message)
    await chat_db.messages.insert_one(
        {
            "room_id": room_id,
            "message": message,
            "sender": sender,
            "timestamp": datetime.now(timezone.utc),
        }
    )


async def get_all_messages(room_id: str):
    # MongoDB에서 특정 방의 모든 메시지를 타임스탬프 순으로 조회
    messages = (
        await chat_db.messages.find({"room_id": room_id})
        .sort("timestamp", 1)
        .to_list(None)
    )

    # datetime 객체를 문자열로 변환
    return [
        {
            "message": json.loads(message["message"])["content"],
            "sender": message["sender"],
            "timestamp": message["timestamp"].isoformat(),
        }
        for message in messages
    ]


async def publish_message(room_id: str, message: str, sender: str):
    await redis.publish(f"room:{room_id}:{sender}", message)


async def set_room_user_expiration(room_id: str):
    await redis.expire(f"room:{room_id}:users", 1800)  # 30분 TTL 설정


async def get_chat_rooms():
    # MongoDB에서 방 목록 조회
    rooms = await chat_db.chat_rooms.find().to_list(None)  # 모든 방 목록 조회
    room_list = []

    for room in rooms:
        room_id = str(room["_id"])
        user_count = await redis.zscore("chatroom:user_count", room_id)
        # MongoDB에서 가장 최근 메시지 조회
        latest_message = await chat_db.messages.find_one(
            {"room_id": room_id}, sort=[("timestamp", -1)]
        )

        room_list.append(
            {
                "room_id": room_id,
                "title": room.get("title", ""),
                "user_count": int(user_count) if user_count else 0,
                "latest_message": latest_message["message"] if latest_message else None,
            }
        )

    # 30분 내 접속자 수로 정렬
    room_list.sort(key=lambda x: x["user_count"], reverse=True)

    return room_list


async def create_room(title: str):
    room = {"title": title}
    result = await chat_db.chat_rooms.insert_one(room)
    return str(result.inserted_id)


async def get_chat_room(room_id: str):
    return await chat_db.chat_rooms.find_one({"_id": room_id})


async def get_messages(room_id: str, limit: int = 50):
    return (
        await chat_db.messages.find({"room_id": room_id})
        .sort("timestamp", -1)
        .limit(limit)
        .to_list(length=limit)
    )


# 누락된 메시지 처리 함수 추가
async def handle_message(room_id: str, message: str, sender: str):
    # 메시지를 저장하고 발행
    await save_message(room_id, message, sender)
    # await publish_message(room_id, message, sender)


async def add_user_to_room_in_db(room_id: str, user_id: str):
    # MongoDB에 방에 참여자 추가
    await chat_db.rooms.update_one(
        {"_id": room_id}, {"$addToSet": {"participants": user_id}}
    )


async def remove_user_from_room_in_db(room_id: str, user_id: str):
    # MongoDB에서 방에서 참여자 제거
    await chat_db.rooms.update_one(
        {"_id": room_id}, {"$pull": {"participants": user_id}}
    )


async def get_room_participants(room_id: str):
    # MongoDB에서 특정 방의 참여자 목록 조회
    room = await chat_db.rooms.find_one({"_id": room_id})
    return room.get("participants", []) if room else []


# 웹소켓 연결을 관리하는 딕셔너리
connected_clients = {}


# async def redis_subscriber(room_id: str):
#     pubsub = redis.pubsub()
#     await pubsub.subscribe(f"room:{room_id}:*")

#     async for message in pubsub.listen():
#         if message and message["type"] == "message":
#             room_channel = message["channel"].decode()
#             room_id_extracted = room_channel.split(":")[1]
#             sender = room_channel.split(":")[2]
#             data = message["data"].decode()

#             # 연결된 모든 클라이언트에 메시지 전송
#             if room_id_extracted in connected_clients:
#                 for client in connected_clients[room_id_extracted].values():
#                     await client.send_text(data)


# 채팅방 생성 요청 모델
class CreateChatRoomRequest(BaseModel):
    title: str


# 클라이언트 페이지 렌더링
@router.get("/client")
async def client(request: Request):
    return templates.TemplateResponse("client2.html", {"request": request})


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()

    # 유저별 웹소켓을 연결하여 관리
    if user_id not in connected_clients:
        connected_clients[user_id] = websocket

    try:
        while True:
            data = await websocket.receive_text()
            event_data = json.loads(data)

            # 이벤트 타입을 확인하여 처리
            if event_data["type"] == "join_room":
                room_id = event_data["room_id"]

                # MongoDB에 방 참여자 정보 추가
                await add_user_to_room_in_db(room_id, user_id)

                # 현재 방에 참여 중인 다른 클라이언트들에게 알림
                participants = await get_room_participants(room_id)
                for participant_id in participants:
                    if (
                        participant_id in connected_clients
                        and participant_id != user_id
                    ):
                        await connected_clients[participant_id].send_json(
                            {
                                "event": "user_joined",
                                "user_id": user_id,
                                "room_id": room_id,
                            }
                        )

            elif event_data["type"] == "message":
                # 방에 메시지를 보냈을 때 처리
                room_id = event_data["room_id"]
                message_content = event_data["content"]

                # 메시지 처리 및 저장
                await handle_message(room_id, message_content, user_id)

                # 방의 모든 사용자에게 메시지 전달
                participants = await get_room_participants(room_id)
                for participant_id in participants:
                    if participant_id in connected_clients:
                        await connected_clients[participant_id].send_json(
                            {
                                "message": message_content,
                                "sender": user_id,
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
    except WebSocketDisconnect:
        # 유저의 웹소켓 연결 해제 시 클라이언트 목록에서 제거
        del connected_clients[user_id]


# 채팅방 생성
@router.post("/chatrooms")
async def create_chat_room(request: CreateChatRoomRequest):
    try:
        room = await create_room(request.title)
        return {"message": "채팅방이 생성되었습니다.", "room": room}
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail=str(e))


# 채팅방 목록 조회
@router.get("/chatrooms")
async def get_chat_rooms_endpoint():
    return await get_chat_rooms()


# 라우터를 FastAPI 애플리케이션에 포함
app.include_router(router)

# 서버 실행 코드 (개발 환경에서 사용할 수 있음)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
