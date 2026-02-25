# cartier_contact_only_http1.py
# pip install playwright requests

import os
import requests
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
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "YOUR_SLACK_WEBHOOK_URL_HERE")

def notify_slack(text: str):
    try:
        resp = requests.post(SLACK_WEBHOOK_URL, json={"text": text}, timeout=10)
        print("[Slack]", resp.text)
    except Exception as e:
        print("[Slack 전송 실패]", e)

def open_browser(p):
    # 로컬에 설치된 Chrome/Edge 사용 (브라우저 다운로드 불필요)
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-http2",  # HTTP/2 비활성화
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

def main():
    with sync_playwright() as p:
        browser = open_browser(p)

        proxy_cfg = None
        # 사내 프록시를 쓰는 환경이면 환경변수에서 읽어 적용 (예: http://proxy.company:8080)
        for key in ("HTTPS_PROXY", "HTTP_PROXY"):
            if os.environ.get(key):
                proxy_cfg = {"server": os.environ[key]}
                break

        context = browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
            viewport={"width": 1366, "height": 850},
            ignore_https_errors=True,  # SSL 가로채기 환경 우회
            proxy=proxy_cfg
        )
        context.set_extra_http_headers({"Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"})
        page = context.new_page()
        page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_())

        try:
            # 1차: domcontentloaded
            try:
                page.goto(PRODUCT_URL, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                print("[WARN] domcontentloaded 실패, commit로 재시도:", e)
                # 2차: commit (HTTP/2 문제 우회에 도움될 때가 있음)
                page.goto(PRODUCT_URL, wait_until="commit", timeout=45000)

            # 버튼 컨테이너 로드 대기
            try:
                page.wait_for_selector("div.product-add__container", state="attached", timeout=15000)
            except Exception:
                pass

            # “상담원 연결”이 보이는지(숨김 아님) 확인
            sel_attr = ("div.product-add__container "
                        "a.product-add__button.add-to-cart[data-product-component='availability-status']"
                        "[href*='/contact-customer-care']:not(.hidden)")
            contact = page.locator(sel_attr).first

            found = False
            if contact.count() > 0 and contact.is_visible():
                found = True
                text = contact.inner_text().strip()

            if not found:
                # 폴백: 텍스트 포함 + not(.hidden)
                xpath_fb = ("//a[contains(normalize-space(.), '상담원 연결') "
                            "and not(contains(@class,'hidden'))]")
                fb = page.locator(f"xpath={xpath_fb}").first
                if fb.count() > 0 and fb.is_visible():
                    found = True
                    text = fb.inner_text().strip()

            if found:
                msg = (f"[Cartier 모니터] '{text}' 버튼 감지\n"
                       f"URL: {PRODUCT_URL}\n"
                       f"시간(KST): {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(msg)
                notify_slack(msg)
            else:
                print("상담원 연결 버튼이 현재 보이지 않습니다.")

        finally:
            context.close()
            browser.close()

if __name__ == "__main__":
    main()
