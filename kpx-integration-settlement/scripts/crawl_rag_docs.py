"""RAG 문서 크롤러 (playwright 기반).

공식 사이트(한전, K-Point 등)에서 에너지캐시백·절전 관련 페이지를 수집해
rag_docs/raw/ 에 마크다운으로 저장한다.

실행:
    cd kpx-integration-settlement
    python scripts/crawl_rag_docs.py

주의:
    - 뉴스/리서치 사이트(yna.co.kr 등)는 저작권으로 제외.
    - robots.txt를 준수한다. 차단된 경로는 [ROBOTS] 로 표시하고 건너뛴다.
    - 요청 간 2초 딜레이 적용.
"""
from __future__ import annotations

import re
import sys
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

# ---------------------------------------------------------------------------
# 크롤링 대상
# (출력 파일명, URL, 문서 제목)
# ---------------------------------------------------------------------------
TARGETS: list[tuple[str, str, str]] = [
    # ── 에너지캐시백 ──────────────────────────────────────────────────────
    (
        "cashback_overview.md",
        "https://cyber.kepco.co.kr/ckepco/front/jsp/CY/E/E/CYEEHP00101.jsp",
        "KEPCO 에너지캐시백 개요",
    ),
    (
        "cashback_enrollment.md",
        "https://cyber.kepco.co.kr/ckepco/front/jsp/CY/E/E/CYEEHP00201.jsp",
        "KEPCO 에너지캐시백 신청 방법",
    ),
    # ── 한국전력포인트 ────────────────────────────────────────────────────
    (
        "kpoint_intro.md",
        "https://cpoint.or.kr/user/main/main.do",
        "한국전력포인트 개요",
    ),
    (
        "kpoint_guide.md",
        "https://cpoint.or.kr/user/guide/guide.do",
        "한국전력포인트 이용 안내",
    ),
    # ── 누진제·요금 안내 ──────────────────────────────────────────────────
    (
        "tariff_progressive.md",
        "https://cyber.kepco.co.kr/ckepco/front/jsp/CY/H/G/CYHGHP00101.jsp",
        "KEPCO 주택용 전기요금 안내",
    ),
    # ── 에너지 절감 팁 ────────────────────────────────────────────────────
    (
        "tips_energy_saving.md",
        "https://www.energy.or.kr/web/kem_home_new/energy_all/saving/index.asp",
        "에너지관리공단 절전 팁",
    ),
]

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
OUT_DIR      = Path(__file__).parent.parent / "rag_docs" / "raw"
DELAY_SEC    = 2.0
MIN_TEXT_LEN = 300   # 이 길이 미만이면 수집 실패로 기록
# playwright가 사용하는 Chrome User-Agent (robots.txt 확인에 사용)
_CHROME_UA   = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# ---------------------------------------------------------------------------
# robots.txt 캐시
# ---------------------------------------------------------------------------
_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}

def _can_fetch(url: str) -> bool:
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(urljoin(origin, "/robots.txt"))
        try:
            rp.read()
        except Exception:
            rp.allow_all = True  # type: ignore[attr-defined]
        _robots_cache[origin] = rp
    return _robots_cache[origin].can_fetch(_CHROME_UA, url)


# ---------------------------------------------------------------------------
# HTML → 마크다운 변환 (노이즈 정제)
# ---------------------------------------------------------------------------
_NOISE_TAGS = {
    "script", "style", "nav", "header", "footer", "aside",
    "noscript", "iframe", "form", "button", "input", "select",
    "svg", "img",
}
# 광고·메뉴 등 전형적인 노이즈 클래스/ID 패턴
_NOISE_ATTRS = re.compile(
    r"(gnb|lnb|snb|breadcrumb|banner|popup|modal|tooltip"
    r"|sitemap|quick-menu|quick_menu|skip|dim|loading"
    r"|ad-|advertisement|copyright|footer|header)",
    re.I,
)

def _is_noise_element(tag) -> bool:
    if not getattr(tag, "attrs", None):
        return False
    for attr in ("id", "class"):
        val = tag.get(attr, "")
        combined = " ".join(val) if isinstance(val, list) else str(val)
        if _NOISE_ATTRS.search(combined):
            return True
    return False

def _html_to_markdown(html: str, title: str, url: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    # 1차: 태그 유형으로 노이즈 제거
    for tag in soup(_NOISE_TAGS):
        tag.decompose()

    # 2차: 클래스/ID 패턴으로 노이즈 제거
    for tag in soup.find_all(True):
        if _is_noise_element(tag):
            tag.decompose()

    # 본문 영역 우선순위
    body = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id=re.compile(r"^(content|main|wrap|container)", re.I))
        or soup.find(class_=re.compile(r"^(content|main|wrap|container)", re.I))
        or soup.find("body")
        or soup
    )

    lines: list[str] = [f"# {title}", f"\n> 출처: {url}\n"]
    prev_was_blank = False

    for elem in body.find_all(["h1", "h2", "h3", "h4", "h5", "p", "li", "tr"]):
        # 이미 분해된 요소 건너뜀
        if not elem.parent:
            continue

        raw = elem.get_text(" ", strip=True)
        # 연속 공백·줄바꿈 정규화
        text = re.sub(r"\s+", " ", raw).strip()
        if not text or len(text) < 2:
            continue

        tag = elem.name
        if tag == "h1":
            line = f"\n## {text}"
        elif tag == "h2":
            line = f"\n### {text}"
        elif tag in ("h3", "h4", "h5"):
            line = f"\n#### {text}"
        elif tag == "li":
            line = f"- {text}"
        elif tag == "tr":
            cells = [td.get_text(" ", strip=True) for td in elem.find_all(["td", "th"])]
            line = "| " + " | ".join(cells) + " |" if cells else ""
        else:  # p
            line = text

        if not line:
            continue

        # 중복 공백행 방지
        is_blank = not line.strip()
        if is_blank and prev_was_blank:
            continue
        prev_was_blank = is_blank

        lines.append(line)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 단일 URL 수집
# ---------------------------------------------------------------------------
def crawl_one(page, filename: str, url: str, title: str) -> str:
    out_path = OUT_DIR / filename

    if not _can_fetch(url):
        return "[ROBOTS] robots.txt 차단"

    try:
        page.goto(url, wait_until="networkidle", timeout=20_000)
    except Exception as exc:
        # timeout 또는 네트워크 오류 → domcontentloaded 로 재시도
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            page.wait_for_timeout(3_000)
        except Exception as exc2:
            return f"[ERROR] {str(exc2)[:100]}"

    html = page.content()
    md   = _html_to_markdown(html, title, url)

    body_len = len(md.replace(f"# {title}", "").replace(f"> 출처: {url}", "").strip())
    if body_len < MIN_TEXT_LEN:
        return f"[EMPTY] 본문 {body_len}자 — 로그인 필요 또는 접근 차단 가능성"

    out_path.write_text(md, encoding="utf-8")
    return f"[OK] {body_len:,}자 → {out_path.name}"


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"출력: {OUT_DIR}\n")

    failed: list[tuple[str, str]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            ignore_https_errors=True,   # 한국 공공기관 구형 SSL 대응
            locale="ko-KR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()

        for filename, url, title in TARGETS:
            print(f"[{title}]")
            print(f"  {url}")
            result = crawl_one(page, filename, url, title)
            print(f"  {result}")
            if not result.startswith("[OK]"):
                failed.append((title, result))
            time.sleep(DELAY_SEC)

        browser.close()

    print("\n" + "=" * 55)
    ok_count = len(TARGETS) - len(failed)
    print(f"완료: {ok_count}/{len(TARGETS)} 성공")
    if failed:
        print("\n실패 목록:")
        for title, reason in failed:
            print(f"  - {title}: {reason}")
    print(f"\n저장 위치: {OUT_DIR}")


if __name__ == "__main__":
    main()
