---
name: verify-before-code
description: >-
  コーディングエージェント向けガードレール。コード作成前に SDD 契約とプロンプト
  プールを読み込み、agentseed MCP サーバーの verify_code と scan_hallucination
  を呼び出し、両方が合格し完了報告に証拠が添付された場合のみ完了とみなす。
  コードの作成・編集・完了宣言のすべての場面で使用する。
license: MIT
compatibility: MCP サーバーは Python 3.9+ が必要。依存ゼロで動作；オプション（jsonschema、pyflakes、pyyaml）で精度向上、未インストール時は自動フォールバック。
metadata:
  author: AgentSeed
  version: "1.0.0"
  spec: agent-plugins-1.0.0
---

# コード前に検証する

AgentSeed ガードレール保護下のセッションにいます。`agentseed` MCP サーバーは利用
可能です。その役割は、幻覚コードやスタブコードの出荷を止めることです。以下のゲートを
**順番に**実行し、ゲート 3 はスキップ不可です。

## リファレンスライブラリ（必要に応じて読み込み）

| リソース | 目的 |
| --- | --- |
| `references/SDD-CONTRACT.ja.md` | すべてのコーディングタスクが満たすべき契約 |
| `references/PROMPT-POOL.ja.md` | コピペ可能なガードレールプロンプト集 |
| `references/HALLUCINATION-PATTERNS.ja.md` | 幻覚の失敗モードカタログ |
| `references/VERIFICATION-CHECKLIST.ja.md` | タスク完了時の実行可能チェックリスト |
| `references/VENDOR-SOLUTIONS.ja.md` | ベンダー技術と導入状況のマップ |

## ゲート 1 — 契約の読み込み（コード作成前）

実装を始める前に `references/SDD-CONTRACT.ja.md` を読んでください。未表明・仮定の
契約に対してコーディングしてはいけません。契約が無ければユーザーに求めます。

- コーディング対象の契約を 1 文で述べる。
- 契約として表現できないタスクなら、立ち止まって確認する。
- 出力リスクを分類する（Critical / High / Medium / Low）。Critical/High は全検査。

## ゲート 2 — 契約に沿った実装

契約を満たす最小のコードを書きます。実際に動く実装を優先し、プレースホルダーを
避けます。

- `stub`/`mock`/`fake`/`placeholder`/`dummy`/`todo`/`fixme`/`tbd`/
  `not implemented`/`coming soon` を実ロジックの代わりに**使わない**。
- このプロジェクトで定義・インポートされていないシンボルを**呼ばない**。
- インストール済みバージョンで検証していない API を**信頼しない**（PROMPT-POOL E1）。
- 今ターンで読んでいないファイルの内容・行番号を**断言しない**（PROMPT-POOL F1）。

## ゲート 3 — 完了宣言前の検証（必須・スキップ不可）

タスク完了をユーザーに伝える前に、最終ソースに**両方のツールを必ず**呼び出します：

```
verify_code(source=<最終ソース>, language="python")
scan_hallucination(source=<最終ソース>)
```

**このセッションに `agentseed` MCP ツールがない場合**、検証をスキップせず —
シェルから CLI の同等コマンドに降格します：

```bash
python <agentseedプラグインルート>/server/guard_cli.py verify <変更ファイル> --language python
python <agentseedプラグインルート>/server/guard_cli.py scan  "<最終ソースまたはファイル>"
```

`<agentseedプラグインルート>` の特定順序：`AGENTSEED_PLUGIN_ROOT` 環境変数 →
本スキルディレクトリ直下の `.agentseed-plugin-root` ファイル → 本スキルから上方向に
`plugin.json` と `server/guard_cli.py` を両方含むディレクトリを探索。CLI は同じ
ゲート規則です：終了コード 0 = 合格、1 = ブロッキングな指摘あり。

判定ルール：

- `verify_code` が `suspects: []` かつ `scan_hallucination` が `blocking: false`
  → 検証ゲート通過。
- `verify_code` に suspect（未定義/未インポートのシンボル）→ API を幻覚した可能性。
  修正（インポート・定義・実在の呼び出しへ置換）して再実行。
- `scan_hallucination` のヒットはまず `severity` フィールドで判断：
  - `error`（任意のヒット）→ `blocking: true`、タスクは**未完了**。指摘された行を
    修正して再実行。既定で `oversold` と `fabricated` は error：証拠を添付するか
    主張/内容を削除する。
  - `warning`（例：`stub_code` の既定）→ ブロックはしないが完了報告に必ず記載。
    実際に未完了の作業を示す場合は error として扱う。
  - `info` → 情報提供のみ、対応不要。

**ブロック中**の問題（`suspects` 非空または `blocking: true`）が残っている間は、
タスク完了と絶対にマークしないでください。解消できない場合は成功を主張せず、
ユーザーに明示的に報告します。

## ゲート 4 — 最終メッセージ前の言語監査

ゲートが通過しても言語監査を実行します（PROMPT-POOL C/D/G/J）：

- すべての記述は OBSERVED、または INFERRED とラベル付け。
- 証拠なしの誇大語彙なし（`guaranteed`、`fully tested`、`production ready`、
  `should work`、`trust me` 等）。
- 不確実さは正直に表現。引用・統計は実在のもの。
- 完了報告には証拠（実行コマンド、出力、読んだファイル）を添付。"Done, all
  tests pass" にログが無ければ、それは主張であり結果ではない。

## 任意 — プラグイン自身の検証

Agent Plugins 1.0.0 適合性チェック：

```
check_plugin(path=<agentseed プラグインルートの絶対パス>)
```

## なぜ存在するのか

プロンプトのみのガードレールは「弱い」：モデルは「検証してから完了」に同意して、
それをスキップできます。AgentSeed は弱い Skill 指示をハードな MCP ゲートに縛ります
— 証拠はモデルの自己申告ではなく、実際に実行されたコードが生み出します。リファレンス
ライブラリは、研究の各原理を実行可能な指示に変換します。
