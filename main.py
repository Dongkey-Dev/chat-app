from fastapi import FastAPI

from app.routes import chat

app = FastAPI()

# 라우터 등록
app.include_router(chat.router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
