from google.adk.agents import LlmAgent

from common.model import get_default_model, get_generate_content_config

MODEL = get_default_model()
GEN_CONFIG = get_generate_content_config()

root_agent = LlmAgent(
    name="SystemDevSpecialist",
    model=MODEL,
    description="システム開発エンジニアの観点で実現方法を検討して回答する。",
    generate_content_config=GEN_CONFIG,
    instruction=(
        "タスク分解（テキスト）:\n{task_breakdown}\n\n"
        "上の内容から system_task を読み取り、設計・実装・運用の観点で具体的に回答してください。\n"
        "必要なら、簡単な手順/構成案/落とし穴も含めてください。\n"
        "日本語で。"
    ),
    output_key="system_answer",
)
