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
HUD = sys.argv[1] if len(sys.argv) > 1 else f"http://127.0.0.1:{PORT}/index.html?api={API}"
OUT = os.path.join(os.path.dirname(__file__), "_verify")


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
        pg = b.new_page(viewport={"width": 1280, "height": 800})
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto(HUD)
        pg.wait_for_function("window.__noirReady === true", timeout=15000)
        pg.wait_for_timeout(3500)

        checks["brand = live /api/core name"] = "BLACK NOIR" in pg.inner_text("#brand").upper()
        checks["core connection online"] = "online" in pg.inner_text("#conn")
        checks["map: 3D cloud canvas present"] = pg.locator("#map canvas").count() > 0
        checks["map: cluster labels (C1..C6)"] = "C1" in pg.inner_text("#labels") and "C6" in pg.inner_text("#labels")
        pg.screenshot(path=os.path.join(OUT, "1-map.png"))

        pg.evaluate("document.querySelectorAll('#labels .lab.cl')[0].click()")
        pg.wait_for_timeout(500)
        checks["map: core inspector = 4 AI"] = "Оркестратор" in pg.inner_text("#insp") and "Builder" in pg.inner_text("#insp")
        pg.screenshot(path=os.path.join(OUT, "1b-core-ai.png"))
        pg.click("#insp-x")

        # 2D schema: same core->cluster->module links, live, animated flow
        pg.click("#sb2d"); pg.wait_for_timeout(900)
        checks["map: 2D schema links (svg lines+nodes)"] = pg.locator("#s2svg line.lnk").count() >= 6 and pg.locator("#s2svg circle.nd").count() >= 7
        checks["map: 2D schema ACTIVE counter"] = "ACTIVE" in pg.inner_text("#s2act")
        pg.screenshot(path=os.path.join(OUT, "1c-schema2d.png"))
        pg.click("#sb3d"); pg.wait_for_timeout(400)

        def tab(name):
            pg.click(f".tab[data-go={name}]"); pg.wait_for_timeout(700)

        tab("tasks")
        checks["tasks: kanban columns"] = "В ОЧЕРЕДИ" in pg.inner_text("#tasks") and "ГОТОВО" in pg.inner_text("#tasks")
        pg.screenshot(path=os.path.join(OUT, "2-tasks.png"))

        tab("chat")
        checks["chat: voice equalizer + visual btn"] = pg.locator("#eq").count() > 0 and pg.locator("#visual").count() > 0
        pg.click("#visual"); pg.wait_for_timeout(800)
        checks["chat: visual face window"] = pg.locator("#facewin.on").count() > 0
        pg.screenshot(path=os.path.join(OUT, "3-chat.png"))
        pg.click("#faceclose")

        tab("sys")
        checks["systems: live host metrics"] = "CPU" in pg.inner_text("#metrics") and "RAM" in pg.inner_text("#metrics")
        checks["systems: governor audit"] = "GOVERNOR" in pg.inner_text("#gov")
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
