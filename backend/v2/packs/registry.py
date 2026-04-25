from __future__ import annotations

from dataclasses import dataclass

from v2.packs.demo_pack import build_demo_pack, build_ktp_placeholder_pack
from v2.shared.schemas import DomainPackSummary


@dataclass(slots=True)
class DomainPackRegistry:
    packs: list[DomainPackSummary]

    def list_packs(self) -> list[DomainPackSummary]:
        return self.packs


def build_default_pack_registry() -> DomainPackRegistry:
    return DomainPackRegistry(
        packs=[
            build_demo_pack(),
            build_ktp_placeholder_pack(),
        ]
    )
