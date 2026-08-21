<div align="center">

# 🛡️ AgentSeed

**AI コーディングエージェント向け幻覚防止ガードレール。**

[Agent Plugins 1.0.0](https://agent-plugins.org) 準拠のハイブリッドプラグイン
（Skill + MCP サーバー）。仕様駆動開発を強制し、**コードが「完了」とマークされる前に
検証**します — "Done, all tests pass" を主張ではなく観測事実にします。

[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.3.0-blue)](https://github.com/weed33834/AgentSeed/releases)
[![Agent Plugins](https://img.shields.io/badge/Agent%20Plugins-1.0.0-purple)](https://agent-plugins.org)
[![CI](https://github.com/weed33834/AgentSeed/actions/workflows/ci.yml/badge.svg)](https://github.com/weed33834/AgentSeed/actions)
[![Stars](https://img.shields.io/github/stars/weed33834/AgentSeed)](https://github.com/weed33834/AgentSeed)
[![Platforms](https://img.shields.io/badge/platform-Cursor%20%7C%20VS%20Code%20%7C%20Claude%20Code%20%7C%20Copilot-blue)](https://agent-plugins.org)

**日本語** · [English](./README.md) · [中文](./README.zh.md)

⭐ **役立つと思ったらスターをお願いします — 幻覚コードを出荷する前にガードレールを
知る開発者を増やすことができます。**

</div>

---

## なぜ AgentSeed なのか

LLM は幻覚します — コードでは**存在しない API、未定義の識別子、偽のテスト合格、
自信過剰な誇張主張**として現れます。データ：

- コード幻覚の **15.1%** は知識衝突型：存在しない・未インポートの API 呼び出し
  （[arXiv:2404.00971](https://arxiv.org/abs/2404.00971)）。
- 幻覚コードの **<10%** しかテストで検出されません — ほとんどが CI をすり抜けます（同上）。
- モデル出力エラーの **60%+** は**検証不能**（FAVA、[SoK](https://arxiv.org/abs/2502.18468) 引用）。

プロンプトのみのガードレールは「弱い」：モデルは検証に同意して、スキップできます。
**AgentSeed は指示をハードな MCP ゲートに縛ります** — 証拠はモデルの自己申告ではなく、
実行されたコードが生み出します。

1.0.0 仕様が意図的に残した 2 つの穴も埋めます：

| 仕様の穴 | AgentSeed の対応 |
| --- | --- |
| 強制メカニズムなし（スキルは任意） | `verify-before-code` を**スキップ不可**に |
| 公式 linter なし | `check_plugin` が**初の厳格 1.0.0 linter** |

## 機能

ゼロ依存の MCP ツール 5 つ：

| ツール | ブロックするもの | 技術 |
| --- | --- | --- |
| `verify_code` | 捏造 API / 未定義シンボル | Python AST + TS/JS 語彙パス |
| `scan_hallucination` | プレースホルダー、誇張、捏造 | 3 グループ 28+ シグナル |
| `check_plugin` | 不適合なプラグイン | 厳格 1.0.0 linter |
| `sandbox_run` | 実行せずに「テスト合格」 | 決定的実行チャネル |
| `schema_validate` | 不正な構造化出力 | JSON Schema 検証 |

## ライブデモ

```
$ verify_code(source="def f():\n    return magic_unknown()\n", language="python")
{
  "language": "python",
  "suspects": ["magic_unknown"]      # ← 幻覚 API を検出
}

$ scan_hallucination(source="The feature is production ready, all tests pass. Trust me.")
{
  "hits": [
    {"word": "all tests pass", "group": "oversold", "line": 1},
    {"word": "production ready", "group": "oversold", "line": 1},
    {"word": "trust me", "group": "oversold", "line": 1}
  ],
  "clean": false                      # ← 誇張主張を検出
}

$ check_plugin(path="/path/to/AgentSeed")
{ "ok": true, "errors": [], "warnings": [] }   # ← 厳格 1.0.0 適合
```

## クイックスタート

```bash
git clone https://github.com/weed33834/AgentSeed.git
# または：https://gitcode.com/badhope/AgentSeed · https://gitee.com/badhope/AgentSeed
```

1. `AgentSeed/` ディレクトリを Agent Plugins 1.0.0 対応クライアント（Cursor、VS Code、
   Claude Code、Copilot…）に置くだけ。ビルド不要・インストール不要。コアは依存ゼロ（オプションの拡張は下記）。
2. クライアントが `plugin.json` + `mcp.json` から `verify-before-code` スキルと
   `agentseed` MCP サーバーを自動検出します。
3. **完了。** 以降、すべてのコーディングタスクにゲートがかかります：
   契約 → 実装 → 検証 → 証拠。

スタンドアロンでの自己チェック：

```bash
python3 server/guard_engine.py              # 適合性 + デモ
python3 -m unittest discover -s server      # 50+ 個のユニットテスト
```

> **Windows の注意：** `mcp.json` は `python3` でサーバーを起動します。多くの Windows
> 環境ではこの別名が Microsoft Store のスタブです。サーバーが起動しない場合は
> `command` を `["python", "server/guard_server.py"]` またはインタープリターの絶対パスに
> 変更してください。

## 変更履歴

[CHANGELOG.md](./CHANGELOG.md) を参照。

### 1.3.0（要約）
- **モジュール化:** `guard_engine.py` を `server/engine/` パッケージへ分割。手書き実装を標準ライブラリの車輪に置換 — jsonschema（Draft 2020-12 フル検証）、pyflakes（F821 未定義名分析）、PyYAML（frontmatter）。すべてオプションで、未インストール時は内蔵実装へ自動フォールバック。
- **一貫性修正:** スキル文と重要度モデルの整合、バージョンの plugin.json 単一ソース化、インストーラの推測パス削除、プラットフォームマトリクスの正直なステータス。

### 1.2.0（要約）
- **重要度レベル:** 各ヒットに `error`/`warning`/`info` を付与。既定では oversold/fabricated のみブロックし、TODO 系は warning へ。設定で再マップ可能。
- **永続設定:** 仕様 §9.1 に従い `${PLUGIN_DATA}/agentseed.config.json` から allowlist・重要度マップ・サンドボックスタイムアウトを読み込み。
- **CLI:** `server/guard_cli.py` が `verify`/`scan`/`check --ci`/`sandbox` を提供。終了コードで人間の PR もゲート可能。
- **Linter:** §7.2.1/§9.1 準拠 — サーバーエントリのクローズドバリアント検証、予約 env キー、リモート URL ルール。

## 内蔵ガードレールライブラリ（日本語 / EN / 中文）

| リソース | 内容 |
| --- | --- |
| `PROMPT-POOL` | 20+ のコピペ用プロンプト：完了証拠、先検証、不確実性、API 検証、引用規則 |
| `HALLUCINATION-PATTERNS` | 失敗モードカタログ：5 分類法 + SoK 知見 + 実在の法律/対話事例 |
| `VERIFICATION-CHECKLIST` | 実行可能チェックリスト：リスク分類 → 契約 → 証拠 → 言語監査 |
| `SDD-CONTRACT` | すべてのタスクが満たすべき契約 |
| `VENDOR-SOLUTIONS` | ベンダー技術導入マップ（Anthropic、OpenAI、AWS、NVIDIA、IBM、Guardrails AI、Vectara） |

## ゲートの仕組み

1. **コーディング前** — SDD 契約を読み、1 文で述べる。
2. **実装** — 実コードのみ：プレースホルダー・API 捏造禁止。
3. **「完了」の前** — `verify_code` + `scan_hallucination` を呼ぶ；実行主張は
   `sandbox_run` で実証；構造は `schema_validate` で検証。
4. **言語監査** — 完了報告に証拠添付；誇大語彙は禁止。
5. 全チェック通過時のみ完了とみなす。

## 比較

| | Anti-Hallucinate（mcpmarket） | superpowers | **AgentSeed** |
| --- | --- | --- | --- |
| コードに触れる | ❌ チャットのみ | プロンプトのみ | ✅ AST 解析 |
| ツール実行 | ❌ | ❌ | ✅ MCP ツール 5 種 |
| 強制 | 弱い | 弱い | **ハードゲート** |
| 1.0.0 linter | ❌ | ❌ | ✅ 初 |

## ロードマップ

- [x] ハイブリッド Skill + MCP、5 ツール — 初の厳格 1.0.0 linter
- [x] プロンプトプール + パターンライブラリ + グループ信号 + ベンダー技術
- [x] `verify_code` を TypeScript / JavaScript に拡張（ゼロ依存語彙パス）
- [ ] `verify_code` を Go に拡張
- [ ] 構造化出力の文法制約付きデコーディング
- [ ] 任意のリモートファクトチェッカー（HHEM 型）MCP サーバー

## FAQ

**特定の LLM が必要ですか？** いいえ — クライアント・モデル非依存。ゲートはスキル +
MCP サーバーが強制し、モデルには依存しません。

**ゼロ依存？** コアは依存ゼロです — 何もインストールせずに完全動作します。server/requirements.txt（jsonschema / pyflakes / pyyaml）を入れると schema_validate が Draft 2020-12 フル検証に、erify_code が pyflakes 分析に、frontmatter 解析がフル YAML にアップグレードされます（未インストール時は内蔵実装へ自動フォールバック）。

**適合していますか？** `check_plugin` が 1.0.0 §5/§6/§7 に照らして検証 — AgentSeed は
自身の linter を通過します（`ok: true`）。

## コントリビュート

Issue・PR・アイデア歓迎。方向性は[ロードマップ](#ロードマップ)を参照 —
未収録の幻覚パターンを見つけたら Issue を開いてください。

## ライセンス

MIT © AgentSeed。[LICENSE](./LICENSE) を参照。

---

<div align="center">

⭐ **AgentSeed が幻覚コードの出荷を防いだなら、スターをお願いします — ガードレールが
重要だという最良のシグナルです。**

</div>
