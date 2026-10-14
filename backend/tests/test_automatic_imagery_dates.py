"""Automatic search dates are independent of manual card filters."""
from datetime import date

import pytest
from schemas.workspace import WorkspaceContext, WorkspaceIntent, WorkspaceImagerySearch
from runtime.workspace_assistant import automatic_imagery_request, plan_workspace
from test_workspace_assistant import AOI, Planner


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("runtime.workspace_assistant.imagery_today", lambda: date(2026, 10, 14))


@pytest.mark.parametrize("card", [
    {"start_date": "2026-10-14", "end_date": "2026-10-14"},
    {"start_date": "2001-01-01", "end_date": "2001-02-01", "max_cloud_cover": 0},
    {"start_date": "2026-10-14", "end_date": "2026-01-01"},
    None,
])
def test_automatic_search_ignores_manual_dates_and_uses_recent_window(card):
    context = WorkspaceContext(workspace_id="ws", revision=1, aoi=AOI, auto_execute=True, imagery_search=card)
    result = automatic_imagery_request(context, WorkspaceIntent(intent="execute", summary="分析目前长势"))
    assert (result.start_date, result.end_date, result.max_cloud_cover) == ("2026-07-16", "2026-10-14", 20)


@pytest.mark.parametrize("requested,expected", [
    ({"start_date": "2026-06-01", "end_date": "2026-06-30"}, ("2026-06-01", "2026-06-30")),
    ({"start_date": "2026-10-14", "end_date": "2026-10-14"}, ("2026-10-14", "2026-10-14")),
    ({"end_date": "2026-01-31"}, ("2025-11-02", "2026-01-31")),
    ({"start_date": "2026-09-01"}, ("2026-09-01", "2026-10-14")),
])
def test_explicit_user_dates_override_default_without_using_card(requested, expected):
    context = WorkspaceContext(workspace_id="ws", revision=1, aoi=AOI, auto_execute=True,
                               imagery_search={"start_date": "2026-10-14", "end_date": "2026-10-14"})
    intent = WorkspaceIntent(intent="execute", summary="用户指定时段", imagery_search=WorkspaceImagerySearch(**requested))
    result = automatic_imagery_request(context, intent)
    assert (result.start_date, result.end_date) == expected


def test_cloud_only_request_does_not_restore_manual_dates():
    context = WorkspaceContext(workspace_id="ws", revision=1, aoi=AOI, auto_execute=True,
                               imagery_search={"start_date": "2020-01-01", "end_date": "2020-01-01"})
    result = automatic_imagery_request(context, WorkspaceIntent(intent="execute", summary="云量低于5", imagery_search=WorkspaceImagerySearch(max_cloud_cover=5)))
    assert (result.start_date, result.end_date, result.max_cloud_cover) == ("2026-07-16", "2026-10-14", 5)


def test_professional_manual_dates_are_preserved_for_user_confirmation():
    context = WorkspaceContext(workspace_id="ws", revision=1, aoi=AOI, professional_mode=True,
                               imagery_search={"start_date": "2026-06-01", "end_date": "2026-06-30"})
    result = automatic_imagery_request(context, WorkspaceIntent(intent="execute", summary="分析"))
    assert (result.start_date, result.end_date) == ("2026-06-01", "2026-06-30")


def test_automatic_model_prompt_does_not_receive_manual_search_dates():
    context = WorkspaceContext(workspace_id="ws", revision=1, aoi=AOI, auto_execute=True,
                               imagery_search={"start_date": "2020-01-01", "end_date": "2020-01-01"})
    planner = Planner("execute")
    plan_workspace(planner, "分析最新长势", context, [])
    assert "imagery_search" not in planner.prompts[0]["workspace"]
    assert planner.prompts[0]["time_context"] == {"current_date": "2026-10-14", "automatic_search_lookback_days": 90}
