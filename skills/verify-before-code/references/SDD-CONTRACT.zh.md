# SDD 契约 —— 规范驱动开发护栏

本契约由 `verify-before-code` 技能在**写码之前**加载。一个编程任务只有当它能对照
本契约表达，并且通过 AgentSeed 的 MCP 闸门时，才算合格。

## 1. 任务契约必须说明什么

写码之前，智能体必须能回答全部：

- **目标** —— 代码必须产生什么行为。
- **接口** —— 代码暴露的确切函数/类/端点名称与签名（不得自创调用方没要求的名字）。
- **输入与输出** —— 类型与结构，包括错误情况。
- **非目标** —— 明确说明哪些不在范围内（YAGNI）。
- **验证方式** —— "完成"如何被证明（一个测试、一条命令，或一次工具调用）。
- **风险等级** —— 关键/高/中/低（见验证清单）。

若其中任何一项未知，智能体必须停下来询问，而不是猜测。

## 2. 禁止模式（幻觉信号）

产出的代码中出现以下情况，即表示任务**尚未**完成：

- 用 `stub`/`mock`/`fake`/`placeholder`/`dummy`/`todo`/`fixme`/`tbd`/`tba`/
  `not implemented`/`coming soon` 充当真实逻辑。
- 调用项目里从未定义或导入的函数/类（知识冲突幻觉——编造 API 占代码幻觉的
  15.1%，见 arXiv:2404.00971）。
- 调用只在"最新版文档"里存在、而**已安装版本**里不存在的 API（先查锁文件）。
- 在需要计算值或拉取值的地方返回硬编码值。
- 不在本轮读取文件就引用其内容或行号（文件可能已变）。
- 完成报告中出现无证据附带的夸大词汇：
  `guaranteed`、`definitely works`、`all tests pass`、`everything works`、
  `fully tested`、`production ready`、`no bugs`、`works perfectly`、
  `should work`、`trust me`。

## 3. 验证闸门（由 agentseed MCP 服务器运行）

| 工具 | 通过条件 |
| --- | --- |
| `verify_code` | `suspects` 为空（未使用任何未定义/未导入的符号） |
| `scan_hallucination` | `clean` 为 `true`，且无 `stub_code`/`oversold`/`fabricated` 命中 |

两者都通过，智能体才能报告完成。完成报告必须附上产生"通过"的证据
（命令、输出、文件）。

## 4. 失败处理

闸门失败时，智能体必须：

1. 阅读被标记的符号/行及其 `group`（`stub_code`/`oversold`/`fabricated`）。
2. 要么正确地实现/导入它，要么换成真实依赖，要么补上缺失的证据。
3. 重跑闸门直到通过。
4. 只有当某个告警确实无法消除时，才把它抛给用户——绝不要悄悄标记完成。

## 5. 配套资源

- `PROMPT-POOL.zh.md` —— 本契约每条规则的即用型提示词。
- `HALLUCINATION-PATTERNS.zh.md` —— 这些规则背后的失效模式目录。
- `VERIFICATION-CHECKLIST.zh.md` —— 任务收尾的可执行清单。
