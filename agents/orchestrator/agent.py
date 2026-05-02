from pydantic import BaseModel

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent

from common.model import get_default_model, get_generate_content_config
from oci_expert.agent import root_agent as oci_root_agent
from system_dev_specialist.agent import root_agent as system_root_agent

MODEL = get_default_model()
GEN_CONFIG = get_generate_content_config()


class TaskBreakdown(BaseModel):
  oci_task: str
  system_task: str
  final_answer_style: str

task_router_agent = LlmAgent(
    name="OrchestratorRouter",
    model=MODEL,
    description="ユーザー依頼をサブタスクに分解して、領域別エージェントへ割り当てる。",
    generate_content_config=GEN_CONFIG,
    output_schema=TaskBreakdown,
    instruction=(
        "ユーザーの依頼を、次の2領域に分解してください:\n"
        "- oci_task: OCI/OCI Generative AI/SDK/IAM/運用に関する調査・回答タスク\n"
        "- system_task: システム開発（要件整理、設計、実装方針、運用）の観点の回答タスク\n\n"
        "出力は必ずJSONのみで、キーは oci_task / system_task / final_answer_style の3つです。\n"
        "final_answer_style には、回答のトーン/形式（例: 箇条書き、手順、表）を短く指定してください。"
    ),
    output_key="task_breakdown",
)

domain_parallel = ParallelAgent(
    name="DomainAgents",
    description="領域別エージェントを並列実行する。",
    sub_agents=[oci_root_agent, system_root_agent],
)

final_orchestrator_agent = LlmAgent(
    name="OrchestratorFinal",
    model=MODEL,
    description="領域別出力を統合して最終回答を生成する。",
    generate_content_config=GEN_CONFIG,
    instruction=(
        "タスク分解:\n{task_breakdown}\n\n"
        "OCI回答:\n{oci_answer}\n\n"
        "システム開発回答:\n{system_answer}\n\n"
        "final_answer_style を優先して、最終回答としてまとめてください。\n"
        "余計な前置きは不要です。"
    ),
)

root_agent = SequentialAgent(
    name="OrchestratorRoot",
    description="オーケストレーション → 領域別エージェント → 統合。",
    sub_agents=[task_router_agent, domain_parallel, final_orchestrator_agent],
)
