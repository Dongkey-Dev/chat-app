from typing import List
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from service import chat_service

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# 클라이언트 페이지 렌더링
@router.get("/client")
async def client(request: Request):
    return templates.TemplateResponse("client2.html", {"request": request})


# 웹소켓 핸들러
@router.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()

    # Redis에서 AI 기반으로 userId 발급
    user_id = await chat_service.get_ai_generated_user_id()

    # 사용자 ID를 이용해 채팅방에 추가
    await chat_service.add_user_to_room(room_id, user_id)

    try:
        while True:
            data = await websocket.receive_text()
            await chat_service.handle_message(room_id, data)
    except WebSocketDisconnect:
        await chat_service.remove_user_from_room(room_id, user_id)


# 채팅방 생성 요청 모델
class CreateChatRoomRequest(BaseModel):
    title: str


# 채팅방 생성
@router.post("/chatrooms")
async def create_chat_room(request: CreateChatRoomRequest):
    try:
        room = await chat_service.create_chat_room(request.title, request.participants)
        return {"message": "채팅방이 생성되었습니다.", "room": room}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# 채팅방 목록 조회
@router.get("/chatrooms")
async def get_chat_rooms():
    return await chat_service.get_chat_rooms()
