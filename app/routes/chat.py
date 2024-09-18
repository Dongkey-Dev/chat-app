from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
import json

from fastapi.templating import Jinja2Templates

from app.service.chat_service import ChatService

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/chatrooms")
async def get_chat_rooms_endpoint():
    return await ChatService.get_chat_rooms()


@router.get("/client")
async def client(request: Request):
    return templates.TemplateResponse("client.html", {"request": request})


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """WebSocket 연결 핸들러"""
    await websocket.accept()
    await ChatService.add_client(user_id, websocket)

    try:
        await send_initial_data(websocket, user_id)
        await handle_messages(websocket, user_id)
    except WebSocketDisconnect:
        await handle_disconnect(user_id)


async def send_initial_data(websocket: WebSocket, user_id: str):
    """초기 연결 시 방 목록 전송"""
    room_list = await ChatService.get_chat_rooms()
    await websocket.send_json(
        {"event": "connected", "user_id": user_id, "rooms": room_list}
    )


async def handle_messages(websocket: WebSocket, user_id: str):
    """메시지 처리 핸들러"""
    while True:
        data = await websocket.receive_text()
        event_data = json.loads(data)
        match event_data.get("type"):
            case "join_room":
                await handle_join_room_event(websocket, user_id, event_data)
            case "message":
                await handle_chat_message_event(user_id, event_data)
            case "create_room":
                await handle_create_room_event(event_data)


async def handle_join_room_event(websocket: WebSocket, user_id: str, event_data: dict):
    room_id = event_data["room_id"]
    messages = await ChatService.get_all_messages(room_id)
    await websocket.send_json({"event": "messages", "messages": messages})

    if room_id not in await ChatService.get_user_rooms_from_redis(user_id):
        await ChatService.add_user_to_room(room_id, user_id)
        await ChatService.notify_room_participants(
            room_id, "님이 방에 참여했습니다.", user_id
        )


async def handle_chat_message_event(user_id: str, event_data: dict):
    room_id = event_data["room_id"]
    message_content = event_data["content"]

    await ChatService.save_message(room_id, message_content, user_id)
    await ChatService.notify_room_participants(room_id, message_content, user_id)


async def handle_create_room_event(event_data: dict):
    title = event_data["title"]
    room_id = await ChatService.create_room(title)
    await ChatService.notify_all_clients(
        {"event": "room_created", "room_id": room_id, "title": title}
    )


async def handle_disconnect(user_id: str):
    await ChatService.remove_client(user_id)
    user_rooms = await ChatService.get_user_rooms_from_redis(user_id)
    for room_id in user_rooms:
        await ChatService.remove_user_from_room(room_id, user_id)
        await ChatService.notify_room_participants(
            room_id, "님이 방을 떠났습니다.", user_id
        )
