from fastapi import Header, HTTPException
from .config import settings

def verify_api_key(x_api_key: str = Header(..., description="API Key Authentication")):
    if x_api_key != settings.AGENT_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )
    return "authorized_user"
