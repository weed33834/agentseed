# ベンダーソリューション — 幻覚防止技術と導入状況

> 主要ベンダー・学界・MCP エコシステムの幻覚防止技術マップ、および AgentSeed
> における各技術の導入先。
>
> 凡例：✅ 導入済み（プロンプト/ルール）· 🛠 AgentSeed MCP ツールとして実装済み
> · ➡️ 将来リリースで推奨 · 📄 リファレンスとして文書化済み。

## 1. 導入マトリクス

| 技術 | 提供元 | 仕組み | AgentSeed 内 |
| --- | --- | --- | --- |
| 「分からない」と言わせる | Anthropic / OpenAI | 不確実さを認めさせる | ✅ プロンプトプール D1/D2 |
| 直接引用グラウンディング | Anthropic | 推論前に引用文を抽出 | ✅ プロンプトプール C1/G1 |
| 引用検証 | Anthropic | 主張→裏付け引用、無ければ撤回 | ✅ プロンプトプール G1-J1 |
| 思考連鎖検証 | Anthropic / 学界 | 独立した批判的推論パス | ✅ プロンプトプール A2 |
| Best-of-N / 自己整合性 | Anthropic / 学界 | N 回実行して出力を比較 | ✅ プロンプトプール J3/J4 |
| 反復精錬 | Anthropic | 出力を再検証にフィードバック | ✅ プロンプトプール J3/J4 |
| 外部知識の制限 | Anthropic | 提供文書のみ、一般知識は使わない | ✅ プロンプトプール I2 |
| グラウンディング / RAG | Google / Microsoft / Progress | 回答を検索ソースに固定 | ✅ プロンプトプール I2 |
| 指示階層 | OpenAI | 衝突時 system > user > model | 📄 推奨 |
| 構造化出力（JSON Schema） | OpenAI / Guardrails AI | 信頼前にスキーマ検証 | 🛠 `schema_validate` |
| 入出力ガードレール | OpenAI Agents SDK | 違反でパイプライン停止 | ✅ 4 ゲート SKILL |
| 決定的実行 | CDV / サンドボックス実行 | テストを実行し結果を観察 | 🛠 `sandbox_run` |
| 二重チャネル min 融合 | CDV | 決定的 + LLM 批判者、拒否権 | ✅ SKILL ゲート 3/4 |
| 静的 AST 解析 | Axivion / tree-sitter MCP | 未定義シンボル = 捏造 API | 🛠 `verify_code` |
| NeMo 五種レール | NVIDIA NeMo Guardrails | 入力/対話/検索/実行/出力 | ✅ 4 ゲートにマップ |
| Automated Reasoning 検査 | AWS Bedrock | ポリシーの数学的検証 | 📄 推奨 |
| Granite Guardian リスク判定 | IBM | 幻覚/有害を検出するガードレールモデル | 📄 推奨 |
| バリデータハブ（50+） | Guardrails AI | プラグイン式バリデータ | ✅ プロンプトプール（サブセット） |
| 幻覚評価モデル | Vectara HHEM | 要約の無根拠コンテンツを検出 | 📄 推奨 |
| SelfCheckGPT / FActScore | 学界 | サンプリング比較 / 事実固定チェック | 📄 推奨 |
| 制約付きデコーディング | 学界（outlines） | 文法制約付き生成 | ➡️ ロードマップ（TS/Go） |
| 幻覚パターン分類法 | arXiv:2404.00971 | コード幻覚 5 分類カタログ | ✅ 幻覚パターンライブラリ |

## 2. ツール機能一覧

| 新機能 | 種類 | 導入した技術 |
| --- | --- | --- |
| `sandbox_run` | MCP ツール | 決定的実行チャネル（CDV チャネル A / Anthropic 実行検証 / AWS 推論検証の精神） |
| `schema_validate` | MCP ツール | 構造化出力検証（OpenAI 構造化出力 / Guardrails AI / OWASP LLM09） |
| Best-of-N + 反復精錬 | プロンプトプール | Anthropic 高度技術 J3/J4 |
| VENDOR-SOLUTIONS | リファレンス文書 | 完全な導入マップ（本ファイル） |

## 3. 次回推奨（将来リリース）

1. **制約付きデコーディング / 文法** — `schema_validate` のスキーマを生成側に
   接続し（outlines 方式）、モデルが適合 JSON のみを生成するようにする。
2. **HHEM 型ファクトチェッカー** — 幻覚評価モデルをラップした任意のリモート MCP
   サーバーを長文要約向けに提供。
3. **サンドボックス隔離強化** — `sandbox_run` へのリソース上限
   （メモリ/ネットワーク/FS）追加（Docker/gVisor バックエンド）。
4. **TypeScript/Go 静的解析** — tree-sitter ベースの `verify_code` で非 Python
   プロジェクトをカバー（現在は Python のみ）。

## 4. コンプライアンス維持の理由

上記はすべて Agent Plugins 1.0.0（§6/§7）が定義する `skills/` + `mcp.json` の
パッケージ構造内に収まります。この仕様はプラグインの**パッケージ方法と検出方法**
のみを定め、skill が**何を教えるか**、MCP サーバーが**どのツールを公開するか**は
制限しません。新ツールはすべて純標準ライブラリ Python（依存ゼロ）のため、クライアント
側のインストールは不要です。
