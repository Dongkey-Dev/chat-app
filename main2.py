import asyncio
from bson import ObjectId
from datetime import datetime, timezone
import json
from fastapi import (
    FastAPI,
    APIRouter,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.templating import Jinja2Templates
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

# Redis 및 MongoDB 클라이언트 초기화
redis = Redis(host=redis_host, port=redis_port, decode_responses=True)
mongo_client = AsyncIOMotorClient(f"mongodb://{mongodb_host}:{mongodb_port}/")
chat_db = mongo_client["chat_database"]


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
            "message": message["message"],
            "sender": message["sender"],
            "timestamp": message["timestamp"].isoformat(),
        }
        for message in messages
    ]


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


async def add_user_to_room(room_id: str, user_id: str):
    await redis.zadd(f"room:{room_id}:users", {user_id: 9999999999})
    await update_room_user_count(room_id)


async def remove_user_from_room(room_id: str, user_id: str):
    current_time = datetime.now().timestamp()
    await redis.zadd(f"room:{room_id}:users", {user_id: current_time})
    await update_room_user_count(room_id)


async def update_room_user_count(room_id: str):
    # 30분 내의 활성 사용자 수를 계산하여 Redis에 반영
    current_time = datetime.now().timestamp()
    # 30분이 지난 사용자들을 제거
    await redis.zremrangebyscore(f"room:{room_id}:users", 0, current_time - 1800)
    # 현재 방의 30분 내 활성 사용자 수를 ZSet에 업데이트
    user_count = await redis.zcard(f"room:{room_id}:users")
    await redis.zadd("chatroom:user_count", {room_id: user_count})


async def create_room(title: str):
    room = {"title": title, "participants": []}
    result = await chat_db.chat_rooms.insert_one(room)
    return str(result.inserted_id)


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
    await chat_db.chat_rooms.update_one(
        {"_id": ObjectId(room_id)}, {"$addToSet": {"participants": user_id}}
    )


async def get_room_participants(room_id: str):
    # MongoDB에서 특정 방의 참여자 목록 조회
    room = await chat_db.chat_rooms.find_one({"_id": ObjectId(room_id)})
    return room.get("participants", []) if room else []


# 웹소켓 연결을 관리하는 딕셔너리
connected_clients = {}


async def handle_join_room_event(user_id: str, room_id: str):
    # MongoDB에 참여자 추가
    await add_user_to_room_in_db(room_id, user_id)


# 클라이언트 페이지 렌더링
@router.get("/client")
async def client(request: Request):
    return templates.TemplateResponse("client2.html", {"request": request})


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """WebSocket을 통해 사용자 연결을 관리하는 엔드포인트"""

    await websocket.accept()
    connected_clients[user_id] = websocket
    await send_initial_data(websocket, user_id)

    try:
        await asyncio.gather(handle_messages(websocket, user_id), log_status())
    except WebSocketDisconnect:
        await handle_disconnect(user_id)


async def send_initial_data(websocket: WebSocket, user_id: str):
    """클라이언트가 연결되면 방 목록과 유저 ID를 전송"""
    room_list = await get_chat_rooms()
    await websocket.send_json(
        {"event": "connected", "user_id": user_id, "rooms": room_list}
    )


async def handle_messages(websocket: WebSocket, user_id: str):
    """WebSocket으로부터 메시지를 수신 및 처리하는 함수"""
    while True:
        data = await websocket.receive_text()
        event_data = json.loads(data)

        # match 문을 사용해 이벤트 타입에 따른 분기 처리
        match event_data.get("type"):
            case "join_room":
                await handle_join_room_event(websocket, user_id, event_data)
            case "message":
                await handle_chat_message_event(user_id, event_data)
            case "create_room":
                await handle_create_room_event(event_data)


async def handle_join_room_event(websocket: WebSocket, user_id: str, event_data: dict):
    """유저가 방에 참여하는 이벤트 처리"""
    room_id = event_data["room_id"]

    messages = await get_all_messages(room_id)
    await websocket.send_json({"event": "messages", "messages": messages})

    if not await is_user_in_room(user_id, room_id):
        await add_user_to_room(room_id, user_id)
        await add_user_to_room_in_db(room_id, user_id)
        await notify_room_participants(room_id, "님이 방에 참여했습니다.", user_id)


async def handle_chat_message_event(user_id: str, event_data: dict):
    """채팅 메시지를 처리하고 다른 사용자에게 전달"""
    room_id = event_data["room_id"]
    message_content = event_data["content"]

    await handle_message(room_id, message_content, user_id)
    await notify_room_participants(room_id, message_content, user_id)


async def handle_create_room_event(event_data: dict):
    """새로운 채팅방을 생성하고 클라이언트들에게 알림"""
    title = event_data["title"]
    room_id = await create_room(title)

    await notify_all_clients(
        {"event": "room_created", "room_id": room_id, "title": title}
    )


async def notify_room_participants(room_id: str, message: str, sender: str):
    """방에 있는 모든 사용자에게 메시지를 전송"""
    participants = await get_room_participants(room_id)
    for participant_id in participants:
        if participant_id in connected_clients:
            await connected_clients[participant_id].send_json(
                {
                    "event": "message",
                    "message": message,
                    "sender": sender,
                    "room_id": room_id,
                    "timestamp": datetime.now().isoformat(),
                }
            )


async def notify_all_clients(event_data: dict):
    """모든 클라이언트에게 이벤트 알림"""
    for client in connected_clients.values():
        await client.send_json(event_data)


async def is_user_in_room(user_id: str, room_id: str) -> bool:
    """사용자가 해당 방에 이미 참여 중인지 확인"""
    user_rooms = await get_user_rooms_from_redis(user_id)
    return room_id in user_rooms


async def handle_disconnect(user_id: str):
    """클라이언트 연결이 끊겼을 때 처리"""
    if user_id in connected_clients:
        del connected_clients[user_id]

    user_rooms = await get_user_rooms_from_redis(user_id)
    for room_id in user_rooms:
        await remove_user_from_room(room_id, user_id)
        await notify_room_participants(
            room_id, f"{user_id}님이 방을 떠났습니다.", user_id
        )


async def log_status():
    """주기적으로 WebSocket 연결 상태를 로그로 출력"""
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass


async def get_user_rooms_from_redis(user_id: str):
    # 모든 방의 사용자 목록에서 해당 사용자를 포함하는 방만 선택
    room_keys = await redis.keys("room:*:users")
    user_rooms = []
    for room_key in room_keys:
        if await redis.zscore(room_key, user_id):
            room_id = room_key.split(":")[1]
            user_rooms.append(room_id)
    return user_rooms


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
