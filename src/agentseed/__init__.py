"""agentseed: AgentSeed 分发层 + CLI 入口。"""
from .core import (
    REPO_ROOT, build_ruleset, write_tool_file, list_profiles,
    TOOL_OUTPUT, TOOL_CHAR_LIMIT, SKELETON_BUDGET_BYTES,
    PLATFORM_DETECT_MARKERS,
)

__version__ = "1.1.0"
__all__ = [
    "REPO_ROOT", "build_ruleset", "write_tool_file", "list_profiles",
    "TOOL_OUTPUT", "TOOL_CHAR_LIMIT", "SKELETON_BUDGET_BYTES",
    "PLATFORM_DETECT_MARKERS",
]
