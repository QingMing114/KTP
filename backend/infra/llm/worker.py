"""Persistent Qwen worker process used by the shared planner/executor provider."""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def main() -> int:
    model_path = os.environ.get("AGENT_LLM_MODEL_PATH")
    device_map = os.environ.get("AGENT_LLM_DEVICE_MAP", "auto")
    dtype = os.environ.get("AGENT_LLM_DTYPE", "auto")
    require_accelerator = _is_truthy(os.environ.get("AGENT_LLM_REQUIRE_ACCELERATOR", "true"))
    if not model_path:
        _write_response(
            {
                "ok": False,
                "ready": False,
                "fatal": True,
                "error": "AGENT_LLM_MODEL_PATH is not configured.",
            }
        )
        return 1

    try:
        import torch
        from transformers import AutoProcessor, Qwen3VLMoeForConditionalGeneration
    except Exception as exc:  # pragma: no cover - depends on external runtime
        _write_response(
            {
                "ok": False,
                "ready": False,
                "fatal": True,
                "error": f"Failed to import transformers runtime: {exc}",
            }
        )
        return 1

    accelerator = _detect_accelerator(torch)
    if require_accelerator and accelerator is None:
        _write_response(
            {
                "ok": False,
                "ready": False,
                "fatal": True,
                "error": (
                    "No supported accelerator is available for the shared Qwen runtime. "
                    "CUDA/MPS was not detected."
                ),
            }
        )
        return 1

    try:
        model = _load_model(
            Qwen3VLMoeForConditionalGeneration,
            model_path=model_path,
            device_map=device_map,
            dtype=dtype,
        )
        processor = AutoProcessor.from_pretrained(model_path)
        model.eval()
    except Exception as exc:  # pragma: no cover - depends on external runtime
        _write_response(
            {
                "ok": False,
                "ready": False,
                "fatal": True,
                "error": f"Failed to load Qwen model: {exc}",
            }
        )
        return 1

    _write_response(
        {
            "ok": True,
            "ready": True,
            "runtime": {
                "accelerator": accelerator or "cpu",
                "device_map": device_map,
                "dtype": dtype,
                "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            },
        }
    )

    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            request = json.loads(stripped)
            text = _generate_text(model=model, processor=processor, request=request)
            _write_response({"ok": True, "text": text})
        except Exception as exc:  # pragma: no cover - runtime failure path
            _write_response({"ok": False, "error": str(exc)})
    return 0


def _load_model(
    model_cls,
    *,
    model_path: str,
    device_map: str,
    dtype: str,
):
    try:
        return model_cls.from_pretrained(
            model_path,
            dtype=dtype,
            device_map=device_map,
            low_cpu_mem_usage=True,
        )
    except TypeError:
        return model_cls.from_pretrained(
            model_path,
            torch_dtype=dtype,
            device_map=device_map,
            low_cpu_mem_usage=True,
        )


def _generate_text(*, model, processor, request: dict[str, Any]) -> str:
    messages = [
        {
            "role": "system",
            "content": [{"type": "text", "text": str(request["system_prompt"])}],
        },
        {
            "role": "user",
            "content": [{"type": "text", "text": str(request["user_prompt"])}],
        },
    ]
    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    )
    target_device = _detect_input_device(model)
    if target_device is not None:
        inputs = inputs.to(target_device)
    generation_kwargs: dict[str, Any] = {
        "max_new_tokens": int(request.get("max_new_tokens", 256)),
    }
    temperature = float(request.get("temperature", 0.0))
    if temperature > 0:
        generation_kwargs["do_sample"] = True
        generation_kwargs["temperature"] = temperature
        generation_kwargs["top_p"] = float(request.get("top_p", 0.9))
    generated_ids = model.generate(**inputs, **generation_kwargs)
    generated_ids_trimmed = [
        out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
    ]
    output_text = processor.batch_decode(
        generated_ids_trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )
    return str(output_text[0]).strip()


def _detect_input_device(model):
    device_map = getattr(model, "hf_device_map", None)
    if isinstance(device_map, dict):
        for device in device_map.values():
            normalized = _normalize_device(device)
            if normalized is not None:
                return normalized
    try:
        first_parameter = next(model.parameters())
    except StopIteration:  # pragma: no cover - defensive branch
        return None
    return first_parameter.device


def _normalize_device(device):
    if device in {None, "cpu", "disk"}:
        return None
    if isinstance(device, int):
        return f"cuda:{device}"
    return device


def _detect_accelerator(torch_module) -> str | None:
    if torch_module.cuda.is_available():
        return "cuda"
    mps_backend = getattr(torch_module.backends, "mps", None)
    if mps_backend is not None and mps_backend.is_available():
        return "mps"
    return None


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _write_response(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(main())
