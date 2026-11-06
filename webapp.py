"""Мини-приложение проверки доступа (как у Kuki)."""
import asyncio
import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

from aiohttp import web

from config import BOT_TOKEN, PORT
from database import get_user, set_verified

on_verified = None

PAGE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>Проверка</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
html,body{margin:0;height:100%}
body{display:flex;flex-direction:column;align-items:center;
justify-content:center;text-align:center;
font-family:-apple-system,system-ui,"Segoe UI",sans-serif;
background:var(--tg-theme-bg-color,#fff);color:var(--tg-theme-text-color,#111)}
h2{font-size:22px;margin:24px 0 8px}
p{margin:0;color:var(--tg-theme-hint-color,#666);font-size:16px}
.spin{width:56px;height:56px;border:5px solid #ddd;border-top-color:#2f8cf5;
border-radius:50%;animation:s 1s linear infinite}
@keyframes s{to{transform:rotate(360deg)}}
</style></head><body>
<div class="spin" id="spin"></div>
<h2 id="title">Проверяем доступ…</h2>
<p id="sub">Это займёт пару секунд</p>
<script>
var tg = window.Telegram.WebApp;
tg.ready(); tg.expand();
function raw(){
  try {
    return [screen.width, screen.height, screen.colorDepth,
      window.devicePixelRatio, navigator.language, navigator.platform,
      navigator.hardwareConcurrency || 0,
      Intl.DateTimeFormat().resolvedOptions().timeZone].join("|");
  } catch (e) { return ""; }
}
async function sha(s){
  try {
    var b = new TextEncoder().encode(s);
    var h = await crypto.subtle.digest("SHA-256", b);
    return Array.from(new Uint8Array(h)).map(function(x){
      return x.toString(16).padStart(2, "0");}).join("").slice(0, 32);
  } catch (e) { return ""; }
}
function done(ok){
  document.getElementById("spin").style.display = "none";
  if (ok) {
    document.getElementById("title").textContent = "Доступ открыт";
    document.getElementById("sub").textContent = "Возвращаемся в бота…";
    setTimeout(function(){ tg.close(); }, 1200);
  } else {
    document.getElementById("title").textContent = "Не удалось пройти проверку";
    document.getElementById("sub").textContent =
      "Закрой окно и нажми /start ещё раз";
  }
}
(async function(){
  try {
    var fp = await sha(raw());
    await new Promise(function(r){ setTimeout(r, 1500); });
    var r = await fetch("/api/verify", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({initData: tg.initData, fp: fp})});
    var j = await r.json();
    done(!!j.ok);
  } catch (e) { done(false); }
})();
</script></body></html>"""


def check_init_data(init_data):
    """Проверяет подпись Telegram. Возвращает данные пользователя или None."""
    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True))
        recv_hash = data.pop("hash", "")
        check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret = hmac.new(
            b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, recv_hash):
            return None
        if time.time() - int(data.get("auth_date", 0)) > 86400:
            return None
        return json.loads(data["user"])
    except Exception:
        return None


def client_ip(request):
    fwd = request.headers.get("X-Forwarded-For", "")
    return (fwd.split(",")[0].strip()
            or request.headers.get("X-Real-IP", "")
            or request.remote or "")


async def page(request):
    return web.Response(text=PAGE, content_type="text/html")


async def health(request):
    return web.Response(text="ok")


async def api_verify(request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False}, status=400)
    user = check_init_data(body.get("initData", ""))
    if not user:
        return web.json_response({"ok": False}, status=403)
    uid = user["id"]
    row = await get_user(uid)
    if not row:
        return web.json_response({"ok": False, "error": "start"}, status=404)
    ip_hash = hashlib.sha256(
        (client_ip(request) + BOT_TOKEN).encode()).hexdigest()[:16]
    fp = str(body.get("fp", ""))[:64]
    first = not row["verified"]
    await set_verified(uid, ip_hash, fp)
    if first and on_verified:
        asyncio.create_task(_safe_cb(uid))
    return web.json_response({"ok": True})


async def _safe_cb(uid):
    try:
        await on_verified(uid)
    except Exception:
        logging.exception("on_verified error")


async def start_server(callback):
    global on_verified
    on_verified = callback
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/verify", page)
    app.router.add_post("/api/verify", api_verify)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    logging.info("webapp listening on %s", PORT)
