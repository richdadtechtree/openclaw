import os
import time
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from notifier import send_telegram_photo

load_dotenv()

PORT = os.getenv("PORT", "8000")
HOST = os.getenv("HOST", "127.0.0.1")

SCREENSHOT_PATH = "static/briefing_screenshot.png"

# Optional executable path override (useful on sandboxes with pre-installed chromium)
CHROMIUM_PATH = os.getenv("CHROMIUM_PATH")

# 브리핑에 찍는 "마감" 시각은 항상 한국시각 기준으로 표시 (서버가 UTC여도 정확하게)
BRIEFING_TZ = os.getenv("SCHEDULER_TZ", "Asia/Seoul")


def _now_kst():
    """한국시각 기준 현재 시각. zoneinfo가 없거나 실패하면 서버 로컬 시각으로 폴백."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(BRIEFING_TZ))
    except Exception:
        return datetime.now()


def _client_host(host):
    """
    접속용 호스트 정규화.
    uvicorn 은 보통 0.0.0.0(모든 인터페이스)에 '바인딩'하지만, 그건 서버가 '듣는' 주소일 뿐
    클라이언트가 '접속하는' 주소로는 부적절하다. 크로미움은 0.0.0.0 / :: 같은 와일드카드
    주소로의 접속을 거부·실패할 수 있으므로 루프백(127.0.0.1)으로 바꿔서 접속한다.
    (에러 로그의 `http://0.0.0.0:8000/` 이 바로 이 케이스)
    """
    if host in ("0.0.0.0", "::", "*", ""):
        return "127.0.0.1"
    return host


def _wait_for_indices(page, timeout=20000):
    """지수 카드에 '실제 시세'(.price-value)가 렌더되면 True, 타임아웃이면 False."""
    # ⚠️ 셀렉터는 index.html 이 실제 렌더하는 클래스와 일치해야 한다.
    #    index.html 리디자인 후 카드가 .market-card 로 바뀌었고, 초기 플레이스홀더 카드
    #    (`.market-card > p '지수 데이터를 로딩 중입니다…'`)엔 .price-value 가 없다.
    #    그래서 "데이터 로딩 완료"는 실제 시세 카드에만 있는 .price-value 로만 판정한다.
    #    (옛 셀렉터 `.index-card:not(.loading-skeleton)` 는 더 이상 존재하지 않아 항상 타임아웃)
    try:
        page.wait_for_selector("#indices-grid .price-value", timeout=timeout)
        return True
    except Exception:
        return False


def capture_dashboard(path=SCREENSHOT_PATH):
    """
    대시보드 웹 화면을 사진으로 찍어 path에 저장. 성공 시 True.
    (전송은 하지 않음 — 캡처만)
    """
    url = f"http://{_client_host(HOST)}:{PORT}/"
    print(f"Navigating to dashboard at: {url}")

    with sync_playwright() as p:
        browser = None
        try:
            launch_kwargs = {"headless": True}
            if CHROMIUM_PATH:
                launch_kwargs["executable_path"] = CHROMIUM_PATH
            browser = p.chromium.launch(**launch_kwargs)
            page = browser.new_page()

            # Set high-DPI viewport for crisp screenshot (TQQQ + 알람 섹션 포함 높이)
            page.set_viewport_size({"width": 1320, "height": 1080})

            # 1) 서버 접속. 여기서 실패하면 '웹서버가 안 떠 있음' → 하드 실패로 명확히 알린다.
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
            except Exception as e:
                print(f"[Error] 대시보드 접속 실패 ({url}): {e}")
                print("        → stock 웹서버(scheduler.py/uvicorn)가 떠 있는지 확인하세요.")
                return False

            print("Waiting for dashboard to finish loading data...")
            # 2) 지수 시세가 렌더될 때까지 대기. 서버는 떴는데 데이터가 늦거나 일부 실패하면
            #    한 번 새로고침 후 재시도(일시적 API 지연 대비).
            data_ready = _wait_for_indices(page)
            if not data_ready:
                print("[Warn] 지수 시세 로딩 지연 — 새로고침 후 재시도합니다.")
                try:
                    page.reload(wait_until="domcontentloaded", timeout=20000)
                except Exception:
                    pass
                data_ready = _wait_for_indices(page)

            if not data_ready:
                # 서버는 응답하는데 시세가 끝내 안 뜸(외부 시세 API 오류 등).
                # 로딩중 화면을 슬랙에 보내면 오히려 혼란스러우므로 하드 실패로 처리.
                print("[Error] 서버는 응답하나 지수 시세(.price-value)가 로딩되지 않았습니다.")
                print("        → 시세 데이터 소스(market_data) 오류 가능성. 대시보드를 직접 열어 확인하세요.")
                return False

            # Sleep slightly to ensure CSS transitions/animations settle
            time.sleep(1.5)

            # 스크린샷 범위: 헤더 + 지수 스냅샷까지만.
            # 투자 타이밍(.strategy-section)·관심종목·푸터는 브리핑에서 제외 요청됨.
            # ⚠️ page.screenshot(clip=...) 좌표 계산 방식은 뷰포트 크기/타이밍에 따라
            #    필요한 영역이 온전히 안 잡히는 문제가 있었다("TQQQ 박스가 계속 잘림").
            #    → index.html 쪽에 캡처 범위를 감싸는 전용 래퍼(#briefing-capture-area)를
            #      만들어두고, 그 요소 하나를 통째로 element screenshot 한다.
            #      (element screenshot 은 Playwright 가 알아서 뷰포트 밖 영역까지
            #       스크롤/캡처해주므로 좌표 계산이 필요 없어 훨씬 안정적이다.)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            capture_area = page.locator("#briefing-capture-area")
            if capture_area.count() > 0:
                capture_area.screenshot(path=path)
            else:
                # index.html 에 래퍼가 없는 옛 배포본일 때의 안전한 폴백
                print("[Warn] #briefing-capture-area 없음 — 전체 컨테이너로 캡처합니다.")
                page.locator(".container").screenshot(path=path)
            print(f"Screenshot successfully saved to {path}")
            return True
        except Exception as e:
            print(f"[Error] Playwright screenshot failed: {e}")
            return False
        finally:
            if browser:
                browser.close()


def capture_and_send():
    """
    대시보드를 캡처해서 텔레그램(브리핑 봇)으로 전송. 성공 시 True.
    """
    if not capture_dashboard(SCREENSHOT_PATH):
        return False

    date_str = _now_kst().strftime("%Y년 %m월 %d일 %H:%M 마감")
    caption = (
        f"📈 *주요 시장 지수 마감 브리핑*\n"
        f"📅 일시: {date_str}\n\n"
        f"코스피, 코스닥, S&P 500, 나스닥, QLD, TQQQ 현황을 공유합니다."
    )
    print("Sending photo to Telegram...")
    if send_telegram_photo(SCREENSHOT_PATH, caption):
        print("Telegram briefing message sent successfully!")
        return True
    return False


if __name__ == "__main__":
    capture_and_send()
