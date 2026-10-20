"""Cerebros creativos locales: Ollama y servidores compatibles con OpenAI (LM Studio, llama.cpp, vLLM)."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import httpx

from ...config import get_config
from ..base import Engine, EngineStatus


def extract_json(text: str) -> dict | list | None:
    """Extrae el primer bloque JSON de una respuesta (tolerante a ```json y texto alrededor)."""
    if not text:
        return None
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    return None


class LLMEngine(Engine):
    capabilities = {"llm"}

    async def chat(self, system: str, user: str, *, json_mode: bool = False, temperature: float = 0.9, images: list[Path] | None = None, max_tokens: int = 4096) -> str:
        raise NotImplementedError

    async def chat_json(self, system: str, user: str, temperature: float = 0.9, images: list[Path] | None = None) -> dict | list | None:
        txt = await self.chat(system, user, json_mode=True, temperature=temperature, images=images)
        return extract_json(txt)


class OllamaEngine(LLMEngine):
    id = "ollama"
    name = "Ollama (LLM local)"
    description = "Qwen3, Llama, Gemma, Mistral… El guionista y director creativo de durosTCM. Con modelos de visión describe rostros de inspiración."
    capabilities = {"llm", "vision"}
    quality = "pro"

    def _url(self) -> str:
        return get_config().settings.endpoints.ollama_url.rstrip("/")

    async def models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=3, trust_env=False) as c:
            r = await c.get(self._url() + "/api/tags")
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]

    async def status(self) -> EngineStatus:
        try:
            ms = await self.models()
        except Exception:
            return EngineStatus(available=False, detail=f"No responde en {self._url()} (instala Ollama)", quality="pro")
        if not ms:
            return EngineStatus(available=False, detail="Ollama sin modelos: ollama pull qwen3:8b", quality="pro")
        want = get_config().settings.endpoints.ollama_model
        detail = want if any(m.startswith(want.split(":")[0]) for m in ms) else f"{ms[0]} (no está {want})"
        return EngineStatus(available=True, detail=detail, models=ms, quality="pro")

    async def _pick_model(self, vision: bool) -> str:
        ep = get_config().settings.endpoints
        want = ep.ollama_vision_model if vision else ep.ollama_model
        try:
            ms = await self.models()
        except Exception:
            return want
        if want in ms:
            return want
        base = want.split(":")[0]
        for m in ms:
            if m.startswith(base):
                return m
        if vision:
            for m in ms:
                if any(k in m for k in ("vl", "llava", "vision", "gemma3", "minicpm-v", "moondream")):
                    return m
        return ms[0] if ms else want

    async def chat(self, system: str, user: str, *, json_mode: bool = False, temperature: float = 0.9, images: list[Path] | None = None, max_tokens: int = 4096) -> str:
        model = await self._pick_model(bool(images))
        msg: dict = {"role": "user", "content": user}
        if images:
            msg["images"] = [base64.b64encode(Path(p).read_bytes()).decode() for p in images]
        payload: dict = {
            "model": model,
            "messages": [{"role": "system", "content": system}, msg],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"
        if "qwen3" in model:
            payload["think"] = False
        async with httpx.AsyncClient(timeout=600, trust_env=False) as c:
            r = await c.post(self._url() + "/api/chat", json=payload)
            if r.status_code == 400 and "think" in payload:
                payload.pop("think")
                r = await c.post(self._url() + "/api/chat", json=payload)
            r.raise_for_status()
            return r.json().get("message", {}).get("content", "")


class OpenAICompatEngine(LLMEngine):
    id = "openai_compat"
    name = "Servidor compatible OpenAI (local)"
    description = "LM Studio, llama.cpp server, vLLM, Jan… cualquier endpoint /v1/chat/completions local."
    capabilities = {"llm", "vision"}
    quality = "pro"

    def _cfg(self) -> tuple[str, str]:
        ep = get_config().settings.endpoints
        return ep.openai_compat_url.rstrip("/"), ep.openai_compat_model

    async def status(self) -> EngineStatus:
        url, model = self._cfg()
        if not url:
            return EngineStatus(available=False, detail="Sin configurar")
        try:
            async with httpx.AsyncClient(timeout=3, trust_env=False) as c:
                r = await c.get(url + "/models")
                r.raise_for_status()
                ms = [m.get("id", "") for m in r.json().get("data", [])]
            return EngineStatus(available=True, detail=model or (ms[0] if ms else ""), models=ms)
        except Exception:
            return EngineStatus(available=False, detail=f"No responde en {url}")

    async def chat(self, system: str, user: str, *, json_mode: bool = False, temperature: float = 0.9, images: list[Path] | None = None, max_tokens: int = 4096) -> str:
        url, model = self._cfg()
        content: list | str = user
        if images:
            content = [{"type": "text", "text": user}] + [
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(Path(p).read_bytes()).decode()}} for p in images
            ]
        payload: dict = {
            "model": model or "local",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=600, trust_env=False) as c:
            r = await c.post(url + "/chat/completions", json=payload)
            if r.status_code >= 400 and json_mode:
                payload.pop("response_format", None)
                r = await c.post(url + "/chat/completions", json=payload)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
