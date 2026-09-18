# test_monitor.py
# Slack Webhook 연동 및 네트워크 세팅을 1회성으로 점검하기 위한 스크립트
# pip install playwright requests

from datetime import datetime
from playwright.sync_api import sync_playwright

from common import PRODUCT_URL, load_env, notify_slack, open_browser, new_context, block_heavy_resources

load_env()


def main():
    with sync_playwright() as p:
        browser = open_browser(p)
        context = new_context(browser)
        page = context.new_page()
        block_heavy_resources(page)

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

            # "상담원 연결"이 보이는지(숨김 아님) 확인
            sel_attr = ("div.product-add__container "
                        "a.product-add__button.add-to-cart[data-product-component='availability-status']"
                        "[href*='/contact-customer-care']:not(.hidden)")
            contact = page.locator(sel_attr).first

            found = False
            text = ""
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
