# cartier_monitor_switch.py
# pip install playwright requests

import os, time, random, requests
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError

# 로컬 .env 파일이 존재하면 읽어서 환경 변수로 설정 (외부 라이브러리 없이)
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip("'").strip('"')

PRODUCT_URL = "https://www.cartier.com/ko-kr/watches/all-collections/tank/%ED%83%B1%ED%81%AC-%EB%A8%B8%EC%8A%A4%ED%8A%B8-%EB%93%9C-%EA%B9%8C%EB%A5%B4%EB%9D%A0%EC%97%90-%EC%9B%8C%EC%B9%98-CRWSTA0107.html"

SLACK_WEBHOOK_URL = os.getenv(
    "SLACK_WEBHOOK_URL",
    "YOUR_SLACK_WEBHOOK_URL_HERE"
)

# 폴링 주기(짧게): 30초 + [0~30]초 지터
BASE_INTERVAL = 30
JITTER_MAX = 30

def notify_slack(text: str):
    try:
        resp = requests.post(SLACK_WEBHOOK_URL, json={"text": text}, timeout=10)
        print("[Slack]", resp.text)
    except Exception as e:
        print("[Slack 전송 실패]", e)

def open_browser(p):
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-http2",
    ]
    try:
        return p.chromium.launch(channel="chrome", headless=True, args=launch_args)
    except Exception as e1:
        print("[INFO] Chrome 채널 실패:", e1)
        try:
            return p.chromium.launch(channel="msedge", headless=True, args=launch_args)
        except Exception as e2:
            print("[INFO] Edge 채널 실패:", e2)
            raise RuntimeError("Chrome/Edge 채널 실행 실패")

def state_detect(page) -> str:
    """
    반환값: 'CONTACT' | 'ADD' | 'UNKNOWN'
    """
    # ADD
    sel_add = ("div.product-add__container "
               "button.product-add__button.add-to-cart"
               "[data-product-component='add-button']:not(.hidden):not([disabled])")
    add_btn = page.locator(sel_add).first
    if add_btn.count() > 0 and add_btn.is_visible():
        return "ADD"
    add_fb = page.locator(
        "xpath=//button[contains(normalize-space(.),'쇼핑백에 추가하기') and not(contains(@class,'hidden'))]"
    ).first
    if add_fb.count() > 0 and add_fb.is_visible():
        return "ADD"

    # CONTACT
    sel_contact = ("div.product-add__container "
                   "a.product-add__button.add-to-cart"
                   "[data-product-component='availability-status']"
                   "[href*='/contact-customer-care']:not(.hidden)")
    contact = page.locator(sel_contact).first
    if contact.count() > 0 and contact.is_visible():
        return "CONTACT"
    contact_fb = page.locator(
        "xpath=//a[contains(normalize-space(.),'상담원 연결') and not(contains(@class,'hidden'))]"
    ).first
    if contact_fb.count() > 0 and contact_fb.is_visible():
        return "CONTACT"

    return "UNKNOWN"

def main():
    with sync_playwright() as p:
        browser = open_browser(p)
        context = browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
            viewport={"width": 1366, "height": 850},
            ignore_https_errors=True,
        )
        context.set_extra_http_headers({"Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"})
        page = context.new_page()
        page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_())

        # 최초 접근
        try:
            try:
                page.goto(PRODUCT_URL, wait_until="domcontentloaded", timeout=45000)
            except Exception:
                page.goto(PRODUCT_URL, wait_until="commit", timeout=45000)
            try:
                page.wait_for_selector("div.product-add__container", state="attached", timeout=15000)
            except Exception:
                pass
        except Exception as e:
            print("[초기 접속 실패]", e)

        last_state = None
        print("[START] 모니터링 시작:", PRODUCT_URL)

        try:
            while True:
                try:
                    # 새로고침
                    try:
                        page.reload(wait_until="domcontentloaded", timeout=45000)
                    except Exception:
                        page.goto(PRODUCT_URL, wait_until="commit", timeout=45000)
                    try:
                        page.wait_for_selector("div.product-add__container", state="attached", timeout=15000)
                    except Exception:
                        pass

                    curr = state_detect(page)
                    now_kst = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"[{now_kst}] 상태={curr}")

                    if last_state is None:
                        last_state = curr
                    else:
                        if last_state != curr:
                            # ADD로 변경되면 알림
                            if curr == "ADD":
                                msg = (f"[Cartier 모니터] 상태 변경 감지: 상담원 연결 → 쇼핑백에 추가하기\n"
                                       f"URL: {PRODUCT_URL}\n시간(KST): {now_kst}")
                                print(msg)
                                notify_slack(msg)
                            # UNKNOWN으로 변경되면 알림 (요청 반영)
                            elif curr == "UNKNOWN":
                                msg = (f"[Cartier 모니터] 상태가 UNKNOWN으로 변경됨(버튼 미탐지)\n"
                                       f"URL: {PRODUCT_URL}\n시간(KST): {now_kst}")
                                print(msg)
                                notify_slack(msg)
                            last_state = curr

                except Exception as e:
                    print("[루프 에러] 재시도:", e)

                # 폴링 주기(봇탐지 완화: 지터 유지)
                sleep_sec = BASE_INTERVAL + random.randint(0, JITTER_MAX)
                time.sleep(sleep_sec)

        finally:
            context.close()
            browser.close()

if __name__ == "__main__":
    main()
