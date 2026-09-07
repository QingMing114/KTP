from __future__ import annotations

from dataclasses import dataclass

from schemas.runtime import PermissionPolicy


@dataclass(slots=True)
class PolicyRegistryV2:
    policies: list[PermissionPolicy]

    def list_policies(self) -> list[PermissionPolicy]:
        return self.policies

    def get_default_policy(self) -> PermissionPolicy:
        return self.policies[0]


def build_default_policy_registry() -> PolicyRegistryV2:
    return PolicyRegistryV2(
        policies=[
            PermissionPolicy(
                name="bounded_runtime_default",
                description="Default V2 bounded runtime policy.",
                max_replans=1,
                max_delegations=1,
            )
        ]
    )
