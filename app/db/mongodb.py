from motor.motor_asyncio import AsyncIOMotorClient
import os

mongodb_host = os.getenv("MONGO_HOST", "localhost")
mongodb_port = int(os.getenv("MONGO_PORT", 27017))

mongo_client = AsyncIOMotorClient(f"mongodb://{mongodb_host}:{mongodb_port}/")
chat_db = mongo_client["chat_database"]
