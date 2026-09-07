from pathlib import Path

from v2.runtime.memory_manager import MemoryManager


def test_write_fact_updates_managed_index_and_is_immediately_searchable(tmp_path: Path) -> None:
    manual_index = "# Human index\n\nKeep this paragraph exactly.\n"
    (tmp_path / "MEMORY.md").write_text(manual_index, encoding="utf-8")
    manager = MemoryManager(memory_dir=tmp_path)

    written = manager.write_fact(
        name="irrigation-window",
        description="Irrigation scheduling preference",
        body="Apply irrigation before the maize stress window.",
        metadata={"type": "preference"},
    )

    assert written is not None
    assert manager.get("irrigation-window") is not None
    assert manager.find_relevant("maize irrigation")[0].name == "irrigation-window"
    index_text = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert manual_index.strip() in index_text
    assert "<!-- KTP-MEMORY-MANAGED:START -->" in index_text
    assert "(irrigation-window.md)" in index_text


def test_written_fact_survives_new_manager_instance(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("# Index\n", encoding="utf-8")
    manager = MemoryManager(memory_dir=tmp_path)
    manager.write_fact(
        name="soil-moisture",
        description="Soil moisture threshold",
        body="The warning threshold is 18 percent.",
    )

    restarted = MemoryManager(memory_dir=tmp_path)

    assert restarted.get("soil-moisture") is not None
    assert restarted.find_relevant("moisture threshold")[0].body.startswith("The warning threshold")


def test_unsafe_name_cannot_escape_or_overwrite_manual_document(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("# Index\n", encoding="utf-8")
    manual = tmp_path / "existing.md"
    manual.write_text("human-authored", encoding="utf-8")
    manager = MemoryManager(memory_dir=tmp_path)

    first = Path(manager.write_fact(
        name="../existing",
        description="Safe generated fact",
        body="generated one",
    ) or "")
    second = Path(manager.write_fact(
        name="../existing",
        description="Second safe generated fact",
        body="generated two",
    ) or "")

    assert first.parent.resolve() == tmp_path.resolve()
    assert second.parent.resolve() == tmp_path.resolve()
    assert first.name == "existing-2.md"
    assert second.name == "existing-3.md"
    assert manual.read_text(encoding="utf-8") == "human-authored"
    assert first.read_text(encoding="utf-8") != second.read_text(encoding="utf-8")


def test_index_path_traversal_link_is_ignored(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-memory.md"
    outside.write_text("---\nname: outside\ndescription: outside\n---\nsecret\n", encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text(
        "# Index\n\n- [unsafe](../outside-memory.md)\n",
        encoding="utf-8",
    )

    manager = MemoryManager(memory_dir=tmp_path)

    assert manager.get("outside") is None
    assert manager.entries == {}


def test_context_injection_labels_the_markdown_source(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text(
        "# Index\n\n- [Protocol](protocol.md)\n",
        encoding="utf-8",
    )
    (tmp_path / "protocol.md").write_text(
        "# Dataset protocol\n\nCreate datasets with `POST /datasets`.\n",
        encoding="utf-8",
    )
    manager = MemoryManager(memory_dir=tmp_path)

    injection = manager.build_context_injection("How do I create a dataset?")

    assert "Retrieved Markdown Knowledge" in injection
    assert "Source: protocol.md" in injection
    assert "POST /datasets" in injection


def test_context_injection_selects_a_matching_later_markdown_section(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text(
        "# Index\n\n- [Protocol](protocol.md)\n",
        encoding="utf-8",
    )
    (tmp_path / "protocol.md").write_text(
        "# Protocol\n\nGeneral introduction.\n\n"
        "## Datasets\n\nCreate a dataset with `POST /datasets`.\n\n"
        "## Idempotency\n\n`POST /datasets` accepts `Idempotency-Key`.\n",
        encoding="utf-8",
    )
    manager = MemoryManager(memory_dir=tmp_path)

    injection = manager.build_context_injection("Which requests accept Idempotency-Key?")

    assert "## Idempotency" in injection
    assert "Idempotency-Key" in injection


def test_context_injection_prefers_the_specific_chinese_question_target(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text(
        "# Index\n\n- [Manual](manual.md)\n",
        encoding="utf-8",
    )
    (tmp_path / "manual.md").write_text(
        "# Manual\n\n"
        "## 桥梁养护基本术语\n\n桥梁养护需要按规范开展检查。\n\n"
        "## 编制依据\n\n手册依据 JTG 5120-2021 编制。\n",
        encoding="utf-8",
    )
    manager = MemoryManager(memory_dir=tmp_path)

    injection = manager.build_context_injection("桥梁养护手册的编制依据有哪些？")

    assert "## 编制依据" in injection
    assert "JTG 5120-2021" in injection
