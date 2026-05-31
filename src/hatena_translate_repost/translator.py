from __future__ import annotations

import httpx

from hatena_translate_repost.models import TranslationResult


class Translator:
    def __init__(self, base_url: str, model: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._http = httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Translator:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def translate(self, title: str, markdown: str) -> TranslationResult:
        translated_title = self._translate_title(title)
        translated_body = self._translate_markdown(markdown)
        return TranslationResult(title=translated_title, body=translated_body)

    def _translate_title(self, title: str) -> str:
        prompt = (
            "Translate the following Japanese blog title into natural English.\n"
            "Return only the translated title.\n"
            "Do not add quotes, labels, or explanations.\n\n"
            f"{title}"
        )
        return self._generate_text(prompt).strip()

    def _translate_markdown(self, markdown: str) -> str:
        prompt = (
            "Translate the following Japanese Markdown blog post into natural English.\n"
            "Requirements:\n"
            "- Preserve Markdown structure.\n"
            "- Preserve headings, lists, blockquotes, tables, and emphasis.\n"
            "- Preserve fenced code blocks, inline code, and URLs exactly.\n"
            "- Translate link text, but never alter link destinations.\n"
            "- Keep YAML front matter unchanged if present.\n"
            "- Return only the translated Markdown.\n\n"
            f"{markdown}"
        )
        return _unwrap_code_fence(self._generate_text(prompt))

    def _generate_text(self, prompt: str) -> str:
        response = self._http.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a professional English translator for blog articles. "
                            "Your output must be natural, concise, and publication-ready."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": -1,
            },
        )
        response.raise_for_status()
        payload = response.json()

        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError(f"LM Studio did not return a choice: {payload}")

        content = choices[0].get("message", {}).get("content", "").strip()
        if not content:
            raise RuntimeError(f"LM Studio returned empty content: {payload}")
        return content


def _unwrap_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text.strip()

    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text.strip()
