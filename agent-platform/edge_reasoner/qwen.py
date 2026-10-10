"""Small Qwen compatible API client; secrets are read only from the environment."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class QwenClient:
    def __init__(self) -> None:
        self.key = os.environ.get("DASHSCOPE_API_KEY", "")
        if not self.key:
            raise RuntimeError("DASHSCOPE_API_KEY is required for live calls")
        self.url = os.environ.get(
            "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).rstrip("/")
        self.model = os.environ.get("QWEN_TEACHER_MODEL", "qwen-max")
        self.calls = 0

    def chat(self, system: str, user: str, *, temperature: float = 0.2) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            self.url + "/chat/completions",
            data=payload,
            headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"Qwen API returned HTTP {exc.code}; check endpoint, model and key"
            ) from None
        self.calls += 1
        return data["choices"][0]["message"]["content"]

    def judge(self, prompt: str, completion: str, facts: str = "") -> float:
        system = (
            '你是資料品質評分員。只輸出 JSON {"score": 0.0-1.0}。'
            "評估回答是否符合已知事實、是否承認未知；"
            "沒有證據的保險結論評 0。格式另行評分。"
        )
        content = self.chat(
            system,
            json.dumps(
                {"question": prompt, "candidate": completion, "known_facts": facts},
                ensure_ascii=False,
            ),
            temperature=0,
        )
        try:
            score = float(json.loads(content)["score"])
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("Judge did not return score JSON") from exc
        if not 0 <= score <= 1:
            raise ValueError("Judge score outside [0, 1]")
        return score
