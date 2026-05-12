"""멀티에이전트 insights 실행 → LangSmith 트레이싱 평가용.

목업 가구 (HH001-HH003): DB 없이 실행 가능.
실데이터 가구 (H011 등): DB 연결 필요.
"""
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / "config" / ".env")

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.agent.multi_agent.supervisor import run_multi_agent

# 목업 가구 — DB 없이 평가 가능
MOCK_HOUSEHOLDS = ["HH001", "HH002", "HH003"]

# 실데이터 가구 — DB 연결 필요 시 사용
REAL_HOUSEHOLDS = ["H011","H015","H016","H017","H039","H049","H054","H063","H067"]

HOUSEHOLD_IDS = MOCK_HOUSEHOLDS + REAL_HOUSEHOLDS

PROMPT = "이상 탐지 이벤트를 진단하고 절약 추천을 JSON으로 생성해줘"

results = {"ok": [], "empty": [], "error": []}

for i, hh in enumerate(HOUSEHOLD_IDS, 1):
    t0 = time.time()
    try:
        output = run_multi_agent(household_id=hh)
        elapsed = round(time.time() - t0, 1)
        has_content = bool(output.recommendations or output.anomaly_diagnoses)
        status = "ok" if has_content else "empty"
        results[status].append(hh)
        rag_flag = ""
        print(f"[{i:>2}/{len(HOUSEHOLD_IDS)}] {hh} {status} ({elapsed}s)"
              f"  recs={len(output.recommendations)} diag={len(output.anomaly_diagnoses)}")
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        results["error"].append((hh, str(e)[:80]))
        print(f"[{i:>2}/{len(HOUSEHOLD_IDS)}] {hh} ERROR ({elapsed}s): {e!s:.80}")

print("\n─── 완료 ───────────────────────────────")
print(f"성공: {len(results['ok'])}  빈 결과: {len(results['empty'])}  실패: {len(results['error'])}")
if results["error"]:
    print("\n실패 목록:")
    for hh, err in results["error"]:
        print(f"  {hh}: {err}")
print("\nLangSmith → https://smith.langchain.com 에서 프로젝트 ax_nilm-kpx 확인")
