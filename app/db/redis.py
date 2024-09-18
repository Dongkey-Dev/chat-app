from redis.asyncio import Redis
import os

redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))

redis = Redis(host=redis_host, port=redis_port, decode_responses=True)
