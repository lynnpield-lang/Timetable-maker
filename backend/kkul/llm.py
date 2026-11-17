"""LLM 호출 공통 (키 읽기, 타임아웃, JSON 스키마 검증, 근거 검사).

- 숫자는 코드가 계산하고 LLM은 추출·판단·설명만 한다.
- 응답은 반드시 call_json으로 pydantic 스키마 검증. 실패하면 None → 호출한 쪽은 LLM 없이 동작.
- os.environ은 이 파일과 main.py에서만 읽는다.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from kkul import io

log = logging.getLogger(__name__)

DEFAULT_MODELS = {"anthropic": "claude-opus-5-5", "openai": "gpt-4o"}
MAX_TOKENS = 16_000


@dataclass(frozen=True)
class Image:
    data: bytes
    media_type: str = "image/png"


def _settings() -> tuple[str, str | None, str]:
    provider = (os.environ.get("LLM_PROVIDER") or "anthropic").strip().lower()
    key = os.environ.get("LLM_API_KEY") or None
    model = os.environ.get("LLM_MODEL") or DEFAULT_MODELS.get(provider, "")
    return provider, key, model


def available() -> bool:
    """LLM 키가 설정돼 있는지 (없으면 화면에서 LLM 버튼을 숨긴다)."""
    _, key, _ = _settings()
    return bool(key)


def _extract_json(text: str) -> str:
    """응답 문자열에서 JSON 부분만 꺼낸다 (```json 블록 허용)."""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        return m.group(1).strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        return text.strip()
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    return text[start : end + 1] if end > start else text[start:]


def _call_anthropic(
    key: str, model: str, system: str, prompt: str, images: list[Image], timeout: float
) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=key, timeout=timeout, max_retries=1)
    content: list[dict] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img.media_type,
                "data": base64.standard_b64encode(img.data).decode("utf-8"),
            },
        }
        for img in images
    ]
    content.append({"type": "text", "text": prompt})
    resp = client.beta.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": content}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("LLM이 요청을 거절함")
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def _call_openai(
    key: str, model: str, system: str, prompt: str, images: list[Image], timeout: float
) -> str:
    try:
        import openai  # 선택 의존성: 설치돼 있을 때만
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("openai 패키지가 없음 (uv add openai)") from e
    client = openai.OpenAI(api_key=key, timeout=timeout, max_retries=1)
    content: list[dict] = [{"type": "text", "text": prompt}]
    for img in images:
        b64 = base64.standard_b64encode(img.data).decode("utf-8")
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:{img.media_type};base64,{b64}"}}
        )
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
    )
    return resp.choices[0].message.content or ""


def call_text(
    task: str,
    prompt: str,
    *,
    system: str = "",
    images: list[Image] | None = None,
    timeout: float = 10,
    use_cache: bool = True,
) -> str | None:
    """LLM에 보내고 응답 문자열을 받는다. 키 없음·시간 초과·오류면 None."""
    provider, key, model = _settings()
    if not key:
        return None
    images = images or []
    cache_payload = json.dumps(
        {
            "model": model,
            "system": system,
            "prompt": prompt,
            "images": [base64.b64encode(i.data).decode()[:64] + str(len(i.data)) for i in images],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    if use_cache:
        cached = io.read_llm_cache(task, cache_payload)
        if cached is not None:
            return cached
    try:
        if provider == "openai":
            text = _call_openai(key, model, system, prompt, images, timeout)
        else:
            text = _call_anthropic(key, model, system, prompt, images, timeout)
    except Exception as e:  # 네트워크·타임아웃·거절 모두 LLM 없이 진행
        log.warning("LLM 호출 실패 (%s): %s", task, type(e).__name__)
        return None
    if use_cache:
        try:
            io.write_llm_cache(task, cache_payload, text)
        except OSError:
            pass
    return text


def call_json(
    task: str,
    prompt: str,
    schema: type[BaseModel],
    timeout: float = 10,
    *,
    system: str | None = None,
    images: list[Image] | None = None,
    use_cache: bool = True,
) -> BaseModel | None:
    """LLM에 보내고 응답을 schema로 검증해 돌려준다. 실패하면 None."""
    sys_prompt = system if system is not None else _default_system(task)
    sys_prompt += (
        "\n\n반드시 아래 JSON 스키마에 맞는 JSON 하나만 출력한다. 설명 문장을 붙이지 않는다.\n"
        + json.dumps(schema.model_json_schema(), ensure_ascii=False)
    )
    text = call_text(
        task, prompt, system=sys_prompt, images=images, timeout=timeout, use_cache=use_cache
    )
    if text is None:
        return None
    try:
        return schema.model_validate_json(_extract_json(text))
    except (ValidationError, ValueError) as e:
        log.warning("LLM 응답 스키마 검증 실패 (%s): %s", task, str(e)[:200])
        return None


def _default_system(task: str) -> str:
    try:
        return io.read_prompt(task)
    except OSError:
        return "너는 꿀시간표 도우미다. 주어진 입력에 있는 사실만 사용한다."


# ------------------------------------------------------------------ 근거 검사

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_KEY_RE = re.compile(r"[A-Z]{2,4}\d{3,4}(?:-\d{2})?")


def normalize_space(s: str) -> str:
    """공백을 하나로 줄이고 앞뒤를 자른다 (근거 인용 비교용)."""
    return re.sub(r"\s+", " ", s).strip()


def quote_in_source(quote: str | None, source: str) -> bool:
    """근거 인용이 원문에 실제로 있는지 (공백 정규화 후 부분 문자열 검사)."""
    if not quote:
        return False
    q = normalize_space(quote).lower()
    return bool(q) and q in normalize_space(source).lower()


def numbers_in(text: str) -> set[str]:
    """문장에 나온 숫자들 (정규화: 0.50 → 0.5, 50.0 → 50)."""
    out = set()
    for m in _NUM_RE.findall(text):
        f = float(m)
        out.add(str(int(f)) if f.is_integer() else str(f).rstrip("0").rstrip("."))
    return out


def keys_in(text: str) -> set[str]:
    return set(_KEY_RE.findall(text))


def sentence_is_grounded(sentence: str, allowed_numbers: set[str], allowed_keys: set[str]) -> bool:
    """문장의 숫자·학수번호가 모두 입력에 있는지."""
    for k in keys_in(sentence):
        if k not in allowed_keys and k.split("-")[0] not in allowed_keys:
            return False
    return numbers_in(sentence) <= allowed_numbers


def allowed_from_input(obj) -> tuple[set[str], set[str]]:
    """입력 JSON에서 허용 숫자·학수번호 집합을 만든다 (퍼센트 변환 포함)."""
    text = json.dumps(obj, ensure_ascii=False)
    nums = numbers_in(text)
    extra = set()
    for n in list(nums):
        f = float(n)
        if 0 <= f <= 1:  # 0.71 → 71%
            extra |= numbers_in(f"{round(f * 100)} {round(f * 100, 1)}")
        extra |= numbers_in(f"{round(f)} {round(f, 1)}")
    keys = keys_in(text)
    keys |= {k.split("-")[0] for k in keys}
    return nums | extra, keys


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。])\s+|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def keep_grounded(text: str, source_obj) -> str:
    """입력에 없는 숫자·학수번호가 나온 문장을 버린다."""
    nums, keys = allowed_from_input(source_obj)
    kept = [s for s in split_sentences(text) if sentence_is_grounded(s, nums, keys)]
    return " ".join(kept)
