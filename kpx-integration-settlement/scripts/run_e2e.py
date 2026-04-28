"""End-to-end CLI runner — 코치 에이전트 실행 프로토타입.

사용법:
  python scripts/run_e2e.py --household HH001 --question "이번 주 전기료 줄이려면?"
  python scripts/run_e2e.py --household HH001 --question "에어컨 언제 끄면 좋을까?" --dry-run

--dry-run 모드: OpenAI API를 호출하지 않고 LLM에 전달될 메시지(system + baseline + user)를
               그대로 출력해 프롬프트를 검증한다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# 프로젝트 루트를 sys.path에 추가 (scripts/ → 상위 디렉토리)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agent.coach import _SYSTEM_PROMPT, build_baseline_context
from src.agent.data_tools import TOOL_SCHEMAS


def _dry_run(household_id: str, question: str, location: str) -> None:
    """실제 API 호출 없이 LLM에 전달될 메시지 구조를 출력."""
    print("=" * 60)
    print("[DRY-RUN] LLM에 전달될 메시지 미리보기")
    print("=" * 60)

    baseline = build_baseline_context(household_id, location)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": f"{baseline}\n\n{question}"},
    ]

    for i, msg in enumerate(messages):
        role  = msg["role"].upper()
        body  = msg["content"]
        print(f"\n[{i+1}] {role}")
        print("-" * 40)
        print(body)

    print("\n" + "=" * 60)
    print(f"[DRY-RUN] 등록된 도구 수: {len(TOOL_SCHEMAS)}")
    for t in TOOL_SCHEMAS:
        fn = t["function"]
        print(f"  - {fn['name']}: {fn['description'][:50]}...")
    print("=" * 60)
    print("[DRY-RUN] 완료. --dry-run 없이 실행하면 실제 API를 호출합니다.")


def _live_run(household_id: str, question: str, location: str, model: str, max_iter: int) -> None:
    """실제 OpenAI API를 호출해 코치 에이전트를 실행."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[ERROR] OPENAI_API_KEY 환경변수가 설정되지 않았습니다.", file=sys.stderr)
        print("  export OPENAI_API_KEY=sk-...")
        sys.exit(1)

    from src.agent.coach import run_coach

    print(f"[INFO] 코치 에이전트 실행 | household={household_id} | model={model}")
    print(f"[INFO] 질문: {question}\n")

    result = run_coach(
        household_id=household_id,
        user_message=question,
        location=location,
        max_iterations=max_iter,
        model=model,
    )

    print("=" * 60)
    print(f"[결과] session_id : {result['session_id']}")
    print(f"[결과] iterations : {result['iterations']}")
    print(f"[결과] trace_path : {result['trace_path']}")

    if result["pii_warnings"]:
        print(f"[경고] PII 필드 감지됨: {result['pii_warnings']}")

    if result["tool_calls"]:
        print(f"[결과] 호출된 도구 ({len(result['tool_calls'])}회):")
        for tc in result["tool_calls"]:
            print(f"  - {tc.tool}")

    print("\n[최종 답변]")
    print(json.dumps(result["answer"], ensure_ascii=False, indent=2))
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="전력 에너지 코치 에이전트 CLI")
    parser.add_argument("--household", "-H", default="HH001",
                        help="가구 ID (기본값: HH001)")
    parser.add_argument("--question",  "-q", default="이번 주 전기료를 줄이려면 어떻게 해야 하나요?",
                        help="사용자 질문")
    parser.add_argument("--location",  "-l", default="서울",
                        help="지역 (날씨·예보 조회용, 기본값: 서울)")
    parser.add_argument("--model",     "-m", default="gpt-4o-mini",
                        help="OpenAI 모델 ID (기본값: gpt-4o-mini)")
    parser.add_argument("--max-iter",  type=int, default=5,
                        help="최대 tool-call 반복 횟수 (기본값: 5)")
    parser.add_argument("--dry-run",   action="store_true",
                        help="API 호출 없이 LLM 입력 메시지만 출력")
    args = parser.parse_args()

    if args.dry_run:
        _dry_run(args.household, args.question, args.location)
    else:
        _live_run(args.household, args.question, args.location, args.model, args.max_iter)


if __name__ == "__main__":
    main()
