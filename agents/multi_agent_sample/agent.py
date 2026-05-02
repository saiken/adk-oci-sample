import os

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent

# LiteLLM model string (OpenAI). You can override via ADK_MODEL if needed.
# Examples:
# - openai/gpt-5.2
# - openai/gpt-5.2-codex
DEFAULT_MODEL = os.getenv("ADK_MODEL", "openai/gpt-5.2")


requirements_agent = LlmAgent(
    name="RequirementsAgent",
    model=DEFAULT_MODEL,
    description="ユーザーの依頼を要件に分解して整理する。",
    instruction=(
        "ユーザーの依頼を、実装・入出力・制約・前提の観点で短く整理してください。\n"
        "必ず日本語で、箇条書きで出力してください。"
    ),
    output_key="requirements",
)

research_agent = LlmAgent(
    name="ResearchAgent",
    model=DEFAULT_MODEL,
    description="要件を満たすための設計案や構成案を洗い出す。",
    instruction=(
        "要件: {requirements}\n\n"
        "上記を満たすためのアーキテクチャ案（エージェント分割、責務、状態共有の方法）を提案してください。\n"
        "実装のための具体的な構成（ファイル構成案、主要クラス/関数、実行方法）も含めてください。"
    ),
    output_key="design_notes",
)

risk_agent = LlmAgent(
    name="RiskAgent",
    model=DEFAULT_MODEL,
    description="実装時の落とし穴・セキュリティ/運用上の注意点を洗い出す。",
    instruction=(
        "要件: {requirements}\n\n"
        "このサンプルを実装・運用する上での注意点（APIキー管理、プロンプト注入、ログ/PII、レート制限、"
        "エラーハンドリング）を短く列挙してください。"
    ),
    output_key="risk_notes",
)

analysis_parallel = ParallelAgent(
    name="ParallelAnalysis",
    description="設計案とリスクを並列に整理する。",
    sub_agents=[research_agent, risk_agent],
)

draft_agent = LlmAgent(
    name="DraftAgent",
    model=DEFAULT_MODEL,
    description="最終回答のドラフトを作成する。",
    instruction=(
        "要件:\n{requirements}\n\n"
        "設計メモ:\n{design_notes}\n\n"
        "注意点:\n{risk_notes}\n\n"
        "上記を踏まえて、Google ADK(Python)で動くマルチエージェントのサンプルアプリを提示してください。\n"
        "必ず次を含めてください:\n"
        "- エージェント構成（Sequential/Parallelの使い分け）\n"
        "- `agents/<project>/agent.py` のコード\n"
        "- `agents/<project>/__init__.py` の内容\n"
        "- 実行手順（`adk run` / `adk web`）\n"
        "出力はMarkdownで、コードはコードブロックで示してください。"
    ),
    output_key="draft",
)

critic_agent = LlmAgent(
    name="CriticAgent",
    model=DEFAULT_MODEL,
    description="ドラフトの不足や誤りをレビューする。",
    instruction=(
        "次のドラフトをレビューしてください:\n\n{draft}\n\n"
        "観点:\n"
        "- ADKの用語/APIの妥当性（LlmAgent/ParallelAgent/SequentialAgent, root_agent など）\n"
        "- 実行手順の再現性\n"
        "- 説明の過不足\n\n"
        "修正提案を箇条書きで出してください。"
    ),
    output_key="review_comments",
)

final_agent = LlmAgent(
    name="FinalAgent",
    model=DEFAULT_MODEL,
    description="レビューを反映して最終回答を生成する。",
    instruction=(
        "ドラフト:\n{draft}\n\n"
        "レビューコメント:\n{review_comments}\n\n"
        "レビューを反映し、最終回答として整形して出力してください。\n"
        "余計な前置きは不要です。"
    ),
)

root_agent = SequentialAgent(
    name="MultiAgentSampleRoot",
    description="要件整理 → 並列分析 → ドラフト → レビュー → 仕上げ、のマルチエージェント構成。",
    sub_agents=[
        requirements_agent,
        analysis_parallel,
        draft_agent,
        critic_agent,
        final_agent,
    ],
)
