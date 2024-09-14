import json
import os

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pymongo import MongoClient
from redis import Redis

app = FastAPI()
redis_host = os.getenv("REDIS_HOST", "http://localhost")
redis_port = os.getenv("REDIS_PORT", "6379")
mongodb_host = os.getenv("MONGO_HOST", "http://localhost")
mongodb_port = os.getenv("MONGO_PORT", "27017")
redis = Redis(host=redis_host, port=redis_port, decode_responses=True)
mongo = MongoClient(f"mongodb://{mongodb_host}:{mongodb_port}/")

connections = {}


@app.get("/client")
async def client(request: Request):
    return templates.TemplateResponse("client.html", {"request": request})


@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()

    # 접속자 수 관리
    redis.sadd(f"room:{room_id}:users", websocket.client.host)
    redis.expire(f"room:{room_id}:users", 1800)  # 30분 TTL 설정

    try:
        while True:
            data = await websocket.receive_text()
            redis.rpush(f"room:{room_id}:messages", data)
            redis.publish(f"room:{room_id}", data)
    except WebSocketDisconnect:
        redis.srem(f"room:{room_id}:users", websocket.client.host)


@app.get("/chatrooms")
async def get_chat_rooms():
    room_keys = redis.keys("room:*:users")
    rooms = []

    for key in room_keys:
        room_id = key.split(":")[1]
        user_count = redis.scard(key)
        latest_message = redis.lrange(f"room:{room_id}:messages", -1, -1)
        rooms.append(
            {
                "room_id": room_id,
                "user_count": user_count,
                "latest_message": latest_message,
            }
        )

    # 30분 내 접속자 수로 정렬
    rooms.sort(key=lambda x: x["user_count"], reverse=True)
    return rooms
