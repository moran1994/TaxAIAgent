"""LLM gateway — OpenAI-compatible HTTP; extractive fallback without API key."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_PROMPTS = REPO_ROOT / "ops" / "prompts"


def load_prompt(version: str = "vat_qa_v1") -> dict[str, Any]:
    path = REPO_PROMPTS / f"{version}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_path"] = str(path)
        return data
    return {
        "version": version,
        "system": (
            "你是增值税法规助手。只能依据给定【检索片段】作答；"
            "不得编造文号或条款。无依据时必须 uncertainty=true。"
            "输出严格 JSON。"
        ),
        "user_template": "问题：{query}\n\n【检索片段】\n{context}\n\n请输出 JSON。",
    }


class LLMGateway:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.prompt = load_prompt("vat_qa_v1")

    @property
    def configured(self) -> bool:
        return bool(self.settings.llm_api_key)

    def complete_json(self, query: str, context_block: str) -> tuple[dict[str, Any], dict]:
        """Return (payload, call_meta)."""
        system = self.prompt.get("system", "")
        user = self.prompt.get("user_template", "{query}\n{context}").format(
            query=query, context=context_block
        )
        t0 = time.perf_counter()
        if not self.configured or not context_block.strip():
            # extractive fallback — never invent citations
            payload = {
                "conclusion": (
                    "根据检索到的法规片段，要点如下（未配置大模型时的摘录式答复）：\n"
                    + context_block[:1200]
                    if context_block.strip()
                    else ""
                ),
                "uncertainty": not bool(context_block.strip()),
                "boundary": "请结合纳税人资格、行业与主管税务机关口径核实。",
                "mode": "extractive_fallback",
            }
            meta = {
                "prompt_version": self.prompt.get("version", "vat_qa_v1"),
                "model": "extractive",
                "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
                "llm_configured": self.configured,
            }
            return payload, meta

        base = self.settings.llm_api_base or "https://api.openai.com/v1"
        url = base.rstrip("/") + "/chat/completions"
        body = {
            "model": self.settings.llm_model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
            content = data["choices"][0]["message"]["content"]
            payload = json.loads(content)
            meta = {
                "prompt_version": self.prompt.get("version", "vat_qa_v1"),
                "model": self.settings.llm_model,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
                "llm_configured": True,
                "usage": data.get("usage"),
            }
            return payload, meta
        except Exception as exc:  # noqa: BLE001 — surface as extractive safety
            payload = {
                "conclusion": "模型调用失败，已回退为摘录式答复。\n" + context_block[:800],
                "uncertainty": True,
                "boundary": "请转专家或稍后重试。",
                "mode": "llm_error_fallback",
                "error": str(exc)[:200],
            }
            meta = {
                "prompt_version": self.prompt.get("version", "vat_qa_v1"),
                "model": self.settings.llm_model,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
                "llm_configured": True,
                "error": str(exc)[:200],
            }
            return payload, meta
