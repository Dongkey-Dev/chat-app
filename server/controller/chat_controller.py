from fastapi import APIRouter, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from service.chat_service import (
    create_chat_room,
    get_chat_rooms,
    manage_websocket_connection,
)

router = APIRouter()


@app.get("/client")
async def client(request: Request):
    return templates.TemplateResponse("client.html", {"request": request})


@router.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await manage_websocket_connection(websocket, room_id)


@router.post("/chatrooms")
async def create_chat_room_endpoint(title: str):
    return create_chat_room(title)


@router.get("/chatrooms")
async def get_chat_rooms_endpoint():
    return get_chat_rooms()
