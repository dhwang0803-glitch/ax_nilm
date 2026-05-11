"""전력 에너지 코치 LLM Agent — LangGraph 슈퍼바이저 멀티에이전트 래퍼."""
from __future__ import annotations

from typing import Any

from .graph import run_graph


def run_coach(
    household_id: str,
    user_message: str,
    session_id: str | None = None,
    log_dir: str = "logs/traces",
) -> dict[str, Any]:
    """LangGraph 멀티에이전트 코치 실행.

    반환:
      answer, tool_calls, iterations, session_id, trace_path, pii_warnings, validation
    """
    return run_graph(
        household_id=household_id,
        user_message=user_message,
        session_id=session_id,
        log_dir=log_dir,
    )
