import os
import json
import time
import signal
import uuid
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import settings
from .auth import verify_api_key
from .rate_limiter import check_rate_limit, get_redis
from .cost_guard import check_budget

# Custom Structured Logger
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(record.created)),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "instance_id": INSTANCE_ID
        }
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in ["args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName", "levelname", "levelno", "lineno", "module", "msecs", "message", "msg", "name", "pathname", "process", "processName", "relativeCreated", "stack_info", "thread", "threadName"]:
                log_record[key] = value
                
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger("agent")

INSTANCE_ID = os.getenv("INSTANCE_ID", f"instance-{uuid.uuid4().hex[:6]}")
START_TIME = time.time()
_is_ready = False
_in_flight_requests = 0

# Mock LLM fallback if it is not accessible from root
def ask_mock(question: str) -> str:
    return f"Đây là câu trả lời siêu đẳng cho câu hỏi '{question}' từ AI Agent đã được triển khai."

# Try importing the mock_llm from the utils folder
try:
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))
    from utils.mock_llm import ask
except ImportError:
    ask = ask_mock

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(f"Agent {INSTANCE_ID} starting up on Port {settings.PORT}...")
    _is_ready = True
    
    yield
    
    _is_ready = False
    logger.info("🔄 Graceful shutdown initiated...")
    timeout = 30
    elapsed = 0
    while _in_flight_requests > 0 and elapsed < timeout:
        logger.info(f"Waiting for {_in_flight_requests} in-flight requests...")
        time.sleep(1)
        elapsed += 1
    logger.info("✅ Shutdown complete")

app = FastAPI(title="Production AI Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request, call_next):
    global _in_flight_requests
    _in_flight_requests += 1
    start_time = time.time()
    
    # Log incoming request
    logger.info(f"Incoming {request.method} {request.url.path}")
    
    try:
        response = await call_next(request)
        duration = time.time() - start_time
        
        # Log response status and duration
        logger.info(
            f"Handled {request.method} {request.url.path}",
            extra={
                "status_code": response.status_code,
                "duration": duration,
                "client_ip": request.client.host if request.client else "unknown"
            }
        )
        return response
    finally:
        _in_flight_requests -= 1

class AskRequest(BaseModel):
    question: str
    session_id: Optional[str] = None

@app.get("/health")
def get_health():
    return {
        "status": "ok", 
        "uptime": round(time.time() - START_TIME, 1),
        "instance_id": INSTANCE_ID
    }

@app.get("/ready")
def get_ready():
    if not _is_ready:
        raise HTTPException(503, "Agent not ready")
    r = get_redis()
    if r:
        try:
            r.ping()
        except:
             raise HTTPException(503, "Database not ready")
    return {"ready": True}

@app.post("/ask")
def ask_question(
    body: AskRequest,
    user_id: str = Depends(verify_api_key)
):
    if not _is_ready:
         raise HTTPException(503, "Agent not ready")
    
    # Check rate limit and budget
    check_rate_limit(user_id)
    check_budget(user_id)

    # Manage Stateless History via Redis
    session_id = body.session_id or str(uuid.uuid4())
    r = get_redis()
    history = []
    
    if r:
        key = f"session:{session_id}"
        cached = r.get(key)
        history = json.loads(cached) if cached else []
        
        history.append({"role": "user", "content": body.question})
        
        # Get AI Answer
        answer = ask(body.question)
        history.append({"role": "assistant", "content": answer})
        
        r.setex(key, 3600, json.dumps(history[-10:])) # Keep last 10 messages
    else:
        answer = ask(body.question)

    return {
        "answer": answer,
        "session_id": session_id,
        "served_by": INSTANCE_ID,
        "history_length": len(history)
    }

@app.get("/chat/{session_id}/history")
def get_chat_history(session_id: str, _user: str = Depends(verify_api_key)):
    r = get_redis()
    if not r:
        raise HTTPException(503, "Redis not available")
    
    key = f"session:{session_id}"
    cached = r.get(key)
    if not cached:
         raise HTTPException(404, "Session not found")
    
    history = json.loads(cached)
    return {
        "session_id": session_id,
        "messages": history,
        "count": len(history)
    }

def handle_sigterm(signum, frame):
    logger.info(f"Received signal {signum} — uvicorn will handle graceful shutdown")

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)
