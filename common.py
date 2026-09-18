# common.py
# test_monitor.py와 tank_must_monitor.py가 공유하는 설정/유틸리티 모음

import os
import requests

PRODUCT_URL = (
    "https://www.cartier.com/ko-kr/watches/all-collections/tank/"
    "%ED%83%B1%ED%81%AC-%EB%A8%B8%EC%8A%A4%ED%8A%B8-%EB%93%9C-"
    "%EA%B9%8C%EB%A5%B4%EB%9D%A0%EC%97%90-%EC%9B%8C%EC%B9%98-CRWSTA0107.html"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def load_env():
    """저장소 루트의 .env 파일이 있으면 읽어서 환경 변수로 등록한다."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip("'").strip('"')


def get_slack_webhook_url():
    return os.getenv("SLACK_WEBHOOK_URL", "YOUR_SLACK_WEBHOOK_URL_HERE")


def notify_slack(text: str):
    url = get_slack_webhook_url()
    try:
        resp = requests.post(url, json={"text": text}, timeout=10)
        print("[Slack]", resp.text)
    except Exception as e:
        print("[Slack 전송 실패]", e)


def get_proxy_config():
    """사내 프록시를 쓰는 환경이면 환경변수에서 읽어 적용 (예: http://proxy.company:8080)"""
    for key in ("HTTPS_PROXY", "HTTP_PROXY"):
        if os.environ.get(key):
            return {"server": os.environ[key]}
    return None


def open_browser(p):
    """로컬에 설치된 Chrome/Edge를 사용 (브라우저 다운로드 불필요)"""
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


def new_context(browser):
    context = browser.new_context(
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        user_agent=USER_AGENT,
        viewport={"width": 1366, "height": 850},
        ignore_https_errors=True,  # SSL 가로채기 환경 우회
        proxy=get_proxy_config(),
    )
    context.set_extra_http_headers({"Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"})
    return context


def block_heavy_resources(page):
    """이미지/영상/폰트 등 무거운 리소스를 차단해 로딩 속도를 높인다."""
    page.route(
        "**/*",
        lambda route: route.abort()
        if route.request.resource_type in ("image", "media", "font")
        else route.continue_(),
    )
