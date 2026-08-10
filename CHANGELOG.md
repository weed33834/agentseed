# Changelog

## [1.1.0] — 2026-08-10

架构清理与平台检测优化。

### Fixed
- **dar 能力包路径错误**：`build_ruleset(mode="full")` 查找 `capabilities/dar/prompt.md`，但 dar 实际在 `capabilities/research/dar/`（无 prompt.md）。新增 `_resolve_capability_path()` 路径解析器，full 模式正确加载 dar README.md 作为能力包文档。
- **平台检测逻辑重复且不一致**：`forge.py PLATFORM_DETECTION` 只覆盖 9 个平台，`sync_rules.detect_tool_from_cwd()` 覆盖 11 个，检测路径也不同。新增统一 `PLATFORM_DETECT_MARKERS` 注册表作为单一真相源，forge.py 从中派生。
- **sync --tool all 重复写入 AGENTS.md**：agents-md 和 qwenwork 都写 AGENTS.md，第二次覆盖第一次。sync/apply/main 三个入口均添加 `seen_outputs` 去重，跳过重复写入并打印提示。
- **forge.py docstring 写"13 个平台"**：实际 15 个，已修正。
- **detect_tool_from_cwd docstring 写"再看 IDE 进程"**：实际无进程检测代码，修正为准确描述。

### Changed
- 版本号 1.0.0 → 1.1.0（pyproject.toml / __init__.py / CITATION.cff）。

## [1.0.0] — 2026-08-08

AgentSeed 首个正式版本。此前内部迭代（2.x / 1.x 实验版本）已整合归档，全部能力收口到 1.0.0。

### 产品定位（v1.0.0 起）

面向自主智能体的高约束规则治理框架：**治理内核（不可协商）+ 场景规则包（可插拔）+ 三注册表（场景/能力/平台）**。一次装配，15 个智能体工具同步生效。

### Added
- 千问办公 (QwenWork) 注册为第 15 个内置平台：`qwenwork`（entry=AGENTS.md，与 agents-md 同源）。
- CLI `--json` 结构化输出：`list` / `forge` / `sync` / `status` / `platform list` / `persona list` 支持 `--json`，UTF-8 纯净流，供脚本与 Agent 直接消费。
- MCP Server HTTP 传输（`agentseed serve --port N`）：stdlib 实现 `POST /mcp`（JSON-RPC）+ `GET /healthz`。
- MCP 场景规则包别名工具：`scenario_list` / `scenario_activate`（`persona_*` 保留兼容）。
- 场景规则包清单规范 `docs/SCENARIO_PACK_SPEC.md` + 校验器 `scripts/validate_packs.py`（manifest 结构/引用完整性/能力有效性/互斥对称性，防 forge 产物 [missing]）。
- 对外术语统一为"场景规则包 (Scenario Pack)"：README/PROJECT/架构文档重写定位；CLI 文案、MCP 工具描述同步；命令名与 JSON 字段保持兼容。
- 场景包目录双路径兼容：资源根探测与包目录解析支持 `scenarios/`（优先）与 `personas/`（回退）。
- `docs/PUBLISH.md`：PyPI（计划）/ MCP 注册表与市场 / Homebrew / Docker 的分发提交指南。

### Fixed
- **MCP Server 资源根解析**：wheel 安装下资源根指向错误层级，导致 `persona_list` 返回空、`governance_check` 报 "No P0 constraints loaded"。按 `AGENTSEED_REPO → <pkg>/_resources → dev 仓库根` 三级回退，wheel 安装开箱即用。
- **governance_check 工具名无关匹配**：破坏性操作/密钥/MCP 自装检查不再要求特定工具名，从任意工具参数中递归提取命令字符串匹配。
- **Windows 中文环境编码**：stdio/HTTP 启动强制 stdout/stderr 为 UTF-8，CLI `--json` 输出同样强制 UTF-8。
- **场景协议源文件缺失（基线缺陷）**：6 个 `personas/<id>/AGENTS.md` 此前被 `.gitignore` 无锚定规则静默忽略、从未入库，导致 forge 产物出现 `[missing]` 标记。已补全 6 份源文件并把 `.gitignore` 锚定为 `/AGENTS.md`（根级生成文件）。
- coding 包 manifest 补 `agent_mode` 声明。
- 场景包组合精简：移除 `interactive-novel` 与孤儿能力包（`state-machine` / `npc-simulation` / `adaptive-difficulty` / `game-engine` / `novel-chapter-deliverable-mode`），首发场景规则包 6 → 5（coding / conversation / novel / paper / agent-builder）。
- **conversation 并入内核**：通用规则（来源可信度分级/深度检索/方案对比/Tool-Skill-MCP 三层策略）沉淀进 core（governance/interaction/tool-policy），新增内核通用模式 `default`（无场景包依赖），router fallback 改指 default，删除 personas/conversation 与 dar-conversation.yaml，市场首发 4 包 + 内核 default。
- **场景包市场机制（仓库即市场）**：`agentseed pack` 子系统（list/add/remove/new/publish）——最小基础内核（core+平台适配+coding）+ 按需单包安装（sparse 拉取 + Quality Gate 前置）+ 自建包向导与发布回路；`docs/PACK_MARKET.md`；validate_packs 市场感知（互斥引用未安装包只警告）。

### Infrastructure
- GitHub Releases 清理历史 2.x 版本，v1.0.0 作为唯一正式发布（wheel 随 Release 分发）。
- 许可证：Apache-2.0（替代 MIT，增加专利授权保护与版权声明义务）。
- 全量测试：162 passed / 1 skipped（此前 151 passed + 5 基线失败）。

## 历史版本

- 2.4.1 / 2.3.0 / 2.0.0 / 1.4.0 ~ 1.0.0（2026-07 内部迭代）：已整合至 1.0.0，不再单独维护。
