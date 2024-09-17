import uuid
from repository import chat_repository


async def add_user_to_room(room_id: str, user_id: str):
    await chat_repository.add_user_to_room(room_id, user_id)
    await chat_repository.set_room_user_expiration(room_id)


# 사용자를 채팅방에서 제거
async def remove_user_from_room(room_id: str, user_id: str):
    await chat_repository.remove_user_from_room(room_id, user_id)


# 메시지를 저장하고 발행
async def handle_message(room_id: str, message: str):
    await chat_repository.save_message(room_id, message)
    await chat_repository.publish_message(room_id, message)


# 채팅방 목록 조회
async def get_chat_rooms():
    return await chat_repository.get_chat_rooms()


# 채팅방 생성
async def create_chat_room(title: str):
    return await chat_repository.create_chat_room(title)


# 특정 채팅방 정보 조회
async def get_chat_room(room_id: str):
    return await chat_repository.get_chat_room(room_id)


# 특정 채팅방 메시지 조회
async def get_messages(room_id: str, limit: int = 50):
    return await chat_repository.get_messages(room_id, limit)


async def regist_user():
    await chat_repository.regist_user()


# 사용자의 채팅방 세션 만료 설정 (새로운 함수 추가)
async def set_room_user_expiration(room_id: str):
    await chat_repository.set_room_user_expiration(room_id)


async def get_or_create_user_id():
    user_id = await chat_repository.get_user_id()
    if not user_id:
        user_id = str(uuid.uuid4())  # 새로운 UUID 생성
        await chat_repository.save_user_id(user_id)
    return user_id
