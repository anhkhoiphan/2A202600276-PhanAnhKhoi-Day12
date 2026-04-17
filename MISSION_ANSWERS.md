Student Name: Phan Anh Khôi
Student ID: 2A202600276
Date: 17/04/2026

# Day 12 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found
1. API key hardcode trong code: Nếu push lên Github sẽ bị lộ ngay lập tức
2. Không có config management
3. Print thay vì proper logging
4. Không có health check endpoint. Nếu agent crash, platform không biết để restart.
5. Port cố định — không đọc từ environment. Trên Railway/Render, PORT được inject qua env var

### Exercise 1.3: Comparison table
| Feature        | Develop     | Production  | Why Important? |
|----------------|------------|-------------|----------------|
| Config         | Hardcode    | Env vars    | Tách config khỏi code giúp linh hoạt deploy nhiều môi trường và bảo mật thông tin nhạy cảm (API key, DB). |
| Health check   | Không       | Có          | Giúp hệ thống (load balancer, orchestrator) biết service còn sống hay không để tự động restart hoặc route traffic. |
| Logging        | print()     | JSON        | Logging có cấu trúc giúp dễ parse, tìm kiếm và monitor |
| Shutdown       | Đột ngột     | Graceful    | Đảm bảo xử lý nốt request đang chạy, đóng kết nối sạch sẽ, tránh mất dữ liệu hoặc lỗi hệ thống. |
...

## Part 2: Docker

### Exercise 2.1: Dockerfile questions
1. Base image: python:3.11
2. Working directory: /app
...

### Exercise 2.3: Image size comparison
- Develop: 1.66 GB
- Production: 236.44 MB
- Difference: (giảm) 85.8%

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment
- URL: https://lab12vinuniproject-production.up.railway.app/
- Screenshot: https://prnt.sc/Jqkkc1beHn-e


## Part 4: API Security

### Exercise 4.1-4.3: Test result

#### 1. API key được check ở đâu?

API key được kiểm tra trong hàm `verify_api_key`, đóng vai trò là một **FastAPI Dependency**. Hàm này thực hiện hai bước xác thực: trước tiên kiểm tra header `X-API-Key` có tồn tại không, sau đó so sánh giá trị với key được lưu trong biến môi trường.

Hàm không tự chạy mà chỉ được kích hoạt khi được inject vào endpoint thông qua `Depends()`. Các endpoint không khai báo dependency này như `/health` và `/` là public hoàn toàn, không qua bất kỳ bước xác thực nào.

---

### 2. Điều gì xảy ra nếu sai key?

Có hai trường hợp với kết quả khác nhau:

| Tình huống | HTTP Status | Ý nghĩa |
|---|---|---|
| Không gửi header `X-API-Key` | `401 Unauthorized` | Chưa xác thực |
| Gửi key nhưng sai giá trị | `403 Forbidden` | Xác thực rồi nhưng không có quyền |

Việc phân biệt 401 và 403 là đúng chuẩn REST: 401 dành cho request chưa cung cấp thông tin xác thực, 403 dành cho request đã xác thực nhưng không được cấp quyền truy cập.

---

### 3. Làm sao rotate key?

Hiện tại code chỉ lưu một key duy nhất từ env var, không hỗ trợ rotate trực tiếp. Có hai hướng xử lý:

**Cách 1 — Đổi env var:** Cập nhật `AGENT_API_KEY` trên Render Dashboard rồi redeploy. Đơn giản nhưng có downtime ngắn trong lúc service khởi động lại, và toàn bộ client phải đổi key đồng thời.

**Cách 2 — Hỗ trợ nhiều key song song:** Sửa logic để đọc danh sách key từ env var, phân cách bởi dấu phẩy, và kiểm tra key gửi lên có nằm trong danh sách hợp lệ không. Cách này cho phép thêm key mới trong khi key cũ vẫn hoạt động, client có thời gian migrate, sau đó mới xóa key cũ. Không cần redeploy giữa các bước, chỉ update env var trên Render Dashboard.

### Exercise 4.4: Cost guard implementation

#### Approach

Cost guard được implement trong `app/cost_guard.py` với Redis làm storage để đảm bảo stateless — nhiều instances cùng track chính xác một con số.

**Key design:**
- Key Redis: `budget:{user_id}:{YYYY-MM}` — tự động reset sang tháng mới vì key mang tháng vào tên
- TTL: 32 ngày — đủ để data của tháng trước không bị xóa quá sớm
- Nếu Redis không sẵn sàng (dev environment): trả về `True` để không block developer

**Flow khi có request:**
1. Tính `estimated_cost` cho request (mặc định ~$0.005)
2. Đọc spending tháng hiện tại từ Redis
3. Nếu `current + estimated_cost > MONTHLY_BUDGET_USD` → raise `HTTP 402`
4. Ngược lại, `INCRBYFLOAT` trong Redis để cộng dồn

```python
# Key sẽ tự expire và reset mỗi tháng
month_key = datetime.now().strftime("%Y-%m")   # "2026-04"
key = f"budget:{user_id}:{month_key}"

current = float(r.get(key) or 0)
if current + estimated_cost > settings.MONTHLY_BUDGET_USD:
    raise HTTPException(status_code=402, detail=f"Budget exceeded! Current: ${current:.4f}")

r.incrbyfloat(key, estimated_cost)
r.expire(key, 32 * 24 * 3600)
```

**Tại sao Redis thay vì in-memory dict?**  
Khi scale ra 3 instances, mỗi instance có RAM riêng. Nếu dùng dict, user A gọi instance 1 và instance 2 sẽ có hai counter khác nhau — tổng chi tiêu thật có thể gấp đôi. Redis làm single source of truth cho toàn cluster.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks

Implement hai endpoints với mục đích khác nhau:

| Endpoint | Probe type | Mục đích |
|---|---|---|
| `GET /health` | Liveness | Container còn sống không? Platform restart nếu fail |
| `GET /ready` | Readiness | Sẵn sàng nhận traffic chưa? Load balancer bỏ qua nếu fail |

**Implementation trong `app/main.py`:**

```python
@app.get("/health")
def get_health():
    return {
        "status": "ok",
        "uptime": round(time.time() - START_TIME, 1),
        "instance_id": INSTANCE_ID   # giúp debug khi scale nhiều instance
    }

@app.get("/ready")
def get_ready():
    if not _is_ready:                    # flag được set sau khi startup xong
        raise HTTPException(503, "Agent not ready")
    r = get_redis()
    if r:
        try:
            r.ping()                     # check Redis connection
        except:
            raise HTTPException(503, "Database not ready")
    return {"ready": True}
```

**Test result:**
```bash
# Liveness — luôn 200 khi process còn sống
curl http://localhost:8000/health
# → {"status":"ok","uptime":12.3,"instance_id":"agent-a1b2"}

# Readiness — 200 sau startup, 503 nếu Redis chết
curl http://localhost:8000/ready
# → {"ready":true}
```

---

### Exercise 5.2: Graceful shutdown

**Vấn đề:** Khi container orchestrator (Railway, Kubernetes) cần dừng instance, nó gửi `SIGTERM`. Nếu không handle, process bị kill ngay lập tức — requests đang xử lý bị drop.

**Implementation:**

```python
def handle_sigterm(signum, frame):
    logger.info(f"Received signal {signum} — uvicorn will handle graceful shutdown")

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)
```

Uvicorn có built-in graceful shutdown: khi nhận SIGTERM, nó log sự kiện và dừng nhận request mới, đồng thời chờ các request đang xử lý hoàn thành (`timeout_graceful_shutdown=30`). Middleware theo dõi `_in_flight_requests` để biết bao nhiêu request đang chạy.

**Test:**
```bash
python app.py &
PID=$!

# Gửi request chậm đồng thời
curl http://localhost:8000/ask -X POST -d '{"question":"hello"}' &

# Kill ngay lập tức
kill -TERM $PID

# Quan sát: request vẫn hoàn thành trước khi process exit
```

---

### Exercise 5.3: Stateless design

**Anti-pattern (in-memory state):**
```python
# ❌ Khi scale ra 3 instances, mỗi instance có history riêng
conversation_history = {}

def ask(user_id, question):
    history = conversation_history.get(user_id, [])  # instance A có, instance B không có
```

**Implementation stateless với Redis:**

```python
# ✅ Tất cả instances đọc cùng một Redis
@app.post("/ask")
def ask_question(body: AskRequest, user_id: str = Depends(verify_api_key)):
    session_id = body.session_id or str(uuid.uuid4())
    r = get_redis()

    key = f"session:{session_id}"
    history = json.loads(r.get(key) or "[]")

    history.append({"role": "user", "content": body.question})
    answer = ask(body.question)
    history.append({"role": "assistant", "content": answer})

    r.setex(key, 3600, json.dumps(history[-10:]))  # giữ 10 messages cuối, TTL 1h
    return {"answer": answer, "session_id": session_id, "served_by": INSTANCE_ID}
```

Request 1 được instance A xử lý, request 2 của cùng session được instance B xử lý — cả hai đọc cùng history từ Redis, user không bị mất context.

---

### Exercise 5.4: Load balancing

**Stack docker-compose với Nginx làm load balancer:**

```yaml
nginx:
  image: nginx:alpine
  ports:
    - "8080:80"           # client → nginx
  volumes:
    - ./nginx.conf:/etc/nginx/nginx.conf:ro

agent:
  build: .
  deploy:
    replicas: 2           # hoặc --scale agent=3 khi chạy
```

**nginx.conf — round-robin:**
```nginx
upstream agent_cluster {
    server agent:8000;    # Docker resolve thành tất cả containers tên "agent"
}
```

**Test — quan sát `served_by` thay đổi qua các requests:**
```bash
docker compose up --scale agent=3

for i in {1..6}; do
  curl -s http://localhost:8080/ask -X POST \
    -H "X-API-Key: my-super-secret-key" \
    -H "Content-Type: application/json" \
    -d '{"question":"test"}' | python -m json.tool | grep served_by
done
```

Kết quả quan sát: `served_by` xoay vòng giữa 3 instance IDs khác nhau → Nginx đang phân tán traffic theo round-robin.

Nếu kill một instance (`docker kill <id>`), Nginx tự động bỏ qua instance đó sau khi health check fail — traffic chuyển về 2 instances còn lại.

---

### Exercise 5.5: Test stateless

**Kịch bản test:** Tạo conversation trên instance A, rồi gửi request tiếp theo đến instance B — history có còn không?

```bash
# Bước 1: Gửi câu hỏi đầu tiên, lấy session_id
RESPONSE=$(curl -s -X POST http://localhost:8080/ask \
  -H "X-API-Key: my-super-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"question":"Tên tôi là Khôi"}')

SESSION_ID=$(echo $RESPONSE | python -m json.tool | grep session_id | cut -d'"' -f4)
echo "Session: $SESSION_ID"

# Bước 2: Gọi lại với session_id — có thể hit instance khác
curl -s -X POST http://localhost:8080/ask \
  -H "X-API-Key: my-super-secret-key" \
  -H "Content-Type: application/json" \
  -d "{\"question\":\"Bạn có nhớ tên tôi không?\", \"session_id\":\"$SESSION_ID\"}"

# Bước 3: Xem history
curl -s http://localhost:8080/chat/$SESSION_ID/history \
  -H "X-API-Key: my-super-secret-key"
```

**Kết quả:** History vẫn còn dù request đi qua instances khác nhau → thiết kế stateless hoạt động đúng. State sống trong Redis, không phải trong bộ nhớ của bất kỳ instance nào.