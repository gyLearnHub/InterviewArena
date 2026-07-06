from typing import Any

from app.agents import ROUND_ORDER, ROUND_SPECS, get_round_agent


class CapturingLLMClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate_question(
        self,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
        previous_answer: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "resume": resume,
                "target_position": target_position,
                "qa_history": qa_history,
                "previous_answer": previous_answer,
                "system_prompt": system_prompt,
            }
        )
        return {"question_type": "captured", "question": "请说明一个相关案例。"}


class ProjectFirstLLMClient(CapturingLLMClient):
    def generate_question(
        self,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
        previous_answer: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        super().generate_question(
            resume=resume,
            target_position=target_position,
            qa_history=qa_history,
            previous_answer=previous_answer,
            system_prompt=system_prompt,
        )
        return {"question_type": "project_deep_dive", "question": "请详细说说你第一个项目。"}


def test_round_agents_pass_independent_system_prompts() -> None:
    llm_client = CapturingLLMClient()

    for round_type in ROUND_ORDER:
        agent = get_round_agent(round_type, llm_client)
        agent.generate_question(
            resume={"skills": ["Python"]},
            target_position="后端开发",
            qa_history=[],
            previous_answer=None,
        )

    prompts = [call["system_prompt"] for call in llm_client.calls]
    assert prompts == [ROUND_SPECS[round_type].system_prompt for round_type in ROUND_ORDER]
    assert len(set(prompts)) == 4


def test_round_system_prompts_cover_required_sections() -> None:
    required_sections = [
        "角色定位",
        "面试目标",
        "提问范围",
        "追问策略",
        "语言风格",
        "评分维度",
        "结束条件",
    ]

    for spec in ROUND_SPECS.values():
        assert all(section in spec.system_prompt for section in required_sections)
        assert "只返回 JSON" in spec.system_prompt
        assert "不得" in spec.system_prompt


def test_round_specs_keep_technical_follow_up_space() -> None:
    expected_min_total = {"resume": 20, "technical": 20, "manager": 20, "hr": 15}
    for round_type, spec in ROUND_SPECS.items():
        assert spec.min_main_questions == 1
        assert spec.max_main_questions == 40
        assert spec.min_total_questions == expected_min_total[round_type]
        assert spec.max_total_questions == 40


def test_round_prompts_include_cross_topic_strategy() -> None:
    required_rules = [
        "主问题和追问都计入总题数",
        "交叉式",
        "单个主题连续追问原则上不超过 2 次",
        "不得重复",
        "_question_strategy",
    ]

    for spec in ROUND_SPECS.values():
        assert all(rule in spec.system_prompt for rule in required_rules)
    assert "20～40" in ROUND_SPECS["resume"].system_prompt
    assert "20～40" in ROUND_SPECS["technical"].system_prompt
    assert "20～40" in ROUND_SPECS["manager"].system_prompt
    assert "15～40" in ROUND_SPECS["hr"].system_prompt

    technical_prompt = ROUND_SPECS["technical"].system_prompt
    for topic in [
        "计算机基础",
        "语言与框架",
        "数据库",
        "操作系统",
        "计算机网络",
        "算法",
        "系统设计",
        "Agent 基础",
        "RAG",
        "LLM 应用开发",
    ]:
        assert topic in technical_prompt


def test_agent_injects_question_strategy_context() -> None:
    llm_client = CapturingLLMClient()
    agent = get_round_agent("technical", llm_client)

    agent.generate_question(
        resume={"skills": ["Python"]},
        target_position="Agent 工程师",
        qa_history=[
            {
                "question_type": "cs_fundamentals",
                "question": "请说明进程和线程的区别。",
                "question_kind": "main",
            }
        ],
        previous_answer=None,
        question_kind="main",
    )

    strategy = llm_client.calls[0]["resume"]["_question_strategy"]
    assert strategy["min_total_questions"] == 20
    assert strategy["max_total_questions"] == 40
    assert "计算机基础" in strategy["covered_core_topics"]
    assert "数据库" in strategy["uncovered_core_topics"]


def test_technical_agent_replaces_initial_project_deep_dive() -> None:
    agent = get_round_agent("technical", ProjectFirstLLMClient())

    question = agent.generate_question(
        resume={"skills": ["Python"]},
        target_position="Agent 工程师",
        qa_history=[],
        previous_answer=None,
        question_kind="main",
    )

    assert question.question_type == "cs_fundamentals"
    assert "计算机基础" in question.question
