---
name: verify-before-code
description: >-
  面向编程智能体的护栏。写码前加载 SDD 契约与提示池，随后调用 agentseed MCP
  服务器的 verify_code 与 scan_hallucination 工具；只有两者都通过且完成报告附
  带证据时，任务才可标记为完成。适用于智能体编写、修改或宣称完成代码的任何场景。
license: MIT
compatibility: MCP 服务器要求 Python 3.9+（纯标准库，无第三方依赖）。
metadata:
  author: AgentSeed
  version: "1.0.0"
  spec: agent-plugins-1.0.0
---

# 写码之前先验证

你正处于 AgentSeed 护栏保护的编程会话中。AgentSeed MCP 服务器（`agentseed`）
已就绪，它的职责是阻止你交付"幻觉代码"或"桩代码"。请**按顺序**执行下面的
闸门，并把闸门 3 视为不可跳过。

## 参考资料库（按需加载）

| 资源 | 用途 |
| --- | --- |
| `references/SDD-CONTRACT.zh.md` | 每个编程任务必须满足的契约 |
| `references/PROMPT-POOL.zh.md` | 即用型护栏提示词（完成声明、不确定性、API 验证、引用规则等） |
| `references/HALLUCINATION-PATTERNS.zh.md` | 幻觉失效模式目录（信号 + 对策） |
| `references/VERIFICATION-CHECKLIST.zh.md` | 任务收尾的可执行验证清单 |

## 闸门 1 —— 加载契约（写码之前）

在产出任何实现之前，先阅读 `references/SDD-CONTRACT.zh.md`。它定义了代码必须
满足的规范。不要对着隐含或未声明的契约写代码；若契约缺失，先向用户索取。

- 用一句话说明你正在按哪份契约编码。
- 若任务无法表达为契约，停下来澄清。
- 按清单给输出定级（关键/高/中/低）——关键与高风险走全套检查。

## 闸门 2 —— 按契约实现

写出满足契约的最小代码，优先真实可运行的实现，而不是占位符。

- **绝不**用 `stub`/`mock`/`fake`/`placeholder`/`dummy`/`todo`/`fixme`/
  `tbd`/`not implemented`/`coming soon` 充当可运行逻辑。
- **绝不**调用本项目内未定义或未导入的符号。
- **绝不**相信未经"已安装版本"验证的 API（见提示池 E1 —— "绝不编造 API"）。
- **绝不**不读文件就断言其内容或行号（见提示池 F1）。

## 闸门 3 —— 宣称完成之前先验证（强制，不可跳过）

在告诉用户任务完成之前，对最终源码**同时调用**两个工具：

```
verify_code(source=<最终源码>, language="python")
scan_hallucination(source=<最终源码>)
```

判定规则：

- `verify_code` 返回 `suspects: []` 且 `scan_hallucination` 返回 `clean: true`
  → 验证闸门通过。
- `verify_code` 返回任何 suspect（被使用/调用却从未定义或导入的符号）→ 你很可能
  幻觉出了一个 API。修复它（导入、定义，或换成真实调用）后重跑。
- `scan_hallucination` 返回命中时，看 `group` 字段：
  - `stub_code` → 任务**尚未**完成；把占位符换成真实代码后重跑。
  - `oversold` → 未经验证的自信声称（如 "all tests pass"、"production ready"）。
    附上证据或改写；重跑。
  - `fabricated` → 虚构/模拟内容；删除或接地；重跑。

只要任一工具仍报错，就绝不要标记编程任务完成。若你无法消除某个告警，如实向用户
报告，而不是谎称成功。

执行与结构同样用"可观测事实"来验证，而不是靠声称：

- 需要运行代码的声明（测试通过、类型检查干净、linter 通过）→ 用
  `sandbox_run(["python3", "-m", "pytest", ...])` 实证，并引用退出码 + 输出。
- 结构化输出（JSON、配置）→ 使用前用 `schema_validate(instance, schema)` 校验。
  绝不靠自我评估相信"它是合法的"。

## 闸门 4 —— 最终答复前的语言审查

即使闸门都过了，仍要跑一遍语言审查（提示池 C/D/G/J）：

- 每句陈述为 OBSERVED，或标注为 INFERRED。
- 无证据时不使用夸大词汇（`guaranteed`、`fully tested`、`production ready`、
  `should work`、`trust me` 等）。
- 不确定性被如实表达；引用与统计数字真实。
- 完成报告必须附证据：跑过的命令、输出、读过的文件。"Done, all tests pass"
  却没有日志，只是声明，不是结果。

## 可选 —— 校验插件自身

检查本插件是否符合 Agent Plugins 1.0.0：

```
check_plugin(path=<agentseed 插件根目录的绝对路径>)
```

## 为什么需要它

纯 prompt 的护栏是"软"的：模型可以口头答应验证，然后偷偷跳过。AgentSeed 把软的
Skill 指令和硬的 MCP 闸门绑死——证据由真实运行的代码产生，而不是模型的自我陈述。
参考资料库把研究里的每条防幻觉原则变成可执行的指令。
