# AgentSeed — 技術設計

> AgentSeed の日本語技術設計。英語版 [DESIGN.md](./DESIGN.md)・中文版 [DESIGN.zh.md](./DESIGN.zh.md)。

## 1. 背景と問題

### 1.1 仕様は本物だが、誇張されている

Agent Plugins **1.0.0** は 2026 年 8 月に公開された本物のオープン仕様です。技術運営
委員会には **Amazon、Cursor、Microsoft、OpenAI、Vercel** が各 1 名ずつ代表を送って
います。2 点の訂正：

- **Google は委員会にいません。** 「6 社連合リリース」はコンテンツファームによる
  「ベンダー中立の標準化団体」の誇張表現です。
- これは**パッケージング標準**であり、製品ではありません。「箱」（`plugin.json`、
  `skills/`、`mcp.json`）を標準化していますが、意図的に 2 つの穴を残しています。

### 1.2 仕様の 2 つの穴（＝我々の機会）

1. **強制メカニズムがない。** クライアントは skill を読み込む「ことができます」が、
   モデルに完了前の出力検証を強制する手段はありません。
2. **レジストリ / マーケット / 配布機構がない。** 配布はオープン。さらに MUST/SHOULD
   ルールは定義されているのに、**公式 linter がありません**。

### 1.3 市場の隙間

| 既存 | 機能 | 欠けている点 |
| --- | --- | --- |
| mcpmarket `Anti-Hallucinate` | 行動ガードレール、チャットの誠実さのみ | コード・ツールに非対応 |
| `obra/superpowers` | プロンプトのみのコーディングワークフロー | ハード検証なし |
| 一般的な MCP サーバー | モデルへ API を公開 | モデル自身が書いたコードを検証しない |

AgentSeed は「**コードレベル + 実ツール実行 + Skill/MCP クローズドループ強制**」を
埋めます。`check_plugin` は 1.0.0 初の linter です。

## 2. 設計目標

- **クロスクライアント** — 1.0.0 準拠、仕様対応クライアントでネイティブ読み込み。
- **クローズドループ強制** — 弱い Skill 指示をハードな MCP ゲートに接続。
- **ゼロ依存** — 純標準ライブラリ Python、SDK バージョン非依存。
- **初の linter** — 1.0.0 向け `check_plugin`。

## 3. アーキテクチャ

```
            ┌─────────────────────────────────────────────┐
            │  コーディングエージェント（Cursor/VS Code 等）│
            └───────────────┬───────────────┬─────────────┘
                            │ 読み込み       │ 起動（stdio）
                            ▼                ▼
                 ┌──────────────────┐  ┌──────────────────────────┐
                 │  Skill           │  │  MCP サーバー（agentseed） │
                 │  verify-before-  │  │  guard_server.py          │
                 │  code            │  │    │                      │
                 └────────┬─────────┘  │    ▼                      │
                          │ 指示        │  guard_engine.py          │
                          │            │   ├ verify_code（AST）     │
                          │            │   ├ scan_hallucination     │
                          │            │   ├ check_plugin（linter） │
                          │            │   ├ sandbox_run（実行検証）│
                          │            │   └ schema_validate        │
                          ▼            └──────────────────────────┘
                 ┌──────────────────┐
                 │ リファレンス     │  SDD-CONTRACT / PROMPT-POOL /
                 │ ライブラリ       │  HALLUCINATION-PATTERNS /
                 │（英/中/日）      │  VERIFICATION-CHECKLIST /
                 └──────────────────┘  VENDOR-SOLUTIONS
```

## 4. MCP インターフェース契約

トランスポート：stdio 上の行区切り JSON-RPC 2.0。サーバー名 `agentseed`、
プロトコル `2024-11-05`。

| ツール | 説明 |
| --- | --- |
| `verify_code` | 未定義/未インポートシンボルの静的 AST 検出 |
| `scan_hallucination` | 3 グループ幻覚シグナルスキャン（stub_code/oversold/fabricated） |
| `check_plugin` | Agent Plugins 1.0.0 適合性 linter |
| `sandbox_run` | 決定的実行チャネル（サブプロセス・タイムアウト付き） |
| `schema_validate` | JSON Schema サブセット検証（ゼロ依存） |

## 5. 主要アルゴリズム

- **`detect_undefined_symbols`** — `ast` 解析で定義済み集合（builtins、インポート、
  def/class、引数）を収集し、外れの `Name`/`Call` を検出。静的スコープのみ、実行
  なし、属性呼び出しは非展開（誤検出の可能性）。MVP は Python のみ。
- **`scan_hallucination_words`** — 28+ シグナルのグループ化ワード境界スキャン。
  出典：SFD Lab 5 ステップチェックリスト、CDV（"'done, all tests pass' は主張であり
  証拠ではない"）、reze83 先検証ルール。
- **`check_plugin_conformance`** — §5/§6/§7 の厳格 linter：閉じたトップレベル
  スキーマ、`name` 制約、SKILL.md frontmatter（ディレクトリ名一致、
  description ≤1024）、mcp.json の閉じたフィールドと cwd 形式。
- **`sandbox_run`** — shell なしサブプロセス実行（タイムアウト 1–120 秒、出力
  トランケート）。CDV チャネル A の実装。
- **`schema_validate`** — type/enum/const/minLength/maxLength/pattern/minItems/
  maxItems/items/properties/required/additionalProperties をサポートする
  ゼロ依存サブセット検証。

## 6. 1.0.0 適合性チェックリスト

| 仕様節 | 要件 | AgentSeed |
| --- | --- | --- |
| §5.2 マニフェスト | ルート `plugin.json`、クローズドスキーマ | ✅ |
| §5.3 必須 | `$schema` = 1.0.0 アドレス、`name` 必須 | ✅ |
| §5.5 命名 | 1–64 文字、`[a-z0-9.-]`、`--`/`..` 禁止 | ✅ |
| §5.4 メタデータ | `repository` 等は文字列、`author` は name/email/url のみ | ✅ |
| §6.1/§7.1 スキル | `skills/<name>/SKILL.md`、Agent Skills frontmatter | ✅ |
| §7.2 mcp.json | `$schema`+`mcpServers` のみ、stdio + `cwd=${PLUGIN_ROOT}` | ✅ |
| §8 検出 | マニフェスト+スキル+mcp をクライアントが読む | ✅（設計上） |
| §11 linter | （仕様に無し） | ✅ `check_plugin` が埋める |

## 7. 競合比較

| | Anti-Hallucinate | superpowers | **AgentSeed** |
| --- | --- | --- | --- |
| コードに触れる | ❌ | プロンプトのみ | ✅ AST |
| ツール実行 | ❌ | ❌ | ✅ MCP（実行+検証） |
| 強制 | 弱い | 弱い | **ハードゲート** |
| 1.0.0 linter | ❌ | ❌ | ✅ |

## 8. ロードマップ（堀）

1. `verify_code` を TypeScript（tree-sitter）/Go に拡張。
2. `sandbox_run` の隔離強化（メモリ/ネットワーク/FS 上限、Docker/gVisor）。
3. `check_contract` — ユーザーのプライベート仕様を契約として取り込む。
4. PROMPT-POOL を Cursor rules / CLAUDE.md / AGENTS.md に展開。
5. 1.0.0 に欠ける**レジストリ**配布機構を実装。

## 9. リスク

- 静的スコープ解析 → 動的/属性アクセスで誤検出の可能性。
- 仕様が新しい（2026-08）。クライアント採用とスキーマが変動しうる。
- 強制はクライアントがスキルのゲート指示を守るかに依存。

## 10. ビルドとテスト

```bash
python3 server/guard_engine.py                 # 自己テスト + デモ
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize",...}' \
            '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
            '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python3 server/guard_server.py
```
