"""Memory directory manager for the V2 bounded runtime.

Phase B.2: Integrates the Claude Code three-layer memory system
(index → facts → session) into the KTP engine.

Reads ``MEMORY.md`` as the index file and individual ``memory/*.md``
fact files. Provides relevance matching and system-prompt injection.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── frontmatter parsing ──

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body) from a markdown file with YAML frontmatter.

    Uses a minimal line-by-line parser to avoid a PyYAML dependency.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text

    fm: dict[str, Any] = {}
    current_key: str | None = None
    current_indent: int = 0

    for line in m.group(1).split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # top-level key: value
        if not line.startswith(" ") and not line.startswith("\t"):
            if ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                fm[key] = val
                current_key = key
                current_indent = 0
            continue

        # nested key: value (simple one-level nesting)
        indent = len(line) - len(line.lstrip())
        if ":" in stripped and current_key is not None and indent > current_indent:
            sub_key, _, sub_val = stripped.partition(":")
            sub_key = sub_key.strip()
            sub_val = sub_val.strip().strip('"').strip("'")
            if current_key not in fm or not isinstance(fm[current_key], dict):
                fm[current_key] = {}
            fm[current_key][sub_key] = sub_val  # type: ignore[index]

    body = text[m.end():]
    return fm, body


# ── memory entry ──


@dataclass
class MemoryEntry:
    """A single memory fact loaded from a ``memory/*.md`` file."""

    name: str
    description: str
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)
    file_path: str = ""

    @property
    def type(self) -> str:
        meta = self.metadata
        if isinstance(meta, dict):
            return str(meta.get("type", "unknown"))
        return "unknown"

    @property
    def slug(self) -> str:
        return self.name


# ── memory manager ──


class MemoryManager:
    """Loads and queries the KTP memory directory.

    Usage::

        mgr = MemoryManager(memory_dir="/path/to/memory")
        injection = mgr.build_context_injection(query="analyze crop health")
        # → formatted string of relevant memories for the system prompt
    """

    def __init__(self, *, memory_dir: str | Path | None = None) -> None:
        self._memory_dir: Path | None = Path(memory_dir) if memory_dir else None
        self._entries: dict[str, MemoryEntry] = {}
        self._index_links: list[str] = []
        self._loaded = False

        if self._memory_dir is not None and self._memory_dir.is_dir():
            self._load()

    # ── loading ──

    def _load(self) -> None:
        """Load MEMORY.md index and all referenced fact files."""
        assert self._memory_dir is not None
        index_path = self._memory_dir / "MEMORY.md"
        if not index_path.is_file():
            logger.warning("memory_index_missing | path=%s", index_path)
            return

        index_text = index_path.read_text(encoding="utf-8")
        self._index_links = self._parse_index_links(index_text)
        logger.info(
            "memory_index_loaded | path=%s | links=%d",
            index_path, len(self._index_links),
        )

        for link in self._index_links:
            fact_path = self._memory_dir / link
            if not fact_path.is_file():
                logger.debug("memory_fact_missing | path=%s", fact_path)
                continue
            try:
                entry = self._load_fact(fact_path)
                if entry is not None:
                    self._entries[entry.name] = entry
            except Exception:
                logger.exception("memory_fact_load_error | path=%s", fact_path)

        self._loaded = True
        logger.info(
            "memory_manager_initialized | dir=%s | entries=%d",
            self._memory_dir, len(self._entries),
        )

    @staticmethod
    def _parse_index_links(index_text: str) -> list[str]:
        """Extract markdown link references from MEMORY.md content.

        Looks for patterns like ``[Title](filename.md)``.
        """
        links: list[str] = []
        for match in re.finditer(r"\[([^\]]+)\]\(([^)]+\.md)\)", index_text):
            links.append(match.group(2))
        return links

    def _load_fact(self, path: Path) -> MemoryEntry | None:
        """Parse a single memory fact file into a :class:`MemoryEntry`."""
        text = path.read_text(encoding="utf-8")
        fm, body = _parse_frontmatter(text)
        name = str(fm.get("name", path.stem))
        description = str(fm.get("description", ""))
        metadata = fm.get("metadata", {})
        if isinstance(metadata, str):
            metadata = {}
        return MemoryEntry(
            name=name,
            description=description,
            body=body.strip(),
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
            file_path=str(path),
        )

    def reload(self) -> None:
        """Re-read the memory directory from disk."""
        self._entries.clear()
        self._index_links.clear()
        self._loaded = False
        if self._memory_dir is not None and self._memory_dir.is_dir():
            self._load()

    # ── querying ──

    @property
    def entries(self) -> dict[str, MemoryEntry]:
        return dict(self._entries)

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def get(self, name: str) -> MemoryEntry | None:
        return self._entries.get(name)

    def find_relevant(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> list[MemoryEntry]:
        """Return memories ranked by relevance to *query*.

        Uses a simple TF-like keyword overlap score.  For small memory
        directories (<50 entries) this is fast enough; larger directories
        should switch to embedding-based retrieval.
        """
        if not self._entries:
            return []

        query_terms = _tokenize(query)
        if not query_terms:
            return list(self._entries.values())[:top_k]

        scored: list[tuple[float, MemoryEntry]] = []
        for entry in self._entries.values():
            score = _relevance_score(query_terms, entry)
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    def build_context_injection(
        self,
        query: str,
        *,
        top_k: int = 5,
        max_chars: int = 2000,
    ) -> str:
        """Return a formatted string of relevant memories for the system prompt.

        Returns an empty string when no memory directory is configured or
        no relevant memories are found.
        """
        if not self._entries:
            return ""

        relevant = self.find_relevant(query, top_k=top_k)
        if not relevant:
            return ""

        parts: list[str] = []
        total_chars = 0
        header = "## KTP Project Knowledge\n"
        parts.append(header)
        total_chars += len(header)

        for entry in relevant:
            snippet = (
                f"### {entry.description}\n"
                f"{entry.body[:500]}\n"
            )
            if total_chars + len(snippet) > max_chars:
                snippet = snippet[:max_chars - total_chars - 4] + "...\n"
                parts.append(snippet)
                break
            parts.append(snippet)
            total_chars += len(snippet)

        result = "\n".join(parts)
        logger.debug(
            "memory_context_injection | query_len=%d | entries=%d | chars=%d",
            len(query), len(relevant), len(result),
        )
        return result

    def write_fact(
        self,
        *,
        name: str,
        description: str,
        body: str,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Write a new memory fact file and update the index.

        Returns the file path on success, or ``None`` when no memory
        directory is configured.
        """
        if self._memory_dir is None:
            logger.warning("memory_write_skipped_no_dir")
            return None

        meta = dict(metadata or {})
        meta.setdefault("type", "feedback")

        meta_lines = "\n".join(
            f"  {k}: {v}" for k, v in meta.items()
        )
        content = (
            f"---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            f"metadata:\n"
            f"{meta_lines}\n"
            f"---\n\n"
            f"{body.strip()}\n"
        )

        filename = f"{name}.md"
        file_path = self._memory_dir / filename
        file_path.write_text(content, encoding="utf-8")
        logger.info("memory_fact_written | path=%s | name=%s", file_path, name)

        # Reload to pick up the new entry
        self.reload()
        return str(file_path)


# ── helpers ──

def _tokenize(text: str) -> set[str]:
    """Tokenize text into a set of lowercased words (ASCII + CJK bigrams)."""
    tokens: set[str] = set()

    # ASCII words
    for token in re.findall(r"[a-zA-Z0-9_]{2,}", text.lower()):
        tokens.add(token)

    # CJK bigrams (simple sliding window over CJK characters)
    cjk_chars = re.findall(r"[一-鿿㐀-䶿]", text)
    for i in range(len(cjk_chars) - 1):
        tokens.add(cjk_chars[i] + cjk_chars[i + 1])

    return tokens


def _relevance_score(query_terms: set[str], entry: MemoryEntry) -> float:
    """Score an entry against query terms by weighted field overlap."""
    desc_tokens = _tokenize(entry.description)
    body_tokens = _tokenize(entry.body)

    score = 0.0
    for term in query_terms:
        if term in entry.name:
            score += 3.0  # name match is strongest
        if term in desc_tokens:
            score += 2.0  # description match
        if term in body_tokens:
            score += 1.0  # body match

    # Normalize by term count so longer queries don't dominate
    return score / max(len(query_terms), 1)
