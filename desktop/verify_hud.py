"""Headless verification that the HUD renders the full reference view on LIVE core data.
Serves the built dist, drives every tab, asserts live /api/* content (no demo markers),
and writes one screenshot per tab to desktop/_verify/.

Usage:  python verify_hud.py [hud_url] [api_base]
Default: serves ../dist on :8090 against the live core on :8000.
"""
import functools
import http.server
import os
import socketserver
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.join(os.path.dirname(__file__), "dist")
PORT = 8090
API = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
# App-level auth gates /api now → load the page SAME-ORIGIN from the core (so the
# session cookie is sent) and inject a valid owner token into the browser context.
HUD = sys.argv[1] if len(sys.argv) > 1 else f"{API}/index.html"
OUT = os.path.join(os.path.dirname(__file__), "_verify")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.core import webauth  # noqa: E402

TOKEN = webauth.issue(webauth.current_login())


def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    httpd = serve() if ("127.0.0.1:%d" % PORT) in HUD else None
    checks, errors = {}, []
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--ignore-gpu-blocklist"])
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        ctx.add_cookies([{"name": webauth.COOKIE, "value": TOKEN, "url": API}])
        pg = ctx.new_page()
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto(HUD)
        pg.wait_for_function("window.__noirReady === true", timeout=15000)
        pg.wait_for_timeout(3500)

        checks["brand = live /api/core name"] = "BLACK NOIR" in pg.inner_text("#brand").upper()
        checks["core connection online"] = "online" in pg.inner_text("#conn")
        checks["map: 2D schema svg present"] = pg.locator("#s2svg").count() > 0
        checks["map: schema links+nodes"] = pg.locator("#s2svg line.lnk").count() >= 6 and pg.locator("#s2svg circle.nd").count() >= 7
        checks["map: clusters C1..C6"] = "C1" in pg.inner_text("#s2chips") and "C6" in pg.inner_text("#s2chips")
        checks["map: packet layer present"] = pg.locator("#s2pkts").count() > 0
        checks["map: ACTIVE counter"] = "ACTIVE" in pg.inner_text("#s2act")
        checks["map: pulsing/live nodes"] = pg.locator("#s2svg circle.nd.live").count() > 0
        pg.screenshot(path=os.path.join(OUT, "1-map.png"))

        pg.click("#s2svg [data-core]"); pg.wait_for_timeout(700)
        pg.eval_on_selector_all("#mv-tabs .mvtab", "els=>{for(const e of els) if(e.textContent.includes('4 ИИ')) e.click();}"); pg.wait_for_timeout(500)
        checks["map: core dashboard = 4 AI"] = "Оркестратор" in pg.inner_text("#mv-body") and "Builder" in pg.inner_text("#mv-body")
        pg.screenshot(path=os.path.join(OUT, "1b-core-ai.png"))
        pg.click("#mv-x")

        def tab(name):
            pg.click(f".tab[data-go={name}]"); pg.wait_for_timeout(700)

        tab("tasks")
        checks["tasks: kanban + done"] = "В ОЧЕРЕДИ" in pg.inner_text("#tasks") and "ВЫПОЛНЕНО" in pg.inner_text("#tasks")
        pg.screenshot(path=os.path.join(OUT, "2-tasks.png"))

        tab("chat")
        checks["chat: voice equalizer + visual btn"] = pg.locator("#eq").count() > 0 and pg.locator("#visual").count() > 0
        checks["chat: channels (mediator/core/cc/council)"] = pg.locator(".chtab").count() == 4 and "ПЕРЕДАТЧИК" in pg.inner_text(".chsw") and "СОВЕТ" in pg.inner_text(".chsw")
        pg.click("#visual"); pg.wait_for_timeout(800)
        checks["chat: visual face window opens"] = pg.locator("#facewin.on").count() > 0
        pg.screenshot(path=os.path.join(OUT, "3-chat.png"))
        pg.click("#faceclose"); pg.wait_for_timeout(300)
        checks["chat: face window closes"] = pg.locator("#facewin.on").count() == 0
        # channel switch persists view
        pg.click(".chtab[data-ch=core]"); pg.wait_for_timeout(300)
        checks["chat: channel switch works"] = pg.locator(".chtab[data-ch=core].on").count() == 1

        tab("sys")
        checks["systems: live host metrics"] = "CPU" in pg.inner_text("#metrics") and "RAM" in pg.inner_text("#metrics")
        checks["systems: governor audit"] = "GOVERNOR" in pg.inner_text("#gov")
        checks["systems: self-analysis card"] = "САМОАНАЛИЗ" in pg.inner_text("#selfan")
        pg.screenshot(path=os.path.join(OUT, "4-systems.png"))

        tab("ideas")
        checks["ideas: 3 columns"] = all(s in pg.inner_text("#ideacols") for s in ["НА РАЗБОРЕ", "ХОРОШИЕ", "ПЛОХИЕ"])
        checks["ideas: intake bar"] = pg.locator("#iadd").count() > 0
        pg.screenshot(path=os.path.join(OUT, "5-ideas.png"))

        tab("prof")
        pt = pg.inner_text("#prof")
        checks["profile: 5 sections"] = all(s in pt for s in ["ДОМЕНЫ", "МЕТРИКИ", "ГИПОТЕЗЫ", "ЗДОРОВЬЕ", "РАСПИСАНИЕ"])
        pg.screenshot(path=os.path.join(OUT, "6-profile.png"))

        checks["companion VOLT-BRO"] = "VOLT-BRO" in pg.inner_text(".vbro")
        tab("map"); pg.click("#theme"); pg.wait_for_timeout(600)
        checks["theme gold toggle"] = pg.locator("#px.gold").count() > 0
        pg.screenshot(path=os.path.join(OUT, "7-map-gold.png"))

        b.close()
    if httpd:
        httpd.shutdown()

    ok = all(checks.values())
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print("\nconsole errors:", errors[:5] if errors else "none")
    print("screenshots ->", OUT)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
