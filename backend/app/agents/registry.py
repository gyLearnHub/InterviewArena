from __future__ import annotations

from app.agents.base import BaseRoundAgent
from app.agents.hr import HRInterviewAgent
from app.agents.manager import ManagerInterviewAgent
from app.agents.resume import ResumeInterviewAgent
from app.agents.technical import TechnicalInterviewAgent
from app.agents.types import RoundLLMClient, RoundSpec
from app.prompts.loader import load_prompt

ROUND_ORDER = ["resume", "technical", "manager", "hr"]

ROUND_SPECS: dict[str, RoundSpec] = {
    "resume": RoundSpec(
        round_type="resume",
        agent_type="ResumeInterviewAgent",
        system_prompt=load_prompt("resume_interviewer.md"),
        min_main_questions=1,
        max_main_questions=40,
        min_total_questions=0,
        max_total_questions=40,
        dimensions=["经历真实性", "项目理解深度", "个人贡献度", "岗位匹配度", "表达清晰度"],
        core_topics={
            "经历真实性": ["authenticity", "timeline", "education", "work_history"],
            "项目理解深度": ["project_understanding", "project_context", "project_result"],
            "个人贡献度": ["contribution", "ownership", "responsibility"],
            "岗位匹配度": ["job_match", "position_fit", "skill_match"],
            "表达清晰度": ["communication", "clarity", "structured_answer"],
        },
    ),
    "technical": RoundSpec(
        round_type="technical",
        agent_type="TechnicalInterviewAgent",
        system_prompt=load_prompt("technical_interviewer.md"),
        min_main_questions=1,
        max_main_questions=40,
        min_total_questions=0,
        max_total_questions=40,
        dimensions=[
            "基础知识掌握",
            "技术原理理解",
            "问题分析能力",
            "系统设计能力",
            "工程实践能力",
            "追问应对能力",
        ],
        core_topics={
            "计算机基础": ["cs_fundamentals", "computer_fundamentals", "data_structure"],
            "语言与框架": ["language_framework", "framework", "runtime", "python", "java"],
            "数据库": ["database", "sql", "mysql", "transaction", "index"],
            "操作系统": ["operating_system", "os", "process", "thread", "memory"],
            "计算机网络": ["network", "tcp", "http", "protocol"],
            "算法": ["algorithm", "complexity", "coding"],
            "系统设计": ["system_design", "architecture", "scalability"],
            "Agent 基础": ["agent_basics", "agent", "tool_calling", "planning"],
            "RAG": ["rag", "retrieval", "embedding", "vector"],
            "LLM 应用开发": ["llm_application", "llm_app", "prompt", "evaluation"],
        },
    ),
    "manager": RoundSpec(
        round_type="manager",
        agent_type="ManagerInterviewAgent",
        system_prompt=load_prompt("manager_interviewer.md"),
        min_main_questions=1,
        max_main_questions=40,
        min_total_questions=0,
        max_total_questions=40,
        dimensions=[
            "业务理解能力",
            "目标与结果意识",
            "执行推动能力",
            "沟通协作能力",
            "抗压与责任意识",
            "复盘成长能力",
        ],
        core_topics={
            "业务理解能力": ["business_understanding", "business_impact", "user_value"],
            "目标与结果意识": ["goal_result", "metrics", "outcome"],
            "执行推动能力": ["execution", "ownership", "delivery"],
            "沟通协作能力": ["collaboration", "communication", "conflict"],
            "抗压与责任意识": ["pressure", "responsibility", "risk"],
            "复盘成长能力": ["reflection", "growth", "lesson_learned"],
        },
    ),
    "hr": RoundSpec(
        round_type="hr",
        agent_type="HRInterviewAgent",
        system_prompt=load_prompt("hr_interviewer.md"),
        min_main_questions=1,
        max_main_questions=40,
        min_total_questions=0,
        max_total_questions=40,
        dimensions=[
            "职业动机",
            "稳定性",
            "价值观匹配",
            "沟通表达与礼仪",
            "职业规划",
            "薪资与入职意愿",
        ],
        core_topics={
            "职业动机": ["motivation", "job_motivation", "career_choice"],
            "稳定性": ["stability", "leaving_reason", "retention_risk"],
            "价值观匹配": ["values_fit", "culture_fit", "work_preference"],
            "沟通表达与礼仪": ["communication", "professionalism", "etiquette"],
            "职业规划": ["career_plan", "growth_plan", "long_term_goal"],
            "薪资与入职意愿": ["compensation", "offer_intention", "onboarding"],
        },
    ),
}


def get_round_agent(
    round_type: str,
    llm_client: RoundLLMClient,
    *,
    spec: RoundSpec | None = None,
) -> BaseRoundAgent:
    if spec is not None:
        if spec.round_type != round_type:
            raise ValueError("round spec does not match round type")
        return BaseRoundAgent(spec, llm_client)
    if round_type == "resume":
        return ResumeInterviewAgent(llm_client)
    if round_type == "technical":
        return TechnicalInterviewAgent(llm_client)
    if round_type == "manager":
        return ManagerInterviewAgent(llm_client)
    if round_type == "hr":
        return HRInterviewAgent(llm_client)
    raise KeyError(round_type)
