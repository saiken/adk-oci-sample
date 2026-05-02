## Google ADK (Python) マルチエージェント・サンプル

このリポジトリには、Google の Agent Development Kit (ADK) を使ったマルチエージェント構成のサンプル（Python）を含みます。

### セットアップ

```bash
uv sync
```

APIキーを設定します（OpenAI API）。

```bash
cp .env.example .env
```

`.env` の `OPENAI_API_KEY` を自分のキーに置き換えてください。デフォルトでは `ADK_DISABLE_LOCAL_STORAGE=1` により、セッションを in-memory で扱い（`.adk/session.db` を作りません）。

### 実行 (CLI)

```bash
uv run adk run agents/multi_agent_sample
```

### 実行 (Web UI)

`adk web` は「エージェントディレクトリ群」を含む親ディレクトリから起動します。

```bash
uv run adk web agents --port 8000
```

ブラウザで `http://localhost:8000` を開き、`multi_agent_sample` を選択してチャットしてください。
