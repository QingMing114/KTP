"""Shared provider interface for planner/executor local LLM access."""

from __future__ import annotations

import atexit
import json
import logging
import os
import re
import select
import subprocess
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol, TypeVar, get_args, get_origin

import httpx
from pydantic import BaseModel

from infra.llm.config import AgentLLMConfig, get_agent_llm_config
from infra.llm.gpu_selection import GPUSelectionError, resolve_cuda_visible_devices

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
StructuredModelT = TypeVar("StructuredModelT", bound=BaseModel)
_TRANSIENT_OPENAI_STATUS_CODES = frozenset({429, 502, 503, 504})


class AgentLLMError(RuntimeError):
    """Raised when the configured planner/executor LLM cannot be used."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "request_failed",
        request_kind: str | None = None,
        status_code: int | None = None,
        attempt_count: int | None = None,
        response_body_excerpt: str | None = None,
        prompt_chars: int | None = None,
        message_count: int | None = None,
        max_tokens: int | None = None,
        latency_ms: int | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.request_kind = request_kind
        self.status_code = status_code
        self.attempt_count = attempt_count
        self.response_body_excerpt = response_body_excerpt
        self.prompt_chars = prompt_chars
        self.message_count = message_count
        self.max_tokens = max_tokens
        self.latency_ms = latency_ms

    def to_payload(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "category": self.category,
                "request_kind": self.request_kind,
                "status_code": self.status_code,
                "attempt_count": self.attempt_count,
                "response_body_excerpt": self.response_body_excerpt,
                "prompt_chars": self.prompt_chars,
                "message_count": self.message_count,
                "max_tokens": self.max_tokens,
                "latency_ms": self.latency_ms,
            }.items()
            if value is not None
        }


class AgentLLMProvider(Protocol):
    """Provider contract for structured planner/executor generations."""

    def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
    ) -> str:
        """Generate a free-form text response."""

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[StructuredModelT],
    ) -> StructuredModelT:
        """Generate and validate a structured response."""


class SubprocessQwenVLProvider:
    """Shared Qwen provider backed by a persistent external Python worker."""

    def __init__(self, config: AgentLLMConfig) -> None:
        self._config = config
        self._process: subprocess.Popen[str] | None = None
        self._stderr_handle = None
        self._disabled_reason: str | None = None
        self._runtime_info: dict[str, Any] | None = None
        self._lock = threading.Lock()
        atexit.register(self.close)

    def close(self) -> None:
        """Terminate the background worker process when present."""
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                self._terminate_process(self._process)
            self._process = None
            if self._stderr_handle is not None:
                self._stderr_handle.close()
                self._stderr_handle = None

    def ensure_ready(self) -> dict[str, Any]:
        """Start the worker and return the negotiated runtime information."""
        with self._lock:
            self._ensure_process()
            return dict(self._runtime_info or {})

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[StructuredModelT],
    ) -> StructuredModelT:
        """Generate structured JSON through the background Qwen worker."""
        raw_text = self._generate_text(
            system_prompt=system_prompt,
            user_prompt=_build_structured_prompt(
                user_prompt=user_prompt,
                response_model=response_model,
            ),
            max_new_tokens=self._structured_max_tokens(),
        )
        payload = _extract_json_object(raw_text)
        try:
            return response_model.model_validate(payload)
        except Exception as exc:  # pragma: no cover - defensive validation branch
            raise AgentLLMError(f"Structured validation failed: {exc}") from exc

    def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
    ) -> str:
        """Generate a free-form text response through the background worker."""
        return self._generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_new_tokens=max_tokens or self._config.max_new_tokens,
        )

    def _generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int,
    ) -> str:
        with self._lock:
            process = self._ensure_process()
            request = {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "max_new_tokens": max_new_tokens,
                "temperature": self._config.temperature,
                "top_p": self._config.top_p,
            }
            if process.stdin is None or process.stdout is None:  # pragma: no cover
                raise AgentLLMError("LLM worker pipes are unavailable.")

            try:
                process.stdin.write(json.dumps(request, ensure_ascii=True) + "\n")
                process.stdin.flush()
            except BrokenPipeError as exc:
                self._reset_broken_process()
                raise AgentLLMError("LLM worker exited before accepting the request.") from exc

            response_line = self._readline_with_timeout(process.stdout)
            if not response_line:
                self._reset_broken_process()
                raise AgentLLMError(self._format_worker_failure())

        try:
            payload = json.loads(response_line)
        except json.JSONDecodeError as exc:
            raise AgentLLMError(f"LLM worker returned invalid JSON: {response_line!r}") from exc
        if not payload.get("ok", False):
            raise AgentLLMError(str(payload.get("error", "Unknown LLM worker error.")))
        return str(payload.get("text", "")).strip()

    def _structured_max_tokens(self) -> int:
        return max(64, min(self._config.max_new_tokens, self._config.structured_max_new_tokens))

    def _readline_with_timeout(self, stream) -> str:
        ready, _, _ = select.select(
            [stream],
            [],
            [],
            self._config.request_timeout_seconds,
        )
        if not ready:
            self._reset_broken_process()
            raise AgentLLMError(
                "LLM worker timed out after "
                f"{self._config.request_timeout_seconds:.1f}s. "
                "Falling back to deterministic logic."
            )
        return stream.readline()

    def _ensure_process(self) -> subprocess.Popen[str]:
        if self._disabled_reason is not None:
            raise AgentLLMError(self._disabled_reason)
        if self._process is not None and self._process.poll() is None:
            return self._process
        if not self._config.model_path:
            raise AgentLLMError("AGENT_LLM_MODEL_PATH is not configured.")

        stderr_path = Path(self._config.worker_log_path)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        self._stderr_handle = stderr_path.open("a", encoding="utf-8")
        try:
            resolved_cuda_visible_devices = resolve_cuda_visible_devices(
                self._config.cuda_visible_devices
            )
        except GPUSelectionError as exc:
            raise AgentLLMError(str(exc)) from exc
        env = os.environ.copy()
        env.update(
            {
                "AGENT_LLM_MODEL_PATH": self._config.model_path,
                "AGENT_LLM_DEVICE_MAP": self._config.device_map,
                "AGENT_LLM_DTYPE": self._config.dtype,
                "AGENT_LLM_REQUIRE_ACCELERATOR": str(self._config.require_accelerator).lower(),
            }
        )
        if resolved_cuda_visible_devices:
            env["CUDA_VISIBLE_DEVICES"] = resolved_cuda_visible_devices
        logger.info(
            "agent_llm_worker_starting | backend=%s | python=%s | model_path=%s | cuda_visible_devices=%s",
            self._config.backend,
            self._config.runtime_python,
            self._config.model_path,
            resolved_cuda_visible_devices or "inherit",
        )
        self._process = subprocess.Popen(
            [self._config.runtime_python, "-m", "infra.llm.worker"],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_handle,
            text=True,
            bufsize=1,
        )
        startup_payload = self._read_json_payload_with_timeout(
            self._process.stdout,
            timeout_seconds=self._config.startup_timeout_seconds,
            timeout_context="startup",
        )
        self._runtime_info = _parse_worker_startup_payload(startup_payload)
        return self._process

    def _format_worker_failure(self) -> str:
        detail = f"LLM worker exited unexpectedly. See {self._config.worker_log_path}."
        if self._process is not None and self._process.poll() is not None:
            detail = (
                f"LLM worker exited with code {self._process.returncode}. "
                f"See {self._config.worker_log_path}."
            )
        return detail

    def _reset_broken_process(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._terminate_process(self._process)
        self._process = None
        self._runtime_info = None

    @staticmethod
    def _terminate_process(process: subprocess.Popen[str]) -> None:
        try:
            process.terminate()
            process.wait(timeout=2)
            return
        except subprocess.TimeoutExpired:
            pass

        try:
            process.kill()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("agent_llm_worker_force_kill_timeout")

    def _read_json_payload_with_timeout(
        self,
        stream,
        *,
        timeout_seconds: float,
        timeout_context: str,
    ) -> dict[str, Any]:
        ready, _, _ = select.select(
            [stream],
            [],
            [],
            timeout_seconds,
        )
        if not ready:
            self._reset_broken_process()
            raise AgentLLMError(
                "LLM worker timed out during "
                f"{timeout_context} after {timeout_seconds:.1f}s."
            )

        response_line = stream.readline()
        if not response_line:
            self._reset_broken_process()
            raise AgentLLMError(self._format_worker_failure())

        try:
            payload = json.loads(response_line)
        except json.JSONDecodeError as exc:
            self._reset_broken_process()
            raise AgentLLMError(
                f"LLM worker returned invalid JSON during {timeout_context}: {response_line!r}"
            ) from exc

        if payload.get("ok", False):
            return payload

        error = str(payload.get("error", "Unknown LLM worker error."))
        if payload.get("fatal", False):
            self._disabled_reason = error
        self._reset_broken_process()
        raise AgentLLMError(error)


class OpenAICompatibleProvider:
    """Shared provider backed by an OpenAI-compatible REST API (e.g., vLLM, OpenAI)."""

    def __init__(self, config: AgentLLMConfig) -> None:
        self._config = config
        self.last_call_metadata: dict[str, Any] = {}
        self._client = httpx.Client(
            base_url=self._config.openai_api_base,
            headers={"Authorization": f"Bearer {self._config.openai_api_key}"},
            timeout=self._config.request_timeout_seconds,
        )

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[StructuredModelT],
    ) -> StructuredModelT:
        """Generate structured JSON via the chat completions API."""
        structured_prompt = _build_structured_prompt(
            user_prompt=user_prompt,
            response_model=response_model,
        )
        budgets = [self._structured_max_tokens()]
        retry_budget = min(
            self._config.max_new_tokens,
            max(self._structured_max_tokens() * 2, 768),
        )
        if retry_budget > budgets[0]:
            budgets.append(retry_budget)

        last_error: AgentLLMError | None = None
        for budget_index, budget in enumerate(budgets):
            try:
                raw_text = self._generate_text(
                    system_prompt=system_prompt,
                    user_prompt=structured_prompt,
                    max_tokens=budget,
                    request_kind="structured_planner",
                )
                break
            except AgentLLMError as exc:
                last_error = exc
                if exc.category == "incomplete_generation" and budget_index < len(budgets) - 1:
                    logger.info(
                        "agent_llm_structured_retrying_for_incomplete_generation | initial_budget=%s | retry_budget=%s",
                        budget,
                        budgets[budget_index + 1],
                    )
                    continue
                raise
        else:
            assert last_error is not None
            raise last_error
        payload = _extract_json_object(raw_text)
        alias_applied = False
        if "response_message" in response_model.model_fields:
            content_alias = payload.get("content")
            if isinstance(content_alias, str) and content_alias.strip() and not payload.get("response_message"):
                payload["response_message"] = content_alias.strip()
                alias_applied = True
                self.last_call_metadata = {
                    **self.last_call_metadata,
                    "schema_alias_applied": True,
                }
                logger.info(
                    "agent_llm_schema_alias_applied | request_kind=structured_planner | alias=content->response_message"
                )
        payload, structured_alias_applied = _normalize_structured_payload(payload, response_model=response_model)
        if structured_alias_applied:
            alias_applied = True
            self.last_call_metadata = {
                **self.last_call_metadata,
                "schema_alias_applied": True,
            }
            logger.info(
                "agent_llm_schema_alias_applied | request_kind=structured_planner | alias=tool_call_fields"
            )
        try:
            return response_model.model_validate(payload)
        except Exception as exc:  # pragma: no cover
            response_excerpt = _compact_text(raw_text, limit=240)
            self._record_call_metadata(
                request_kind="structured_planner",
                prompt_chars=len(system_prompt) + len(user_prompt),
                message_count=2,
                max_tokens=self._structured_max_tokens(),
                latency_ms=None,
                status_code=200,
                response_body_excerpt=response_excerpt,
                schema_alias_applied=alias_applied,
                error_category="schema_mismatch",
            )
            raise AgentLLMError(
                f"Upstream LLM returned a structured response that did not match the planner contract: {exc}",
                category="schema_mismatch",
                request_kind="structured_planner",
                status_code=200,
                response_body_excerpt=response_excerpt,
                prompt_chars=len(system_prompt) + len(user_prompt),
                message_count=2,
                max_tokens=self._structured_max_tokens(),
            ) from exc

    def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
    ) -> str:
        """Generate a free-form text response via the chat completions API."""
        return self._generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens or self._config.max_new_tokens,
            request_kind="direct_reply",
        )

    def _generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        request_kind: str,
    ) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        request_payload = {
            "model": self._config.openai_model_name,
            "messages": messages,
            "temperature": self._config.temperature,
            "top_p": self._config.top_p,
            "max_tokens": max_tokens,
        }
        if self._should_disable_thinking(request_kind=request_kind):
            request_payload["chat_template_kwargs"] = {"enable_thinking": False}

        total_attempts = max(1, self._config.openai_max_retries + 1)
        prompt_chars = sum(len(_content_to_text(item.get("content"))) for item in messages)
        self.last_call_metadata = {}
        for attempt_index in range(total_attempts):
            start_time = time.perf_counter()
            try:
                response = self._client.post("/chat/completions", json=request_payload)
                response.raise_for_status()
                data = response.json()
                choice = data["choices"][0]
                message = choice["message"]
                finish_reason = choice.get("finish_reason")
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                response_body_excerpt = _compact_text(response.text, limit=240)
                content = _content_to_text(message.get("content"))
                reasoning = _content_to_text(
                    message.get("reasoning") or message.get("reasoning_content")
                )
                if finish_reason == "length":
                    raise AgentLLMError(
                        "Upstream LLM output was truncated because it hit the max token budget.",
                        category="incomplete_generation",
                        request_kind=request_kind,
                        status_code=response.status_code,
                        attempt_count=attempt_index + 1,
                        response_body_excerpt=response_body_excerpt,
                        prompt_chars=prompt_chars,
                        message_count=len(messages),
                        max_tokens=max_tokens,
                        latency_ms=latency_ms,
                    )
                if request_kind == "direct_reply":
                    if content:
                        self._record_success(
                            request_kind=request_kind,
                            prompt_chars=prompt_chars,
                            message_count=len(messages),
                            max_tokens=max_tokens,
                            latency_ms=latency_ms,
                            status_code=response.status_code,
                            response_body_excerpt=response_body_excerpt,
                            attempt_count=attempt_index + 1,
                        )
                        return content
                    if reasoning:
                        raise AgentLLMError(
                            "Upstream LLM returned reasoning without a final answer.",
                            category="incomplete_generation",
                            request_kind=request_kind,
                            status_code=response.status_code,
                            attempt_count=attempt_index + 1,
                            response_body_excerpt=_compact_text(reasoning, limit=240),
                            prompt_chars=prompt_chars,
                            message_count=len(messages),
                            max_tokens=max_tokens,
                            latency_ms=latency_ms,
                        )
                combined_text = "\n".join(part for part in (reasoning, content) if part).strip()
                if combined_text:
                    self._record_success(
                        request_kind=request_kind,
                        prompt_chars=prompt_chars,
                        message_count=len(messages),
                        max_tokens=max_tokens,
                        latency_ms=latency_ms,
                        status_code=response.status_code,
                        response_body_excerpt=response_body_excerpt,
                        attempt_count=attempt_index + 1,
                    )
                    return combined_text
                raise AgentLLMError(
                    "Upstream LLM returned an empty assistant message.",
                    category="incomplete_generation",
                    request_kind=request_kind,
                    status_code=response.status_code,
                    attempt_count=attempt_index + 1,
                    response_body_excerpt=response_body_excerpt,
                    prompt_chars=prompt_chars,
                    message_count=len(messages),
                    max_tokens=max_tokens,
                    latency_ms=latency_ms,
                )
            except httpx.TimeoutException as exc:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                error = AgentLLMError(
                    "Upstream LLM unavailable or overloaded: request timed out.",
                    category="upstream_overloaded",
                    request_kind=request_kind,
                    attempt_count=attempt_index + 1,
                    prompt_chars=prompt_chars,
                    message_count=len(messages),
                    max_tokens=max_tokens,
                    latency_ms=latency_ms,
                )
                self._record_error(error)
                if attempt_index < total_attempts - 1:
                    self._sleep_before_retry(attempt_index)
                    continue
                raise error from exc
            except httpx.HTTPStatusError as exc:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                status_code = exc.response.status_code
                response_excerpt = _compact_text(exc.response.text, limit=240)
                category = (
                    "upstream_overloaded"
                    if status_code in _TRANSIENT_OPENAI_STATUS_CODES
                    else "request_failed"
                )
                error = AgentLLMError(
                    self._format_http_status_error(
                        exc,
                        attempt_count=attempt_index + 1,
                        category=category,
                    ),
                    category=category,
                    request_kind=request_kind,
                    status_code=status_code,
                    attempt_count=attempt_index + 1,
                    response_body_excerpt=response_excerpt,
                    prompt_chars=prompt_chars,
                    message_count=len(messages),
                    max_tokens=max_tokens,
                    latency_ms=latency_ms,
                )
                self._record_error(error)
                if (
                    status_code in _TRANSIENT_OPENAI_STATUS_CODES
                    and attempt_index < total_attempts - 1
                ):
                    self._sleep_before_retry(attempt_index)
                    continue
                raise error from exc
            except AgentLLMError as exc:
                self._record_error(exc)
                raise
            except Exception as exc:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                error = AgentLLMError(
                    f"LLM API request failed: {exc}",
                    category="request_failed",
                    request_kind=request_kind,
                    attempt_count=attempt_index + 1,
                    prompt_chars=prompt_chars,
                    message_count=len(messages),
                    max_tokens=max_tokens,
                    latency_ms=latency_ms,
                )
                self._record_error(error)
                raise error from exc
        raise AgentLLMError("LLM API request failed after exhausting all retry attempts.")

    def _should_disable_thinking(self, *, request_kind: str) -> bool:
        if request_kind not in {"direct_reply", "structured_planner"}:
            return False
        if self._config.openai_disable_thinking:
            return True
        return "qwen3" in self._config.openai_model_name.lower()

    def _structured_max_tokens(self) -> int:
        return max(64, min(self._config.max_new_tokens, self._config.structured_max_new_tokens))

    def _sleep_before_retry(self, attempt_index: int) -> None:
        backoff_seconds = self._config.openai_retry_backoff_seconds * (2**attempt_index)
        if backoff_seconds > 0:
            time.sleep(backoff_seconds)

    def _record_success(
        self,
        *,
        request_kind: str,
        prompt_chars: int,
        message_count: int,
        max_tokens: int,
        latency_ms: int,
        status_code: int,
        response_body_excerpt: str | None,
        attempt_count: int,
    ) -> None:
        self._record_call_metadata(
            request_kind=request_kind,
            prompt_chars=prompt_chars,
            message_count=message_count,
            max_tokens=max_tokens,
            latency_ms=latency_ms,
            status_code=status_code,
            response_body_excerpt=response_body_excerpt,
            attempt_count=attempt_count,
            error_category=None,
        )
        logger.info(
            "agent_llm_request_succeeded | request_kind=%s | prompt_chars=%s | message_count=%s | max_tokens=%s | latency_ms=%s | status_code=%s | response_body_excerpt=%s",
            request_kind,
            prompt_chars,
            message_count,
            max_tokens,
            latency_ms,
            status_code,
            response_body_excerpt or "",
        )

    def _record_error(self, error: AgentLLMError) -> None:
        self._record_call_metadata(
            request_kind=error.request_kind or "unknown",
            prompt_chars=error.prompt_chars or 0,
            message_count=error.message_count or 0,
            max_tokens=error.max_tokens or 0,
            latency_ms=error.latency_ms,
            status_code=error.status_code,
            response_body_excerpt=error.response_body_excerpt,
            attempt_count=error.attempt_count,
            error_category=error.category,
        )
        logger.warning(
            "agent_llm_request_failed | request_kind=%s | prompt_chars=%s | message_count=%s | max_tokens=%s | latency_ms=%s | status_code=%s | error_category=%s | response_body_excerpt=%s",
            error.request_kind or "unknown",
            error.prompt_chars or 0,
            error.message_count or 0,
            error.max_tokens or 0,
            error.latency_ms if error.latency_ms is not None else -1,
            error.status_code if error.status_code is not None else -1,
            error.category,
            error.response_body_excerpt or "",
        )

    def _record_call_metadata(
        self,
        *,
        request_kind: str,
        prompt_chars: int,
        message_count: int,
        max_tokens: int,
        latency_ms: int | None,
        status_code: int | None,
        response_body_excerpt: str | None,
        attempt_count: int | None = None,
        error_category: str | None = None,
        schema_alias_applied: bool | None = None,
    ) -> None:
        metadata = {
            "request_kind": request_kind,
            "prompt_chars": prompt_chars,
            "message_count": message_count,
            "max_tokens": max_tokens,
            "latency_ms": latency_ms,
            "status_code": status_code,
            "response_body_excerpt": response_body_excerpt,
            "attempt_count": attempt_count,
            "error_category": error_category,
        }
        if schema_alias_applied is not None:
            metadata["schema_alias_applied"] = schema_alias_applied
        self.last_call_metadata = {key: value for key, value in metadata.items() if value is not None}

    @staticmethod
    def _format_http_status_error(
        exc: httpx.HTTPStatusError,
        *,
        attempt_count: int,
        category: str,
    ) -> str:
        if category == "upstream_overloaded":
            detail = (
                "Upstream LLM unavailable or overloaded after "
                f"{attempt_count} attempt(s): {exc}"
            )
        else:
            detail = f"LLM API request failed after {attempt_count} attempt(s): {exc}"
        response = exc.response
        response_text = ""
        try:
            response_text = response.text.strip()
        except Exception:  # pragma: no cover - defensive branch
            response_text = ""
        if response_text:
            compact_text = " ".join(response_text.split())
            detail = f"{detail} | response_body={compact_text[:240]}"
        return detail


@lru_cache(maxsize=1)
def get_agent_llm_provider() -> AgentLLMProvider | None:
    """Return the configured shared provider for planner and executor."""
    config = get_agent_llm_config()
    if config.backend == "heuristic":
        return None
    if config.backend == "subprocess_qwen":
        return SubprocessQwenVLProvider(config)
    if config.backend == "openai_compatible":
        return OpenAICompatibleProvider(config)
    raise AgentLLMError(f"Unsupported agent LLM backend: {config.backend}")


def warm_up_agent_llm_provider() -> dict[str, Any] | None:
    """Start the configured worker eagerly and return runtime details when available."""
    provider = get_agent_llm_provider()
    if provider is None:
        return None
    if isinstance(provider, SubprocessQwenVLProvider):
        return provider.ensure_ready()
    return None


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    sanitized = raw_text.strip()
    if sanitized.startswith("```"):
        sanitized = sanitized.strip("`")
        sanitized = sanitized.removeprefix("json").strip()
    start = sanitized.find("{")
    if start == -1:
        raise AgentLLMError(f"Model response does not contain JSON: {raw_text!r}")

    depth = 0
    end = -1
    for index in range(start, len(sanitized)):
        char = sanitized[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end == -1:
        salvaged_payload = _salvage_incomplete_json_object(sanitized[start:])
        if salvaged_payload is not None:
            return salvaged_payload
        raise AgentLLMError(f"Model response contains incomplete JSON: {raw_text!r}")

    try:
        payload = json.loads(sanitized[start:end])
    except json.JSONDecodeError as exc:
        salvaged_payload = _salvage_incomplete_json_object(sanitized[start:end])
        if salvaged_payload is not None:
            return salvaged_payload
        raise AgentLLMError(f"Model response JSON decoding failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise AgentLLMError("Model response JSON must be an object.")
    return payload


def _normalize_structured_payload(
    payload: dict[str, Any],
    *,
    response_model: type[StructuredModelT],
) -> tuple[dict[str, Any], bool]:
    normalized_payload = dict(payload)
    alias_applied = False

    if "reasoning" in response_model.model_fields and not normalized_payload.get("reasoning"):
        for alias_key in ("reason", "reasoning_summary", "rationale", "analysis", "thought"):
            alias_value = normalized_payload.get(alias_key)
            if isinstance(alias_value, str) and alias_value.strip():
                normalized_payload["reasoning"] = alias_value.strip()
                alias_applied = True
                break
        else:
            if normalized_payload.get("action") and (
                normalized_payload.get("response_message")
                or normalized_payload.get("content")
                or normalized_payload.get("tool_calls")
            ):
                normalized_payload["reasoning"] = "Recovered missing reasoning from the upstream structured response."
                alias_applied = True

    if "response_message" in response_model.model_fields and not normalized_payload.get("response_message"):
        for alias_key in ("answer", "response", "message"):
            alias_value = normalized_payload.get(alias_key)
            if isinstance(alias_value, str) and alias_value.strip():
                normalized_payload["response_message"] = alias_value.strip()
                alias_applied = True
                break

    if "tool_calls" not in response_model.model_fields:
        return normalized_payload, alias_applied
    raw_tool_calls = normalized_payload.get("tool_calls")
    if not isinstance(raw_tool_calls, list):
        return normalized_payload, alias_applied

    normalized_tool_calls: list[Any] = []
    for item in raw_tool_calls:
        if not isinstance(item, dict):
            normalized_tool_calls.append(item)
            continue
        normalized_item = dict(item)

        function_payload = normalized_item.get("function")
        if isinstance(function_payload, dict):
            if "tool_name" not in normalized_item and isinstance(function_payload.get("name"), str):
                normalized_item["tool_name"] = function_payload["name"]
                alias_applied = True
            if "tool_input" not in normalized_item and "arguments" in function_payload:
                parsed_arguments = _parse_tool_arguments(function_payload.get("arguments"))
                if parsed_arguments is not None:
                    normalized_item["tool_input"] = parsed_arguments
                    alias_applied = True

        if "tool_name" not in normalized_item:
            for alias_key in ("name", "tool", "toolName"):
                alias_value = normalized_item.get(alias_key)
                if isinstance(alias_value, str) and alias_value.strip():
                    normalized_item["tool_name"] = alias_value.strip()
                    alias_applied = True
                    break

        if "call_id" not in normalized_item and isinstance(normalized_item.get("id"), str):
            normalized_item["call_id"] = normalized_item["id"]
            alias_applied = True

        if "tool_input" not in normalized_item:
            for alias_key in ("input", "params", "arguments"):
                parsed_value = _parse_tool_arguments(normalized_item.get(alias_key))
                if parsed_value is not None:
                    normalized_item["tool_input"] = parsed_value
                    alias_applied = True
                    break

        if "tool_input" not in normalized_item:
            residual_input = {
                key: value
                for key, value in normalized_item.items()
                if key
                not in {
                    "tool_name",
                    "name",
                    "tool",
                    "toolName",
                    "call_id",
                    "id",
                    "type",
                    "function",
                }
            }
            if residual_input:
                normalized_item["tool_input"] = residual_input
                alias_applied = True

        normalized_tool_calls.append(normalized_item)

    if not alias_applied:
        return normalized_payload, False
    normalized_payload["tool_calls"] = normalized_tool_calls
    return normalized_payload, True


def _parse_tool_arguments(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return {}
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


def _salvage_incomplete_json_object(raw_fragment: str) -> dict[str, Any] | None:
    action = _extract_string_field(raw_fragment, "action")
    if action is None:
        return None

    payload: dict[str, Any] = {
        "action": action,
        "reason": _extract_string_field(raw_fragment, "reason") or "salvaged_incomplete_json",
    }

    for field_name in (
        "answer",
        "content",
        "response_message",
        "rewritten_query",
        "workflow_message",
        "region",
        "crop_type",
        "task_type",
        "normalized_message",
    ):
        value = _extract_string_field(raw_fragment, field_name)
        if value is not None:
            payload[field_name] = value

    for field_name in (
        "need_training",
        "need_rag",
        "need_report",
        "need_confidence",
    ):
        value = _extract_boolean_field(raw_fragment, field_name)
        if value is not None:
            payload[field_name] = value

    return payload


def _extract_string_field(raw_fragment: str, field_name: str) -> str | None:
    closed_pattern = rf'"{re.escape(field_name)}"\s*:\s*"((?:\\.|[^"\\])*)"'
    match = re.search(closed_pattern, raw_fragment, re.DOTALL)
    if match:
        return _decode_json_string_fragment(match.group(1))

    partial_pattern = rf'"{re.escape(field_name)}"\s*:\s*"(.+)$'
    match = re.search(partial_pattern, raw_fragment, re.DOTALL)
    if not match:
        return None
    raw_value = match.group(1).strip()
    for terminator in ('",', '"}', '"\n'):
        if terminator in raw_value:
            raw_value = raw_value.split(terminator, 1)[0]
            break
    return _decode_json_string_fragment(raw_value)


def _extract_boolean_field(raw_fragment: str, field_name: str) -> bool | None:
    match = re.search(rf'"{re.escape(field_name)}"\s*:\s*(true|false)', raw_fragment)
    if match is None:
        return None
    return match.group(1) == "true"


def _decode_json_string_fragment(raw_value: str) -> str:
    try:
        return json.loads(f'"{raw_value}"')
    except json.JSONDecodeError:
        return (
            raw_value.replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
            .strip()
        )


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text_value = item.get("text")
                if isinstance(text_value, str) and text_value.strip():
                    parts.append(text_value.strip())
            elif isinstance(item, str) and item.strip():
                parts.append(item.strip())
        return "\n".join(parts).strip()
    return str(content).strip()


def _compact_text(value: str, *, limit: int) -> str:
    compact = " ".join(value.strip().split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _build_structured_prompt(
    *,
    user_prompt: str,
    response_model: type[StructuredModelT],
) -> str:
    schema_contract = _build_response_contract(response_model)
    return (
        f"User Input:\n{user_prompt}\n\n"
        "Instructions:\n"
        "Return exactly one valid JSON object. Do not wrap it in markdown. Do not include any text before or after the JSON.\n"
        "Use null for missing optional fields.\n"
        f"Required JSON keys and types:\n{json.dumps(schema_contract, ensure_ascii=True, sort_keys=True)}\n\n"
        "Example Output Format:\n"
        '{"action": "call_tools", "reasoning": "需要执行模拟", "tool_calls": [{"tool_name": "prosail.simulation", "tool_input": {"lai": 3.0}}]}\n\n'
        "Now, output the final JSON based on the User Input:"
    )


def _build_response_contract(response_model: type[BaseModel]) -> dict[str, str]:
    contract: dict[str, str] = {}
    for field_name, field_info in response_model.model_fields.items():
        contract[field_name] = _describe_annotation(field_info.annotation)
    return contract


def _parse_worker_startup_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("ready", False):
        raise AgentLLMError("LLM worker did not report a ready state.")
    runtime = payload.get("runtime", {})
    if not isinstance(runtime, dict):
        raise AgentLLMError("LLM worker runtime payload must be an object.")
    return runtime


def _describe_annotation(annotation: Any) -> str:
    origin = get_origin(annotation)
    if origin is None:
        if annotation is str:
            return "string"
        if annotation is int:
            return "integer"
        if annotation is float:
            return "number"
        if annotation is bool:
            return "boolean"
        if annotation is dict:
            return "object"
        if annotation is list:
            return "array"
        if annotation is Any:
            return "any"
        return "object"

    if origin in {list, tuple, set}:
        item_types = get_args(annotation)
        if not item_types:
            return "array"
        return f"array[{_describe_annotation(item_types[0])}]"

    if origin is dict:
        return "object"

    if origin is type(None):
        return "null"

    union_types = [item for item in get_args(annotation) if item is not type(None)]
    if union_types and len(union_types) != len(get_args(annotation)):
        rendered = "|".join(_describe_annotation(item) for item in union_types)
        return f"{rendered}|null"

    return "object"
