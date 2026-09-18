# tank_must_monitor.py
# 실사용을 위한 메인 모니터링 봇 (24시간 루프 실행)
# pip install playwright requests

import time
import random
from datetime import datetime
from playwright.sync_api import sync_playwright

from common import PRODUCT_URL, load_env, notify_slack, open_browser, new_context, block_heavy_resources

load_env()

# 폴링 주기(짧게): 30초 + [0~30]초 지터
BASE_INTERVAL = 30
JITTER_MAX = 30


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
        context = new_context(browser)
        page = context.new_page()
        block_heavy_resources(page)

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
