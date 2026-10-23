"""디그 한 호 → PDF (2026-10-23 사용자 요청).

방법: 서버가 크로미움(Playwright, stock 대시보드 캡처에 이미 쓰는 것)으로 '경제 공부 (디그)' 화면을
      인쇄용 모드(`/dig?id=…&print=1`)로 열어 PDF 로 저장한다. 화면과 똑같은 글꼴·사진·굵은 글씨가 그대로 들어간다.
캐시: ~/.openclaw/dig_cache/pdf/<날짜>.pdf  (그 호의 JSON 이 더 새로우면 다시 만든다)
주의: 크로미움은 무거워서 동시에 하나만 돌린다(Lock). 한글 PDF 는 서버에 한글 글꼴(Noto CJK)이 있어야 글자가 나온다.
"""
import os
import threading

import dig_mail

PDF_DIR = os.path.join(dig_mail.CACHE_DIR, "pdf")
CHROMIUM_PATH = os.getenv("CHROMIUM_PATH")             # 샌드박스처럼 크로미움 위치가 따로일 때(capture.py 와 같은 변수)
_lock = threading.Lock()


def _base_url():
    host = os.getenv("HOST", "127.0.0.1")
    if host in ("0.0.0.0", "::", "*", ""):             # 와일드카드 주소는 '듣는' 주소일 뿐 접속용이 아님
        host = "127.0.0.1"
    return "http://%s:%s" % (host, os.getenv("PORT", "8000"))


def pdf_path(issue_id):
    return os.path.join(PDF_DIR, issue_id + ".pdf")


def _fresh(issue_id):
    """PDF 가 있고, 원본 JSON 보다 새것이면 True."""
    try:
        return os.path.getmtime(pdf_path(issue_id)) >= os.path.getmtime(
            os.path.join(dig_mail.CACHE_DIR, issue_id + ".json"))
    except OSError:
        return False


def get_pdf(issue_id, base_url=None):
    """PDF 파일 경로를 돌려준다(없으면 만든다). 그런 호가 없으면 None. 실패하면 예외."""
    if not dig_mail.get_issue(issue_id):                # 날짜 모양 검사 + 존재 확인(경로 조작 방지)
        return None
    if _fresh(issue_id):
        return pdf_path(issue_id)
    with _lock:
        if _fresh(issue_id):                            # 기다리는 동안 다른 요청이 만들어 뒀을 수 있음
            return pdf_path(issue_id)
        from playwright.sync_api import sync_playwright   # 늦게 불러온다 → 이 모듈이 없어도 /dig 화면은 정상
        os.makedirs(PDF_DIR, exist_ok=True)
        tmp = pdf_path(issue_id) + ".tmp"
        with sync_playwright() as p:
            kw = {"headless": True}
            if CHROMIUM_PATH:
                kw["executable_path"] = CHROMIUM_PATH
            browser = p.chromium.launch(**kw)
            try:
                page = browser.new_page()
                page.goto("%s/dig?id=%s&print=1" % (base_url or _base_url(), issue_id),
                          wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector("body[data-ready='1']", timeout=30000)   # 글이 다 그려진 뒤
                # 사진이 다 내려받아질 때까지(실패한 사진은 그냥 건너뜀) 최대 20초
                try:
                    page.wait_for_function(
                        "Array.from(document.images).every(i=>i.complete)", timeout=20000)
                except Exception:
                    pass
                page.pdf(path=tmp, format="A4", print_background=True,
                         margin={"top": "14mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
                         display_header_footer=True,
                         header_template="<span></span>",
                         footer_template='<div style="width:100%;font-size:9px;color:#888;text-align:center">'
                                         '경제 공부 (디그) · <span class="pageNumber"></span> / '
                                         '<span class="totalPages"></span></div>')
            finally:
                browser.close()
        os.replace(tmp, pdf_path(issue_id))
        return pdf_path(issue_id)
