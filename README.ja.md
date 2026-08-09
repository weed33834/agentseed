# AgentSeed

> **`pip install https://github.com/weed33834/agentseed/releases/download/v1.0.0/agentseed-1.0.0-py3-none-any.whl && agentseed forge`**

**🌐 [English](README.md) · [中文](README.zh.md) · [日本語](README.ja.md)**

**📦 [GitHub](https://github.com/weed33834/agentseed) (メイン) · [Gitee](https://gitee.com/badhope/agentseed) · [Gitcode](https://gitcode.com/badhope/agentseed)**

![License](https://img.shields.io/badge/license-Apache_2.0-blue)
![CI](https://github.com/weed33834/agentseed/actions/workflows/ci.yml/badge.svg)
![Personas](https://img.shields.io/badge/personas-5-green)
![Platforms](https://img.shields.io/badge/platforms-15-orange)
![Tests](https://img.shields.io/badge/tests-171%20passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-informational)

---

AIコーディングツールを開くたびに「rm -rf するな」「APIキーをベタ書きするな」「今のスタックは何」って毎回言ってませんか。AgentSeed はそれを一度書いて、使ってる全ツールに同期します。

プロジェクトを自動検出して、最適なペルソナを選び、Claude Code にも Cursor にも Copilot にも Windsurf にも Trae にも、全部にルールファイルを生成します。

```bash
agentseed forge
```

この一行だけ。空のディレクトリに1200行のAGENTS.mdができて、安全ルール、プロジェクト用スキル、各プラットフォーム設定が全部入ります。コード書いてても小説書いてても論文書いてても、同じコマンド。

---

## なにができるか

**安全ベースラインは上書き不可。** コアの安全ルール（rm -rf禁止、キーの捏造禁止、無断インストール禁止）は AgentSeed 本体に組み込まれていて、どのペルソナでも消せません。

**5つのシナリオパック、シーンに応じて自動ルーティング。** `coding`（デフォルト）、`conversation`、`novel`、`paper`、`agent-builder`。それぞれにプロンプト・スキル・ツール設定が入ってます。切替は `agentseed switch --profile novel`。

**14プラットフォーム、一発同期。** ツールごとにフォーマット違う問題、AgentSeedが吸収：
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
- 通義霊碼 → `.lingma/rules/project.md`
- 腾讯云コードアシスタント → `.comate/rules/project.mdr`
- Codex → `.codex/rules.md`
- AGENTS.md（20以上のツールがネイティブ読取）

**全プラットフォームにフック付き。** `adapters/hooks/` 以下、14の `pre_tool_use.py` が危険な操作を実行前にブロック。fail-open設計：フックがクラッシュしても操作は通る。

**MCPサーバー。** `agentseed serve` で起動。MCP対応クライアントなら `governance_check`（安全チェック）、`persona_list`、`persona_activate`、`gap_detect` がそのまま使える。

**自己進化。** プロジェクトの足りないところ（ツール不足、知らない分野）をスコア化して、何を入れればいいか提案します。魔法じゃない、加重計算式。スキル増やすほど精度上がる。

---

## インストール

```bash
pip install https://github.com/weed33834/agentseed/releases/download/v1.0.0/agentseed-1.0.0-py3-none-any.whl
```

ソースから：

```bash
git clone https://github.com/weed33834/agentseed.git
cd agentseed
pip install -e .
```

---

## 使い方

```bash
agentseed forge              # 検出 → 組立 → 生成
agentseed forge --dry-run    # プレビュー（書込なし）
agentseed forge --profile coding
agentseed forge --profile novel

agentseed switch --profile paper

agentseed sync               # 全プラットフォーム同期
agentseed sync --platform cursor

agentseed status             # いま何が入ってる？

agentseed serve              # MCPサーバー起動 (stdio)
agentseed serve --port 8080  # MCPサーバー起動 (HTTP)

agentseed platform list      # 14の内蔵プラットフォーム
agentseed platform import my-ide --entry .myide/rules.md --format markdown

agentseed persona list       # 使えるペルソナ一覧
agentseed persona search "product manager"
```

---

## 自分のプラットフォームを追加

```bash
agentseed platform import my-editor --entry .myeditor/rules.md --format markdown --hook-dir .myeditor
```

これで登録＋フック生成＋毎回の `agentseed sync` に含まれる。

---

## ディレクトリ構成

```
core/                  安全ベースライン（P0レッドライン、判定式、ルーター）
personas/              ペルソナごとのディレクトリ（coding, novel, paper...）
capabilities/          モジュール型スキルパック（testing, research, creative...）
adapters/hooks/        プラットフォーム別のツール実行前フック
src/agentseed/         CLI、同期エンジン、ルーター、forge、自己進化
```

---

## 類似プロジェクトとの違い

- **agent-rules (steipete)** — アーカイブ済。Cursor用コーディングルールのみ。
- **agents.md** — フォーマット提案。中身もツールチェーンもなし。
- **ACP** — エージェント設定マネージャ。ガバナンスも自己進化もなし。
- **Cursor Directory** — コミュニティのルール断片集。マルチプラットフォーム同期なし。
- **AgentSeed** — 安全ルール＋6ペルソナ＋14プラットフォーム同期＋フック＋自己進化。CLI一つで全部。

---

## コントリビューション

[CONTRIBUTING.md](CONTRIBUTING.md) 参照。基本：ソース（`core/`、`personas/`、`capabilities/`）を編集 → `agentseed sync` → 生成ファイルは手編集しない。

テスト：`python -m pytest tests/`（171件パス）。

---

MIT
