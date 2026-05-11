"""세션 트레이스 로거 — tool 호출·LLM 응답을 JSON 파일로 기록.

감사(audit)·재학습·디버깅 용도. 로그에도 PII 미기록 원칙 준수.
저장 위치: {log_dir}/{session_id}.json
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCallEntry:
    tool: str
    inputs: dict[str, Any]
    result: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass
class TraceLogger:
    session_id: str
    household_token: str           # 세션 내 익명 토큰 (household_id 대신 로그에 기록)
    log_dir: str = "logs/traces"

    _tool_calls: list[ToolCallEntry] = field(default_factory=list, init=False)
    _final_answer: dict[str, Any]  = field(default_factory=dict,  init=False)
    _token_usage: dict[str, int]   = field(default_factory=dict,  init=False)
    _start_time: float             = field(default_factory=time.time, init=False)

    def log_tool_call(
        self,
        tool: str,
        inputs: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        """tool 호출 1건 기록. inputs에서 household_id는 household_token으로 대체."""
        safe_inputs = {
            k: (self.household_token if k == "household_id" else v)
            for k, v in inputs.items()
        }
        self._tool_calls.append(ToolCallEntry(tool=tool, inputs=safe_inputs, result=result))

    def log_final_answer(
        self,
        answer: dict[str, Any],
        token_usage: dict[str, int] | None = None,
    ) -> None:
        self._final_answer = answer
        self._token_usage  = token_usage or {}

    def save(self) -> str:
        """트레이스를 JSON 파일로 저장. 저장 경로 반환."""
        os.makedirs(self.log_dir, exist_ok=True)
        payload = {
            "session_id":      self.session_id,
            "household_token": self.household_token,
            "start_time":      self._start_time,
            "elapsed_sec":     round(time.time() - self._start_time, 3),
            "tool_calls": [
                {
                    "tool":      e.tool,
                    "inputs":    e.inputs,
                    "result":    e.result,
                    "timestamp": e.timestamp,
                }
                for e in self._tool_calls
            ],
            "final_answer": self._final_answer,
            "token_usage":  self._token_usage,
        }
        path = os.path.join(self.log_dir, f"{self.session_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return path

    @staticmethod
    def load(path: str) -> dict[str, Any]:
        """저장된 트레이스 JSON 파일 로드."""
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    @property
    def tool_call_count(self) -> int:
        return len(self._tool_calls)

    @property
    def tools_used(self) -> list[str]:
        return [e.tool for e in self._tool_calls]
