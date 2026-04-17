import json
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8080"
API_KEY = "my-super-secret-key"

def post(path: str, data: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(data).encode(),
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def get(path: str) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers={"X-API-Key": API_KEY},
        method="GET",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

print("=" * 60)
print("FINAL PROJECT: Production AI Agent Test")
print("=" * 60)

questions = [
    "What is your name?",
    "How can you help me?",
    "Tell me a joke.",
    "What are you doing now?",
    "Bye!"
]

session_id = None
instances_seen = set()

for i, question in enumerate(questions, 1):
    try:
        result = post("/ask", {
            "question": question,
            "session_id": session_id,
        })
        
        if session_id is None:
            session_id = result["session_id"]
            print(f"Created Session: {session_id}\n")

        instance = result.get("served_by", "unknown")
        instances_seen.add(instance)
        print(f"[{i}] Q: {question}")
        print(f"    Agent ({instance}): {result['answer']}")
        print("-" * 10)
    except urllib.error.HTTPError as e:
        print(f"Error {e.code}: {e.read().decode()}")
        break

print(f"\nSummary:")
print(f"- Total Requests: {len(questions)}")
print(f"- Unique Instances Visited: {instances_seen}")
if len(instances_seen) > 1:
    print(f"✅ Load Balancing Successful!")
else:
    print(f"ℹ️ Only 1 instance responded. (Scaling check needed)")

print("\n--- History Verification ---")
try:
    history = get(f"/chat/{session_id}/history")
    print(f"Successfully retrieved history for {session_id}")
    print(f"Total messages: {history['count']}")
    for msg in history["messages"][-2:]:
        print(f"  [{msg['role']}]: {msg['content']}")
    print("\n✅ Final Project PASSED Verification!")
except Exception as e:
    print(f"❌ History verification failed: {e}")
