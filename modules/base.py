"""Noir module contract (05_modules.md §1, build plan §6.3).

Module = Python MCP server. Trusted base tool-modules (C5/C2/C6) run `in-process`
(allowed by §1.6); Factory-generated/untrusted modules run as subprocess sandbox.

Each module ships a module.yaml manifest, declares its provided tools with the
Governor action_class each tool initiates, and a private memory namespace
(m_<id>__ tables + private Chroma collection). The core invokes tools only through
the registry + Governor (every call audited to agent_log).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolSpec:
    name: str
    action_class: str            # read|local_write|external_send|money|system|self_modify
    description: str = ""


@dataclass
class Manifest:
    module_id: str
    cluster: str                 # C1..C6
    display_name: str
    version: str
    runtime: str                 # in-process | subprocess
    namespace: str               # m_<id>__ private SQLite/Chroma namespace
    tools: list[ToolSpec] = field(default_factory=list)
    capabilities: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def tool(self, name: str) -> ToolSpec | None:
        return next((t for t in self.tools if t.name == name), None)


@dataclass
class CallResult:
    ok: bool
    output: Any = None
    error: str | None = None
    metrics: dict[str, int] = field(default_factory=dict)


class NoirModule(Protocol):
    manifest: Manifest

    async def init(self) -> None: ...
    async def call(self, tool: str, args: dict) -> CallResult: ...
    async def health(self) -> dict: ...


def load_manifest(yaml_path) -> Manifest:
    """Parse a module.yaml into a Manifest."""
    import yaml
    d = yaml.safe_load(open(yaml_path))
    tools = [ToolSpec(name=t["name"], action_class=t["action_class"],
                      description=t.get("description", "")) for t in d.get("tools", [])]
    return Manifest(
        module_id=d["module_id"], cluster=d["cluster"], display_name=d["display_name"],
        version=str(d["version"]), runtime=d.get("runtime", "in-process"),
        namespace=d.get("namespace", f"m_{d['module_id'].replace('-', '_')}__"),
        tools=tools, capabilities=d.get("capabilities", {}),
        description=d.get("description", ""),
    )
