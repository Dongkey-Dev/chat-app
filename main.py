from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.openapi.utils import get_openapi

from controller.chat_controller import router

app = FastAPI()
templates = Jinja2Templates(directory="templates")


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="WebSocket API",
        version="1.0.0",
        description="This is a simple WebSocket API",
        routes=app.routes,
    )

    # WebSocket 경로 수동 추가
    openapi_schema["paths"]["/ws/{room_id}"] = {
        "get": {
            "summary": "WebSocket connection",
            "description": "Connect to the WebSocket server for a specific room. Send a message and receive a response.",
            "parameters": [
                {
                    "name": "room_id",
                    "in": "path",
                    "required": True,
                    "description": "ID of the chat room to connect to",
                    "schema": {"type": "string"},
                }
            ],
            "responses": {
                "101": {
                    "description": "Switching Protocols - The client is switching protocols as requested by the server.",
                },
                "200": {"description": "Connection established successfully"},
                "400": {"description": "Invalid room ID"},
            },
        }
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
app.include_router(router)
