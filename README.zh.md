<div align="center">

# 🛡️ AgentSeed

**面向 AI 编程智能体的防幻觉护栏。**

基于 [Agent Plugins 1.0.0](https://agent-plugins.org) 规范的混合插件（Skill + MCP 服务器）：强制规范驱动开发，**在代码被标记为"完成"之前先验证**——让 "Done, all tests pass" 变成可观测的事实，而不是一句空话。

[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-blue)](https://github.com/weed33834/AgentSeed/releases)
[![Agent Plugins](https://img.shields.io/badge/Agent%20Plugins-1.0.0-purple)](https://agent-plugins.org)
[![CI](https://github.com/weed33834/AgentSeed/actions/workflows/ci.yml/badge.svg)](https://github.com/weed33834/AgentSeed/actions)
[![Stars](https://img.shields.io/github/stars/weed33834/AgentSeed)](https://github.com/weed33834/AgentSeed)
[![Platforms](https://img.shields.io/badge/platform-Cursor%20%7C%20VS%20Code%20%7C%20Claude%20Code%20%7C%20Copilot-blue)](https://agent-plugins.org)

**中文** · [English](./README.md) · [日本語](./README.ja.md)

⭐ **觉得有用？点个 star 支持一下——帮助更多开发者在上线幻觉代码之前装上护栏。**

</div>

---

## 为什么需要 AgentSeed

大模型会幻觉——落到代码里就是**编造 API、未定义的标识符、假测试通过、自信的夸大声称**。数据说话：

- **15.1%** 的代码幻觉是知识冲突型：调用不存在的 API 或从未导入的 API（[arXiv:2404.00971](https://arxiv.org/abs/2404.00971)）。
- **<10%** 的幻觉代码会在测试中失败——大部分能溜过 CI（同上）。
- **60%+** 的模型输出错误**无法验证**——分不清事实与虚构（FAVA，见 [SoK](https://arxiv.org/abs/2502.18468)）。

纯 prompt 的护栏是"软"的：模型可以口头答应"完成前验证"，然后偷偷跳过。**AgentSeed 把指令和硬的 MCP 闸门绑死**——证据来自真实运行的代码，而不是模型的自我陈述。

它还填补了 1.0.0 规范故意留下的两个缺口：

| 规范缺口 | AgentSeed 的做法 |
| --- | --- |
| 无强制执行机制（skill 可被跳过） | `verify-before-code` 技能把验证做成**不可跳过** |
| 无官方一致性 linter | `check_plugin` 是**第一个严格 1.0.0 linter** |

## 它能做什么

五个零依赖 MCP 工具：

| 工具 | 拦截什么 | 技术 |
| --- | --- | --- |
| `verify_code` | 编造的 API / 未定义符号 | Python AST + TS/JS 词法分析 |
| `scan_hallucination` | 占位代码、夸大声称、虚构内容 | 3 组 28+ 信号 |
| `check_plugin` | 不合规的插件打包 | 严格 1.0.0 linter |
| `sandbox_run` | 什么都没跑就说"测试通过" | 确定性执行通道 |
| `schema_validate` | 不合法的结构化输出 | JSON Schema 校验 |

## 实机演示

```
$ verify_code(source="def f():\n    return magic_unknown()\n", language="python")
{
  "language": "python",
  "suspects": ["magic_unknown"]      # ← 幻觉 API 被抓
}

$ scan_hallucination(source="The feature is production ready, all tests pass. Trust me.")
{
  "hits": [
    {"word": "all tests pass", "group": "oversold", "line": 1},
    {"word": "production ready", "group": "oversold", "line": 1},
    {"word": "trust me", "group": "oversold", "line": 1}
  ],
  "clean": false                      # ← 夸大声称被抓
}

$ check_plugin(path="/path/to/AgentSeed")
{ "ok": true, "errors": [], "warnings": [] }   # ← 严格 1.0.0 合规
```

## 快速开始

```bash
git clone https://github.com/weed33834/AgentSeed.git
# 或：https://gitcode.com/badhope/AgentSeed · https://gitee.com/badhope/AgentSeed
```

1. 把 `AgentSeed/` 目录丢进任何支持 Agent Plugins 1.0.0 的客户端（Cursor、VS Code、Claude Code、Copilot……）。无需构建、无需安装、零依赖。
2. 客户端从 `plugin.json` + `mcp.json` 自动发现 `verify-before-code` 技能和 `agentseed` MCP 服务器。
3. **完事。** 技能从此给每个编程任务上锁：契约 → 实现 → 验证 → 证据。

想独立自测：

```bash
python3 server/guard_engine.py              # 一致性 + 演示
python3 -m unittest discover -s server      # 19 个单元测试
```

## 内置护栏库（中 / EN / 日本語）

| 资源 | 内容 |
| --- | --- |
| `PROMPT-POOL` | 20+ 条即用型护栏提示词：完成证据、先验证后声称、不确定性、API 验证、引用规则等 |
| `HALLUCINATION-PATTERNS` | 失效模式目录：五类代码幻觉分类法 + SoK 结论 + 真实法律/对话案例 |
| `VERIFICATION-CHECKLIST` | 任务收尾可执行清单：风险分级 → 契约 → 证据 → 语言审查 |
| `SDD-CONTRACT` | 每个编程任务必须满足的契约 |
| `VENDOR-SOLUTIONS` | 厂商方案引进地图（Anthropic、OpenAI、AWS、NVIDIA、IBM、Guardrails AI、Vectara） |

## 闸门如何工作

1. **写码前** —— 加载 SDD 契约，一句话陈述。
2. **实现** —— 只写真实代码：不用占位符、不编造 API。
3. **宣称完成前** —— 调用 `verify_code` + `scan_hallucination`；运行时声明用 `sandbox_run` 实证；结构用 `schema_validate` 校验。
4. **语言审查** —— 完成报告附证据；夸大词汇禁用。
5. 只有**全部检查通过**才能标记完成。

## 对比

| | Anti-Hallucinate（mcpmarket） | superpowers | **AgentSeed** |
| --- | --- | --- | --- |
| 碰代码 | ❌ 仅聊天 | 仅 prompt | ✅ AST 分析 |
| 跑工具 | ❌ | ❌ | ✅ 5 个 MCP 工具 |
| 强制 | 软 | 软 | **硬闸门** |
| 1.0.0 linter | ❌ | ❌ | ✅ 首个 |

## 路线图

- [x] 混合 Skill + MCP 护栏，5 个工具 —— 首个严格 1.0.0 linter
- [x] 提示池 + 模式库 + 分组信号 + 厂商技术引进
- [x] `verify_code` 支持 TypeScript / JavaScript（零依赖词法分析）
- [ ] `verify_code` 支持 Go
- [ ] 结构化输出的语法约束解码
- [ ] 可选远程事实检查器（HHEM 风格）MCP 服务器

## 常见问题

**需要特定的大模型吗？** 不需要——与客户端、模型无关。闸门由 skill + MCP 服务器强制，不依赖任何模型。

**零依赖？** 是的。整个 MCP 服务器是纯 Python 标准库。

**符合规范吗？** `check_plugin` 按 1.0.0 §5/§6/§7 校验插件——而 AgentSeed 通过了它自己的 linter（`ok: true`）。

## 贡献

欢迎 Issue、PR 和点子。方向见[路线图](#路线图)——如果你发现了我们还没收录的幻觉模式，开个 Issue。

## 许可证

MIT © AgentSeed。见 [LICENSE](./LICENSE)。

---

<div align="center">

⭐ **如果 AgentSeed 帮你拦住了幻觉代码，给个 star 吧——这是"护栏有用"最好的信号。**

</div>
