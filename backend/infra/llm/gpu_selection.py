"""Helpers for dynamic GPU selection for the shared local LLM worker."""

from __future__ import annotations

from dataclasses import dataclass
import subprocess


class GPUSelectionError(RuntimeError):
    """Raised when runtime GPU selection cannot be completed."""


@dataclass(frozen=True)
class GPUStatus:
    """Structured snapshot for one visible GPU."""

    index: int
    memory_used_mb: int
    memory_total_mb: int
    utilization_gpu_percent: int

    @property
    def memory_free_mb(self) -> int:
        """Return currently free memory for the GPU."""
        return self.memory_total_mb - self.memory_used_mb


def resolve_cuda_visible_devices(configured_value: str | None) -> str | None:
    """Resolve a CUDA device selector, including dynamic `auto:<count>` values."""
    if configured_value is None:
        return None

    normalized = configured_value.strip()
    if not normalized:
        return None

    if normalized.startswith("auto:"):
        try:
            count = int(normalized.split(":", maxsplit=1)[1])
        except ValueError as exc:
            raise GPUSelectionError(
                f"Invalid AGENT_LLM_CUDA_VISIBLE_DEVICES value: {configured_value!r}"
            ) from exc
        if count <= 0:
            raise GPUSelectionError("Auto-selected GPU count must be positive.")
        return auto_select_gpu_ids(count)

    return normalized


def auto_select_gpu_ids(count: int) -> str:
    """Select the least-loaded GPUs and return a CUDA_VISIBLE_DEVICES string."""
    statuses = query_gpu_statuses()
    if len(statuses) < count:
        raise GPUSelectionError(
            f"Requested {count} GPUs but only {len(statuses)} visible GPUs were found."
        )

    selected = sorted(
        statuses,
        key=lambda item: (
            -item.memory_free_mb,
            item.utilization_gpu_percent,
            item.memory_used_mb,
            item.index,
        ),
    )[:count]
    return ",".join(str(item.index) for item in sorted(selected, key=lambda item: item.index))


def query_gpu_statuses() -> list[GPUStatus]:
    """Return current GPU memory and utilization snapshots from `nvidia-smi`."""
    try:
        command_result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise GPUSelectionError("`nvidia-smi` is not available in PATH.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise GPUSelectionError(f"`nvidia-smi` failed: {stderr}") from exc

    return parse_nvidia_smi_csv(command_result.stdout)


def parse_nvidia_smi_csv(raw_output: str) -> list[GPUStatus]:
    """Parse `nvidia-smi` CSV output into structured GPU snapshots."""
    statuses: list[GPUStatus] = []
    for raw_line in raw_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 4:
            raise GPUSelectionError(f"Unexpected `nvidia-smi` output line: {raw_line!r}")
        try:
            statuses.append(
                GPUStatus(
                    index=int(parts[0]),
                    memory_used_mb=int(parts[1]),
                    memory_total_mb=int(parts[2]),
                    utilization_gpu_percent=int(parts[3]),
                )
            )
        except ValueError as exc:
            raise GPUSelectionError(f"Failed to parse `nvidia-smi` line: {raw_line!r}") from exc
    return statuses
