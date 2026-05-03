import os

from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.tools.function_tool import FunctionTool

from agents.common.model import get_default_model, get_generate_content_config
from .web_search import web_search_duckduckgo

MODEL = get_default_model()
GEN_CONFIG = get_generate_content_config()


oci_query_agent = LlmAgent(
    name="OciQueryPlanner",
    model=MODEL,
    description="OCI領域タスクからWeb検索用クエリーを生成する。",
    generate_content_config=GEN_CONFIG,
    instruction=(
        "タスク分解（テキスト）:\n{task_breakdown}\n\n"
        "上の内容から、OCI領域(oci_task) を満たすために必要なWeb検索クエリーを3〜6個作り、JSON配列のみで出力してください。\n"
        '例: ["query1", "query2"]\n'
        "日本語/英語は適切に混ぜてください。"
    ),
    output_key="oci_search_queries",
)

oci_web_search_agent = LlmAgent(
    name="OciWebSearcher",
    model=MODEL,
    description="Web検索を実行し、結果を要点として整理する。",
    tools=[FunctionTool(web_search_duckduckgo)],
    generate_content_config=GEN_CONFIG,
    instruction=(
        "検索クエリー一覧:\n{oci_search_queries}\n\n"
        "各クエリーについて tool を使って検索し、上位結果（title/url/snippet）を収集してください。\n"
        "最後に、URL付きで要点を箇条書きで要約してください。\n"
        "出力はMarkdownで、必ず参照URLを含めてください。"
    ),
    output_key="oci_search_notes",
)

oci_expert_agent = LlmAgent(
    name="OciExpert",
    model=MODEL,
    description="検索結果を根拠にOCI領域の回答を生成する。",
    generate_content_config=GEN_CONFIG,
    instruction=(
        "タスク分解（テキスト）:\n{task_breakdown}\n\n"
        "検索メモ:\n{oci_search_notes}\n\n"
        "上記を根拠として、oci_task に答えてください（タスク分解テキストのOCI領域の記述を優先）。\n"
        "不確実な点は断定せず、追加で確認すべき観点も短く添えてください。\n"
        "出力は日本語で。"
    ),
    output_key="oci_answer",
)

root_agent = SequentialAgent(
    name="OciExpertRoot",
    description="OCI領域: クエリー生成 → Web検索 → 回答生成。",
    sub_agents=[oci_query_agent, oci_web_search_agent, oci_expert_agent],
)
