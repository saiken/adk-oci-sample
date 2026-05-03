## Google ADK (Python) マルチエージェント・サンプル

このリポジトリには、Google の Agent Development Kit (ADK) を使ったマルチエージェント構成のサンプル（Python）を含みます。

### ディレクトリ構成と主な処理

```text
.
├── .env.example                 # 環境変数のサンプル（OpenAI / OCI 切り替え）
├── README.md
├── pyproject.toml               # 依存関係（google-adk / oci など）
├── uv.lock
├── agents/
│   ├── common/
│   │   ├── __init__.py
│   │   ├── model.py             # 全エージェント共通のモデル設定
│   │   └── oci_llm.py           # OCI Generative AI 用 LLM アダプタ（共通）
│   ├── orchestrator/
│   │   ├── __init__.py          # ADK エントリ
│   │   └── agent.py             # 全体オーケストレーション（分解→依頼→統合）
│   ├── oci_expert/
│   │   ├── __init__.py          # ADK エントリ
│   │   ├── agent.py             # OCI専門家（クエリ生成→検索→回答）
│   │   └── web_search.py        # Web検索ツール（DuckDuckGo HTML）
│   ├── system_dev_specialist/
│   │   ├── __init__.py          # ADK エントリ
│   │   └── agent.py             # システム開発エンジニア（設計/実装/運用）
└── .adk/                        # （任意）ローカル保存の session/artifacts（無効化可能）
```

主な処理内容:
- `agents/orchestrator/agent.py`：オーケストレーション（タスク分解→領域別実行→統合）で回答を生成します。
- `agents/oci_expert/agent.py`：OCI専門家（クエリ生成→検索→回答）を担当します。
- `agents/common/oci_llm.py`：OCI Generative AI Inference の `chat` API を呼び出す `OciGenerativeAiLlm`（全エージェント共通）を提供します。`.env` の `OCI_COMPARTMENT_ID` / `OCI_MODEL_ID` / `OCI_CHAT_API_FORMAT`（モデルがCohere系かどうか）などを参照します。
- `agents/oci_expert/web_search.py`：OCI専門家エージェントが利用する簡易Web検索（DuckDuckGo）を提供します。
- `agents/system_dev_specialist/agent.py`：システム開発（設計/実装/運用）の観点で回答します。
- `.env.example`：`ADK_DISABLE_LOCAL_STORAGE=1`（セッションを in-memory）を既定にしつつ、OpenAI/OCI の設定例を載せています。

### セットアップ

```bash
uv sync
```

APIキーを設定します（OpenAI または OCI Generative AI）。

```bash
cp .env.example .env
```

`.env` を編集して、`ADK_MODEL` と必要なキー/OCI設定を入れてください。デフォルトでは `ADK_DISABLE_LOCAL_STORAGE=1` により、セッションを in-memory で扱い（`.adk/session.db` を作りません）。

### 実行 (CLI)

```bash
uv run adk run agents/orchestrator
```

### 実行 (API / FastAPI)

`main.py` を起動すると `uvicorn` で FastAPI を立ち上げ、`POST /message` でオーケストレーターエージェントを実行できます。

```bash
uv run python main.py
```

```bash
curl -s -X POST http://127.0.0.1:8000/message \
  -H 'content-type: application/json' \
  -d '{"message":"こんにちは。OCI Generative AI の概要を教えて"}'
```

### 実行 (Web UI)

`adk web` は「エージェントディレクトリ群」を含む親ディレクトリから起動します。

```bash
uv run adk web agents
```

ブラウザで `http://localhost:8000` を開き、`orchestrator` を選択してチャットしてください。
