# AgentSeed —— 技术设计

> AgentSeed 的中文技术设计。英文版见 [DESIGN.md](./DESIGN.md)。

## 1. 背景与问题

### 1.1 规范是真的，但被夸大了

Agent Plugins **1.0.0** 是 2026 年 8 月发布的真实开放规范，技术指导委员会由
**Amazon、Cursor、Microsoft、OpenAI、Vercel** 各派一名代表组成。两点澄清：

- **谷歌不在委员会名单里。** "六巨头联合发布"是内容农场把"厂商中立标准体"夸大而成。
- 它是**打包标准**，不是产品。它标准化了"包装盒"（`plugin.json`、`skills/`、`mcp.json`），
  但故意留了两个口子。

### 1.2 规范的两个缺口（我们的机会）

1. **没有强制执行机制。** 客户端"可以"加载 skill，但没有任何手段强迫模型在宣称完成前
   真正验证输出。
2. **没有注册表 / 市场 / 分发机制**——分发是开放的；而且尽管规范定义了 MUST/SHOULD，
   **却没有官方 linter**。

### 1.3 市场缺口

| 现有方案 | 做什么 | 缺什么 |
| --- | --- | --- |
| mcpmarket `Anti-Hallucinate` | 行为护栏，只让聊天诚实（别编引用/日期） | 不碰代码、不跑工具 |
| `obra/superpowers` | 纯 prompt 编码工作流 | 无硬核校验 |
| 典型 MCP 服务器 | 给模型暴露一个 API | 没有"校验模型自己产出的代码" |

AgentSeed 填补：**代码级 + 真跑工具 + Skill/MCP 闭环强制**。`check_plugin` 是
1.0.0 的首个 linter。

## 2. 设计目标

- **跨客户端** —— 符合 1.0.0，在支持规范的客户端原生加载。
- **闭环强制** —— 软的 Skill 指令与硬的 MCP 闸门绑死。
- **零依赖** —— 纯标准库 Python，不挑 SDK 版本。
- **抢首发 linter** —— 面向 1.0.0 的 `check_plugin`。

## 3. 架构

```
            ┌─────────────────────────────────────────────┐
            │  编程智能体（Cursor / VS Code / Copilot）     │
            └───────────────┬───────────────┬─────────────┘
                            │ 加载           │ 启动（stdio）
                            ▼                ▼
                 ┌──────────────────┐  ┌──────────────────────────┐
                 │  Skill           │  │  MCP 服务器（agentseed）   │
                 │  verify-before-  │  │  guard_server.py          │
                 │  code（闸门逻辑）│  │    │                      │
                 │                  │  │    ▼                      │
                 └────────┬─────────┘  │  guard_engine.py          │
                          │ 指示       │   ├ detect_undefined_      │
                          │ 模型调用： │  │   │   symbols（AST）      │
                          │            │  │   ├ scan_hallucination_  │
                          │            │  │   │   words（正则）       │
                          │            │  │   └ check_plugin_        │
                          ▼            │       │ conformance（JSON） │
                 ┌──────────────────┐  └──────────────────────────┘
                 │  SDD-CONTRACT     │
                 │  （写码前加载）   │
                 └──────────────────┘

  流程：加载契约 → 实现 → verify_code + scan_hallucination →
        都通过？→ 标记完成。否则修复并重跑。
```

## 4. MCP 接口契约

传输：基于 stdio 的逐行 JSON-RPC 2.0。服务器名 `agentseed`，版本 `1.0.0`，
协议 `2024-11-05`。

| 方法 | 说明 |
| --- | --- |
| `initialize` | 握手，返回 protocolVersion / capabilities / serverInfo |
| `tools/list` | 返回 5 个工具 |
| `tools/call` | 调用 `verify_code` / `scan_hallucination` / `check_plugin` / `sandbox_run` / `schema_validate` |

工具签名：见英文版 §4.2。

## 5. 关键算法

- **`detect_undefined_symbols`**：双后端——
  - Python（AST）：`ast` 解析，收集已定义名（builtins、导入别名、def/class 名、
    参数），再扫描不在集合内的 `Name`/`Call`。
  - TypeScript/JavaScript（词法）：正则收集导入（具名/默认/命名空间/解构）、
    声明（function/class/interface/type/enum/const/let/var）、函数参数，再标记
    顶层调用与 `new` 表达式中未定义的被调者（成员访问 `obj.foo()` 不标记，
    关键词/全局白名单）。
  静态检查、不跑运行时；TS 通道是词法而非类型检查——动态/全局引用可能误报，
  解构边界情况可能漏报。
- **`sandbox_run`**：无 shell 子进程执行（超时 1–120 秒、输出截断）。CDV 通道 A
  的落地——"测试通过"变成可观测事实。
- **`schema_validate`**：零依赖 JSON Schema 子集校验（type/enum/const/minLength/
  maxLength/pattern/minItems/maxItems/items/properties/required/additionalProperties）。
- **`scan_hallucination_words`**：逐行正则词边界扫描**分组信号池（28+ 词）**：
  - `stub_code`：stub/mock/fake/placeholder/dummy/todo/fixme/xxx/tbd/tba/wip/
    "not implemented"/"coming soon"
  - `oversold`：guaranteed/"definitely works"/"all tests pass"/"everything works"/
    "fully tested"/"production ready"/"no bugs"/"works perfectly"/"should work"/
    "trust me"/"works on my machine"/"100% correct"/"bug free"/"zero errors"
  - `fabricated`：simulated/hypothetical/imaginary/invented/fabricated/fictional/
    pretend/"made up"
  返回 `hits[]`（word/group/line）、`clean` 与分组计数。
  来源：SFD Lab 五步反幻觉清单第 5 步；CDV（"'done, all tests pass' 是声明不是
  证据"）；reze83 先验证后声称规则。
- **`check_plugin_conformance`**：校验 `plugin.json`（`$schema`=1.0.0 地址、必填
  `name`、合法 JSON）、各 `skills/*/SKILL.md` 是否存在、`mcp.json`（`$schema`、
  `mcpServers`）。返回 `ok` / `errors[]` / `warnings[]`。

## 6. 1.0.0 合规性核对

| 规范章节 | 要求 | AgentSeed |
| --- | --- | --- |
| §5.2 清单 | 根 `plugin.json`，closed schema（仅 `$schema`/`name`/`version`/`description`/`author`/`homepage`/`repository`/`license`/`keywords`/`extensions`） | ✅ |
| §5.3 必填 | `$schema` = 1.0.0 地址；`name` 必填 | ✅ |
| §5.5 命名 | 1–64 字符，`[a-z0-9.-]`，首尾字母数字，无 `--`/`..` | ✅ |
| §5.4 元数据 | `repository`/`homepage`/`license` 为字符串；`author` 仅限 `name`/`email`/`url` | ✅ |
| §6.1/§7.1 技能 | `skills/<name>/SKILL.md`；Agent Skills frontmatter（name 匹配目录、description ≤1024） | ✅ |
| §7.2 mcp.json | 仅 `$schema` + `mcpServers`；stdio 服务器含 `command`，`cwd` = `${PLUGIN_ROOT}` | ✅ |
| §8 发现 | 客户端读取清单+技能+mcp | ✅（设计如此） |
| §11 linter | （规范无） | ✅ `check_plugin` 严格 1.0.0 linter |

## 7. 竞品对比

| | Anti-Hallucinate | superpowers | **AgentSeed** |
| --- | --- | --- | --- |
| 碰代码 | ❌ | 仅 prompt | ✅ AST |
| 跑工具 | ❌ | ❌ | ✅ MCP |
| 强制 | 软 | 软 | **硬闸门** |
| 1.0.0 linter | ❌ | ❌ | ✅ |

## 8. 路线图（护城河）

1. `verify_code` 扩展到 Go（TS/JS 词法分析已随 v1.0 提供）。
2. 加 `sandbox_run` —— 在沙箱里真实执行测试/命令（实现 CDV 通道 A 的确定性下限）。
3. 加 `check_contract` —— 把用户的私有规范作为契约摄入。
4. 把 PROMPT-POOL 接入各客户端配置（Cursor rules、CLAUDE.md、AGENTS.md），
   让提示在"非插件感知"的客户端也生效。
5. 填补 1.0.0 缺失的**注册表**分发机制。

## 9. 风险

- 静态作用域分析 → 对动态/属性访问可能漏报。
- 规范很新（2026-08），客户端 adoption 与 schema 可能变动。
- 强制依赖客户端是否真正遵守 skill 的闸门指令。

## 10. 构建与测试

```bash
python3 server/guard_engine.py                 # 自测 + 演示
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize",...}' \
            '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
            '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python3 server/guard_server.py
```
