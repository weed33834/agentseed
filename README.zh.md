# AgentSeed

> **`pip install https://github.com/weed33834/agentseed/releases/download/v1.0.0/agentseed-1.0.0-py3-none-any.whl && agentseed forge`**

**🌐 [English](README.md) · [中文](README.zh.md) · [日本語](README.ja.md)**

**📦 [GitHub](https://github.com/weed33834/agentseed) (主站) · [Gitee](https://gitee.com/badhope/agentseed) · [Gitcode](https://gitcode.com/badhope/agentseed)**

![License](https://img.shields.io/badge/license-Apache_2.0-blue)
![CI](https://github.com/weed33834/agentseed/actions/workflows/ci.yml/badge.svg)
![Personas](https://img.shields.io/badge/personas-5-green)
![Platforms](https://img.shields.io/badge/platforms-15-orange)
![Tests](https://img.shields.io/badge/tests-171%20passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-informational)

---

每次开一个新的 AI 编程会话，前十分钟都在干同一件事：告诉它别幻觉、别跑 `rm -rf`、你的技术栈是什么。AgentSeed 把这件事做成一整层**不可协商的约束**，再按任务场景插上对应的**场景规则包**，一次装配，同步到你用的所有 AI 工具。

一条命令检测你的项目场景，插上对应的场景规则包，为 Claude Code、Cursor、Copilot、Windsurf、Trae 等 15 个智能体工具统一生成高约束规则文件。

```bash
agentseed forge
```

就这一条。空目录进去，出来一个 1200 行的 AGENTS.md，包含安全规则、项目专属技能、各平台配置。不管你是在写代码、写小说、写论文、还是写另一个 agent，都一样用。

---

## 它能干什么

**安全底线不会丢。** 核心安全规则（禁止 `rm -rf`、禁止捏造密钥、禁止不经确认装东西）是治理内核的一部分，写死在 AgentSeed 里，换什么场景规则包都覆盖不掉。

**内核通用模式 + 四个首发场景规则包。** `default`（内核通用，已内置）、`coding`（默认开发）、`novel`、`paper`、`agent-builder` 面向不同任务场景——每个规则包 = 场景协议 + 提示词 + 技能 + 能力白名单，由项目锚点与用户意图自动选择，也可 `agentseed switch --profile novel` 手动切换。规则包可插拔、可扩展：新增场景只需一个目录 + 一份清单，机制开放，后续场景持续加入，全程不需要改内核。

**15 个平台，一次同步。** 不同工具要不同格式，AgentSeed 自己搞定：
- Claude Code → `CLAUDE.md`
- Cursor → `.cursor/rules/project.mdc`
- Copilot → `.github/copilot-instructions.md`
- Windsurf → `.windsurfrules`
- Gemini → `GEMINI.md`
- Trae → `.trae/rules/project_rules.md`
- Cline → `.clinerules/project.md`
- Continue → `.continue/rules/project.md`
- Amazon Q → `.amazonq/rules/project.md`
- Qodo → `best_practices.md`
- 通义灵码 → `.lingma/rules/project.md`
- 腾讯云代码助手 → `.comate/rules/project.mdr`
- Codex → `.codex/rules.md`
- 千问办公 → `AGENTS.md`（原生读取）
- AGENTS.md（20+ 工具原生读取）

**每个平台都有拦截钩子。** `adapters/hooks/` 下 14 个平台的 `pre_tool_use.py`，在危险操作执行前拦截。fail-open 设计：钩子崩了操作照常，不会误伤。

**MCP Server。** `agentseed serve` 启动，任何支持 MCP 的客户端可以直接调用 `governance_check`（安全红线检查）、`persona_list`（场景规则包列表）、`persona_activate`（激活场景规则包）、`gap_detect`（能力缺口检测）。stdio 模式用于 MCP 客户端；`--port N` 启动 HTTP 模式（`POST /mcp` + `GET /healthz`），供远程/Agent 间调用。

**自进化。** AgentSeed 会给你的项目打分——缺什么工具、哪些领域不懂——然后告诉你该装什么。不是魔法，就是一个加权公式，你装的能力越多它建议越准。

---

## 安装

```bash
pip install https://github.com/weed33834/agentseed/releases/download/v1.0.0/agentseed-1.0.0-py3-none-any.whl
```

源码安装：

```bash
git clone https://github.com/weed33834/agentseed.git
cd agentseed
pip install -e .
```

国内网络慢的话用 Gitee 镜像：

```bash
git clone https://gitee.com/badhope/agentseed.git
```

---

## 快速开始（最小基础 + 按需加包）

仓库即市场：克隆**最小基础内核**（core + 平台适配 + coding），其余场景包按需安装，不要求全量克隆。

```bash
# 最小基础克隆（sparse，只拉基础目录）
git clone --depth 1 --filter=blob:none --sparse https://github.com/weed33834/agentseed.git
cd agentseed
git sparse-checkout set core adapters src scripts docs .github personas/coding \
  capabilities/engineering capabilities/testing capabilities/review \
  capabilities/agent-governance capabilities/research pyproject.toml setup.py LICENSE
agentseed forge --profile coding          # 立即可用

# 按需增强：只拉取单个场景包
agentseed pack list                       # 市场包清单（含已安装状态）
agentseed pack add novel                  # 装 novel（只拉这一个包，Quality Gate 前置）
agentseed pack new my-scenario --name "我的场景" --scenario "数据分析"
agentseed pack publish my-scenario        # 校验 + 生成回传市场的 PR 材料
```

## 常用命令

```bash
agentseed forge              # 检测项目 → 装配 → 生成
agentseed forge --dry-run    # 预览，不写文件
agentseed forge --profile coding
agentseed forge --profile novel

agentseed switch --profile paper

agentseed sync               # 同步到所有平台
agentseed sync --platform cursor

agentseed status             # 看看装了啥、缺啥

agentseed serve              # 启动 MCP server (stdio)
agentseed serve --port 8080  # 启动 MCP server (HTTP: POST /mcp + GET /healthz)

agentseed platform list      # 15 个内置平台
agentseed platform list --json     # JSON 输出（供脚本/Agent 消费）
agentseed forge --dry-run --json   # 装配预览（JSON 输出）
agentseed platform import my-ide --entry .myide/rules.md --format markdown

agentseed pack list          # 市场场景包清单
agentseed pack add novel     # 按需安装单个场景包
agentseed pack new my-scenario  # 创建自定义场景包（模板 + 校验）

agentseed persona list       # 列出场景规则包（命令名兼容保留）
agentseed persona search "产品经理"
```

市场模型详见 [docs/PACK_MARKET.md](docs/PACK_MARKET.md)。

---

## 接入你自己的平台

```bash
agentseed platform import my-editor --entry .myeditor/rules.md --format markdown --hook-dir .myeditor
```

一步注册平台 + 生成拦截钩子 + 纳入每次 `agentseed sync`。

---

## 目录结构

```
core/                  治理内核（P0 红线、决策公式、路由规则，不可变）
personas/              场景规则包（coding、novel、paper...，可插拔）
capabilities/          能力插件（testing、research、creative...，按需加载）
adapters/hooks/        平台适配层：各平台的工具拦截钩子
src/agentseed/         CLI、同步引擎、路由、装配、自进化
```

---

## 跟同类项目比

- **agent-rules (steipete)** — 已归档，只做 Cursor 编码规则。
- **agents.md** — 文件格式提案，只有格式没内容没工具链。
- **ACP** — agent 配置管理器，没治理没自进化。
- **Cursor Directory** — 社区规则片段合集，不支持多平台同步。
- **AgentSeed** — 治理内核 + 可插拔场景规则包 + 15 平台同步 + 拦截钩子 + 自进化，一个 CLI 全包。

---

## 参与开发

看 [CONTRIBUTING.md](CONTRIBUTING.md)。简单说：改源文件（`core/`、`personas/`、`capabilities/`）→ 跑 `agentseed sync` 重生成平台文件 → 别手动改生成产物。

跑测试：`python -m pytest tests/`（171 通过）。

---

MIT
