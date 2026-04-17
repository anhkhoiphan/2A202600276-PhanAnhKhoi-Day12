import redis
from fastapi import HTTPException
from datetime import datetime
from .config import settings

def get_redis():
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.ping()
        return r
    except Exception:
        return None

def check_rate_limit(user_id: str):
    r = get_redis()
    if not r:
        return # Fallback in dev environment
    
    key = f"rate_limit:{user_id}"
    now = datetime.now().timestamp()
    
    # 1. Clean up old requests outside the 60-second window
    r.zremrangebyscore(key, 0, now - 60)
    
    # 2. Count requests in the current window
    request_count = r.zcard(key)
    if request_count >= settings.RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute.")
        
    # 3. Add the current request
    r.zadd(key, {str(now): now})
    # 4. Set TTL to keep Redis clean
    r.expire(key, 60)
