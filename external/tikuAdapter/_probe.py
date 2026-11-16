import json, time, urllib.request

BASE = "http://127.0.0.1:8060/adapter-service/search"

CASES = [
    {"question": "我国现行宪法规定，中华人民共和国的一切权力属于（）",
     "options": ["人民", "公民", "全国人民代表大会", "中国共产党"], "type": 0},
    {"question": "下列属于计算机输入设备的是（）",
     "options": ["显示器", "键盘", "打印机", "音箱"], "type": 0},
    {"question": "TCP协议是面向连接的可靠传输协议", "options": [], "type": 3},
    {"question": "商品的两个基本属性是（）",
     "options": ["使用价值和价值", "价值和交换价值", "具体劳动和抽象劳动", "私人劳动和社会劳动"], "type": 0},
    {"question": "中国共产党成立于哪一年", "options": [], "type": 2},
]

ok = 0
for i, c in enumerate(CASES, 1):
    body = json.dumps(c, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE, data=body, headers={"Content-Type": "application/json; charset=utf-8"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode("utf-8"))
        ans = d.get("answer") or {}
        got = ans.get("bestAnswer") or []
        cost = time.time() - t0
        flag = "OK " if got else "MISS"
        if got:
            ok += 1
        print(f"[{flag}] {i}. {c['question'][:28]}... -> {got} ({cost:.1f}s)")
    except Exception as e:
        print(f"[ERR ] {i}. {c['question'][:28]}... -> {type(e).__name__}: {e}")

print(f"\n命中 {ok}/{len(CASES)}")
