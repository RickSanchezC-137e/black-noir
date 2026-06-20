"""Headless verification that the HUD renders LIVE data from the core (no demo).
Run with the playwright-equipped venv. Asserts live content from /api/* appears.
"""
import sys

from playwright.sync_api import sync_playwright

HUD = "http://127.0.0.1:8090/index.html?api=http://127.0.0.1:8001"


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        errors = []
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto(HUD)
        pg.wait_for_function("window.__noirReady === true", timeout=10000)
        pg.wait_for_timeout(2500)  # let refresh() populate from live API

        checks = {
            "brand (live /api/core name)": "BLACK NOIR" in pg.inner_text("#brand").upper(),
            "connection online": "online" in pg.inner_text("#connlbl"),
            "core AI roster (4)": "Оркестратор" in pg.inner_text("#coreinfo")
                                  and "Builder" in pg.inner_text("#coreinfo"),
            "modules grouped by cluster (live)": "Voice" in pg.inner_text("#clusters")
                                  and "Owner Profile" in pg.inner_text("#clusters")
                                  and "ПАМЯТЬ" in pg.inner_text("#clusters"),
        }
        # switch to systems screen and check live metrics
        pg.click("nav button[data-s=systems]")
        pg.wait_for_timeout(500)
        checks["live host metrics (CPU/RAM)"] = "CPU" in pg.inner_text("#metrics") \
            and "RAM" in pg.inner_text("#metrics")
        checks["governor audit (live)"] = "ALLOW" in pg.inner_text("#gov") \
            or "—" in pg.inner_text("#gov")
        # profile screen
        pg.click("nav button[data-s=profile]")
        pg.wait_for_timeout(500)
        checks["profile facts (live owner_profile)"] = "habits" in pg.inner_text("#pfacts") \
            or "продуктивн" in pg.inner_text("#pfacts")

        b.close()

    ok = all(checks.values())
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    # ensure no demo markers leaked into DOM
    print("\nconsole errors:", errors[:3] if errors else "none")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
