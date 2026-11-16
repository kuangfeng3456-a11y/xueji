import json, subprocess, time, urllib.request, base64, os
import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9223
OUT = r"D:\90\external\tikuAdapter"
profile = os.path.join(OUT, "_cdpprofile")

proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                         f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
                         "--window-size=1440,1000", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def wait_ws():
    for _ in range(40):
        try:
            d = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=2))
            for t in d:
                if t.get("type") == "page":
                    return t["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("no devtools")

ws = websocket.create_connection(wait_ws(), timeout=30)
mid = [0]
def cmd(method, **params):
    mid[0] += 1
    ws.send(json.dumps({"id": mid[0], "method": method, "params": params}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == mid[0]:
            return m.get("result", {})

def js(expr):
    r = cmd("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
    return r.get("result", {}).get("value")

cmd("Page.enable"); cmd("Runtime.enable")
cmd("Page.navigate", url="http://127.0.0.1:8060/")
time.sleep(3)

# 填表并提交
js("""(() => {
  const inputs = [...document.querySelectorAll('input')];
  const set = (el, v) => {
    el.value = v;
    el.dispatchEvent(new Event('input', {bubbles:true}));
    el.dispatchEvent(new Event('change', {bubbles:true}));
  };
  if (inputs[0]) set(inputs[0], 'admin');
  if (inputs[1]) set(inputs[1], '123456');
  return inputs.length;
})()""")
time.sleep(0.5)
js("""(() => {
  const btns = [...document.querySelectorAll('button')];
  const b = btns.find(x => (x.innerText||'').includes('登')) || btns[0];
  if (b) b.click();
  return b ? b.innerText : 'none';
})()""")
time.sleep(3.5)

print("URL:", js("location.href"))
print("TOKEN:", (js("localStorage.getItem('token') || document.cookie") or "")[:40])
print("BODY:", (js("document.body.innerText") or "")[:600])

shot = cmd("Page.captureScreenshot", format="png")
open(os.path.join(OUT, "ui_dash.png"), "wb").write(base64.b64decode(shot["data"]))
print("screenshot saved")
ws.close(); proc.terminate()
