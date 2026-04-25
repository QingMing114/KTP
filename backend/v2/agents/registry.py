from __future__ import annotations

from dataclasses import dataclass

from v2.shared.schemas import AgentProfile


@dataclass(slots=True)
class AgentProfileRegistry:
    profiles: list[AgentProfile]

    def list_profiles(self) -> list[AgentProfile]:
        return self.profiles


def build_default_agent_registry() -> AgentProfileRegistry:
    return AgentProfileRegistry(
        profiles=[
            AgentProfile(
                name="planner_70b",
                role="planner",
                description="Produces structured plans and bounded delegation hints.",
            ),
            AgentProfile(
                name="executor_30b",
                role="executor",
                description="Executes bounded tool actions and validates outputs.",
            ),
            AgentProfile(
                name="reviewer",
                role="reviewer",
                description="Reviews run outputs and suggests bounded replan hints.",
            ),
        ]
    )
