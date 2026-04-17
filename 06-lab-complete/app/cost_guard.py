from datetime import datetime
from fastapi import HTTPException
from .config import settings
from .rate_limiter import get_redis

def check_budget(user_id: str, estimated_cost: float = 0.005) -> bool:
    r = get_redis()
    if not r:
        return True # Fallback in dev

    month_key = datetime.now().strftime("%Y-%m")
    key = f"budget:{user_id}:{month_key}"
    
    current = float(r.get(key) or 0)
    if current + estimated_cost > settings.MONTHLY_BUDGET_USD:
        raise HTTPException(
            status_code=402, 
            detail=f"Budget exceeded limit! Current spend: ${current:.4f}"
        )
    
    r.incrbyfloat(key, estimated_cost)
    r.expire(key, 32 * 24 * 3600)  # Giữ data 32 ngày
    
    return True
