import pytest

from v2.tools.registry import ToolRegistryV2, ToolDefinition
from v2.tools.plugin_adapter import PluginToolSpec, ToolEndpoint, invoke_plugin_tool
from v2.shared.schemas import ToolSpecV2


def _make_registry(*tool_names: str) -> ToolRegistryV2:
    definitions = {}
    for name in tool_names:
        spec = ToolSpecV2(
            name=name,
            display_name=name,
            description=f"Tool {name}",
            visibility="public",
            category="plugin",
        )
        def handler(**kwargs):
            from v2.shared.schemas import ObservationV2
            return ObservationV2(source=name, status="success", summary=name), []
        definitions[name] = ToolDefinition(spec=spec, handler=handler)
    return ToolRegistryV2(definitions=definitions)


class TestPluginToolRegistration:
    def test_register_and_list(self):
        registry = _make_registry()
        spec = PluginToolSpec(
            name="test.my_plugin",
            display_name="My Plugin",
            description="A test plugin",
            endpoint=ToolEndpoint(adapter="python_callable", module="v2.tools.handlers", function="handle_general_query"),
        )
        from v2.tools.plugin_adapter import make_plugin_handler
        handler = make_plugin_handler(spec)
        tool_spec = ToolSpecV2(
            name=spec.name,
            display_name=spec.display_name,
            description=spec.description,
            visibility="public",
            category="plugin",
            pack_name="plugin",
            input_schema=spec.input_schema,
            safety_level=spec.safety_level,
            capabilities=["plugin"],
        )
        registry.register(spec.name, tool_spec, handler)
        assert registry.has_tool("test.my_plugin")

    def test_unregister_plugin(self):
        registry = _make_registry()
        spec = PluginToolSpec(
            name="test.to_remove",
            display_name="To Remove",
            description="Will be removed",
            endpoint=ToolEndpoint(adapter="python_callable", module="v2.tools.handlers", function="handle_general_query"),
        )
        from v2.tools.plugin_adapter import make_plugin_handler
        handler = make_plugin_handler(spec)
        tool_spec = ToolSpecV2(
            name=spec.name,
            display_name=spec.display_name,
            description=spec.description,
            visibility="public",
            category="plugin",
        )
        registry.register(spec.name, tool_spec, handler)
        assert registry.has_tool("test.to_remove")
        registry.unregister("test.to_remove")
        assert not registry.has_tool("test.to_remove")


class TestPluginToolTest:
    def test_invoke_python_callable(self):
        spec = PluginToolSpec(
            name="test.python_tool",
            display_name="Python Tool",
            description="Test python callable",
            endpoint=ToolEndpoint(
                adapter="python_callable",
                module="v2.tools.handlers",
                function="handle_general_query",
            ),
        )
        obs, artifacts = invoke_plugin_tool(spec, {"query": "test input"})
        assert obs.status in ("success", "error")

    def test_invoke_unknown_adapter(self):
        spec = PluginToolSpec(
            name="test.bad_adapter",
            display_name="Bad Adapter",
            description="Test bad adapter",
            endpoint=ToolEndpoint(adapter="nonexistent_adapter"),
        )
        obs, artifacts = invoke_plugin_tool(spec, {})
        assert obs.status == "error"
        assert "Unknown adapter" in obs.summary


class TestDuplicateRegistration:
    def test_duplicate_register_overwrites(self):
        registry = _make_registry()
        spec = ToolSpecV2(name="dup.tool", display_name="Dup", description="Dup", visibility="public", category="test")
        registry.register("dup.tool", spec, lambda **kw: (None, []))
        spec2 = ToolSpecV2(name="dup.tool", display_name="Dup V2", description="Dup V2", visibility="public", category="test")
        registry.register("dup.tool", spec2, lambda **kw: (None, []))
        tool = registry.get_definition("dup.tool")
        assert tool.spec.display_name == "Dup V2"
