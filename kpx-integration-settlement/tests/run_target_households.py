"""79가구 전체 insights 에이전트 실행 → LangSmith 트레이싱 확인용."""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / "config" / ".env")

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.agent.graph import run_graph

HOUSEHOLD_IDS = [
    "H011","H015","H016","H017","H039","H049","H054","H063","H067"
]

PROMPT = "이상 탐지 이벤트를 진단하고 절약 추천을 JSON으로 생성해줘"

results = {"ok": [], "error": []}

for i, hh in enumerate(HOUSEHOLD_IDS, 1):
    t0 = time.time()
    try:
        result = run_graph(household_id=hh, user_message=PROMPT)
        elapsed = round(time.time() - t0, 1)
        answer = result.get("answer", {})
        has_recs = bool(answer.get("recommendations") or answer.get("anomaly_diagnoses"))
        status = "ok" if has_recs else "empty"
        results["ok"].append(hh)
        print(f"[{i:>2}/{len(HOUSEHOLD_IDS)}] {hh} {status} ({elapsed}s)")
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        results["error"].append((hh, str(e)[:80]))
        print(f"[{i:>2}/{len(HOUSEHOLD_IDS)}] {hh} ERROR ({elapsed}s): {e!s:.80}")

print("\n─── 완료 ───────────────────────────────")
print(f"성공: {len(results['ok'])}가구  실패: {len(results['error'])}가구")
if results["error"]:
    print("\n실패 목록:")
    for hh, err in results["error"]:
        print(f"  {hh}: {err}")
print("\nLangSmith → https://smith.langchain.com 에서 프로젝트 ax_nilm-kpx 확인")
