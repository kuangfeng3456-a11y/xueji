"""端到端接口自检：逐个页面核心动作打真实后端，打印非 2xx。"""

import json
import os
from datetime import date, timedelta

import httpx

BASE = "http://127.0.0.1:8146"
client = httpx.Client(base_url=BASE, timeout=180)

login = client.post("/api/auth/login", json={"username": "demo", "password": os.getenv("SEED_DEMO_PASSWORD", "")})
token = login.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

results = []


def call(method, path, **kwargs):
    resp = client.request(method, path, headers=H, **kwargs)
    ok = resp.status_code < 400
    results.append((resp.status_code, method, path, "" if ok else resp.text[:200]))
    print(("OK " if ok else "FAIL "), resp.status_code, method, path, "" if ok else resp.text[:200])
    if ok:
        try:
            return resp.json()
        except Exception:
            return None
    return None


goals = call("GET", "/api/goals") or []
goal = None
if goals:
    goal = goals[0]
else:
    goal = call(
        "POST",
        "/api/goals",
        json={
            "exam_name": "功能验证四级",
            "exam_date": (date.today() + timedelta(days=60)).isoformat(),
            "daily_minutes": 60,
        },
    )
gid = goal["id"]

call(
    "POST",
    f"/api/goals/{gid}/materials/text",
    json={"filename": "功能验证资料", "content": "# 听力\n- 短对话\n- 长对话\n# 阅读\n- 仔细阅读"},
)
call("POST", f"/api/goals/{gid}/plan", json={"days": 3})
call("POST", f"/api/goals/{gid}/quiz/generate", json={"count": 2})
points = call("GET", f"/api/goals/{gid}/knowledge-points") or []
if isinstance(points, dict):
    points = points.get("knowledge_points", [])
kp = points[0]["id"] if points else None
call("POST", f"/api/goals/{gid}/mistakes", json={"question": "He ____ here since 2020.", "user_answer": "lives", "correct_answer": "has lived", "kp_id": kp})
deck = call("GET", f"/api/goals/{gid}/flashcards") or {}
cards = deck.get("cards") or []
if cards:
    call("POST", f"/api/goals/{gid}/flashcards/{cards[0]['kp_id']}/review", json={"remembered": True})
call("POST", f"/api/goals/{gid}/reports", json={})
call("POST", f"/api/goals/{gid}/probes/generate", json={"kind": "probe", "count": 1})
call("POST", f"/api/goals/{gid}/freshness/scan", json={})
call("POST", f"/api/goals/{gid}/panel/review", json={"topic": "功能验证：今天该不该加题"})
call("GET", f"/api/goals/{gid}/risks")
call("POST", f"/api/goals/{gid}/documents/reindex", json={})
call("POST", f"/api/goals/{gid}/documents/search", json={"query": "听力", "top_k": 3})
call("POST", f"/api/goals/{gid}/experiments", json={"strategy": "read", "days": 3})
call("POST", f"/api/goals/{gid}/consent", json={"scope": "parent_report", "granted": True})
call("GET", f"/api/goals/{gid}/parent-report")
call("POST", "/api/psychology/assess", json={"scale": "phq9", "answers": [0] * 9})

cls = call("POST", "/api/classes", json={"name": "功能验证班", "description": "E2E 自检"})
if cls:
    call("GET", f"/api/classes/{cls['id']}/teacher-dashboard")
call("GET", "/api/classes")

register = client.post("/api/auth/register", json={"username": "verifybuddy", "password": "secret123", "nickname": "伙伴"})
call("POST", "/api/buddies", json={"username": "verifybuddy"})

call("POST", "/api/prompts/sync")
call("POST", "/api/eval/run?limit=2", json={})
call("POST", "/api/integrations/test?force=false")

failures = [r for r in results if r[0] >= 400]
print("\nSUMMARY", len(results), "calls,", len(failures), "failures")
for item in failures:
    print("FAIL", item)
