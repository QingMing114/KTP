from __future__ import annotations

from dataclasses import dataclass

from v2.shared.schemas import AgentProfile

_PLANNER_PROMPT = """
你是规划代理 planner_70b：理解用户意图、选择工具或把物理计算委派给专业子代理。
不要直接执行需要下载影像或长时间计算的动作。
"""

_REMOTE_SENSING_PROMPT = """
你是遥感分析子代理 remote_sensing_analyst：只负责遥感数据与作物/LAI 计算。
优先复用宿主已准备好的共享影像；完成后用 reply 返回结果摘要与产物引用。
"""

_REPORTER_PROMPT = """
你是报告子代理 reporter：只负责把已有结果渲染成用户可读报告，不重新计算。
"""

_REVIEWER_PROMPT = """
你是复核代理 reviewer：检查结果与产物是否完整，指出缺口，不做新的计算。
"""


@dataclass(slots=True)
class AgentProfileRegistry:
    profiles: list[AgentProfile]

    def list_profiles(self) -> list[AgentProfile]:
        return self.profiles

    def get(self, name: str) -> AgentProfile | None:
        return next((p for p in self.profiles if p.name == name or p.role == name), None)


def build_default_agent_registry() -> AgentProfileRegistry:
    """Built-in agent roles for the multi-agent runtime (M1).

    ``tool_prefixes`` restrict what each child can call; an empty list means the
    role has no tools (reviewer/planner). Children cannot delegate further in M1,
    so ``allow_delegation`` stays false.
    """
    return AgentProfileRegistry(
        profiles=[
            AgentProfile(
                name="planner_70b",
                role="planner",
                description="Produces structured plans and bounded delegation hints.",
                system_prompt=_PLANNER_PROMPT,
                tool_prefixes=[],
                max_steps=10,
                allow_delegation=True,
                max_children=3,
            ),
            AgentProfile(
                name="executor_30b",
                role="executor",
                description="Executes bounded tool actions and validates outputs.",
                system_prompt=None,  # keeps the legacy SubExecutor prompt
                tool_prefixes=["prosail.", "apsim.", "workspace."],
                max_steps=10,
            ),
            AgentProfile(
                name="remote_sensing_analyst",
                role="executor",
                description="Runs remote-sensing analysis tools (imagery, crop, LAI).",
                system_prompt=_REMOTE_SENSING_PROMPT,
                tool_prefixes=["remote_sensing.", "prosail."],
                max_steps=8,
            ),
            AgentProfile(
                name="reporter",
                role="executor",
                description="Renders reports from already-computed results.",
                system_prompt=_REPORTER_PROMPT,
                tool_prefixes=["remote_sensing.workflow_report", "ktp.build_report"],
                max_steps=4,
            ),
            AgentProfile(
                name="reviewer",
                role="reviewer",
                description="Reviews run outputs and suggests bounded replan hints.",
                system_prompt=_REVIEWER_PROMPT,
                tool_prefixes=[],
                max_steps=3,
            ),
        ]
    )
