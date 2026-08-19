# 厂商方案库 —— 防幻觉技术与引进状态

> 各大厂商、学术界与 MCP 生态的防幻觉技术地图，以及每一项在 AgentSeed 中的落点。
>
> 图例：✅ 已引进（提示/规则）· 🛠 已实现为 AgentSeed MCP 工具 · ➡️ 建议未来版本引入 · 📄 已文档化为参考资料。

## 1. 引进矩阵

| 技术 | 来源 | 核心机制 | 在 AgentSeed 中 |
| --- | --- | --- | --- |
| "我不知道"兜底 | Anthropic / OpenAI | 允许坦诚不确定，而不是猜测 | ✅ 提示池 D1/D2 |
| 直接引用接地 | Anthropic | 推理前先抽取原文引用 | ✅ 提示池 C1/G1 |
| 引用验证 | Anthropic | 声明→找支撑引用，找不到就撤回 | ✅ 提示池 G1-J1 |
| 思维链验证 | Anthropic / 学术界 | 用独立推理轮次做审查者 | ✅ 提示池 A2 |
| Best-of-N / 自一致性 | Anthropic / 学术界 | 跑 N 次对比输出 | ✅ 提示池 J3/J4 |
| 迭代精炼 | Anthropic | 把输出喂回去复查 | ✅ 提示池 J3/J4 |
| 外部知识限制 | Anthropic | 只用提供文档，不靠通用知识 | ✅ 提示池 I2 |
| 接地 / RAG | Google / Microsoft / Progress | 答案锚定检索来源 | ✅ 提示池 I2 |
| 指令层级 | OpenAI | 冲突时 system > user > model | 📄 建议 |
| 结构化输出（JSON Schema） | OpenAI / Guardrails AI | 信任前先过 schema | 🛠 `schema_validate` |
| 输入/输出护栏 | OpenAI Agents SDK | 违规即中断流水线 | ✅ 四道闸门 SKILL |
| 确定性执行 | CDV / 沙箱工具调用 | 跑测试，观察结果 | 🛠 `sandbox_run` |
| 双通道取最小 | CDV | 确定性 + LLM 批评者，一票否决 | ✅ SKILL 闸门 3/4 |
| 静态 AST 分析 | Axivion / tree-sitter MCP | 未定义符号 = 编造 API | 🛠 `verify_code` |
| NeMo 五类护栏 | NVIDIA NeMo Guardrails | 输入/对话/检索/执行/输出 | ✅ 映射到四道闸门 |
| 自动推理检查 | AWS Bedrock | 策略的数学验证 | 📄 建议 |
| Granite Guardian 风险标记 | IBM | 护栏模型标记幻觉/有害内容 | 📄 建议 |
| 验证器中心（50+） | Guardrails AI | 可插拔验证器（PII、毒性等） | ✅ 提示池（子集） |
| 幻觉评估模型 | Vectara HHEM | 检测摘要中无支撑内容 | 📄 建议 |
| SelfCheckGPT / FActScore | 学术界 | 采样比对 / 事实锚定检查 | 📄 建议 |
| 约束解码 | 学术界（outlines） | 语法约束生成 | ➡️ 路线图（TS/Go + 语法） |
| 幻觉模式分类法 | arXiv:2404.00971 | 代码幻觉五类目录 | ✅ 幻觉模式库 |

## 2. 工具能力清单

| 新能力 | 类型 | 引进的技术 |
| --- | --- | --- |
| `sandbox_run` | MCP 工具 | 确定性执行通道（CDV 通道 A / Anthropic 用执行验证 / AWS 推理验证精神）——"测试通过"变成可观测事实 |
| `schema_validate` | MCP 工具 | 结构化输出校验（OpenAI 结构化输出 / Guardrails AI 验证器 / OWASP LLM09）——先 schema 后信任 |
| Best-of-N + 迭代精炼 | 提示池 | Anthropic 进阶技术 J3/J4 |
| VENDOR-SOLUTIONS | 参考文档 | 完整引进地图（本文件） |

## 3. 建议下一步（未来版本）

1. **约束解码 / 语法** —— 把 `schema_validate` 的 schema 接入生成端（outlines 风格），让模型只能产出合规 JSON。
2. **HHEM 式事实检查器** —— 可选远程 MCP 服务器，包装幻觉评估模型用于长文摘要。
3. **沙箱隔离加固** —— 给 `sandbox_run` 加资源上限（内存/网络/文件系统），用 Docker/gVisor 后端。
4. **TypeScript/Go 静态分析** —— 用 tree-sitter 的 `verify_code` 覆盖非 Python 项目（当前 AST 仅支持 Python）。

## 4. 为什么这些都保持合规

以上一切都在 Agent Plugins 1.0.0（§6/§7）定义的 `skills/` + `mcp.json` 打包结构内。
规范约束的是插件**如何打包与发现**——从不约束 skill **教什么**或 MCP 服务器**暴露什么工具**。
新工具均为纯标准库 Python（零依赖），客户端无需任何安装。
