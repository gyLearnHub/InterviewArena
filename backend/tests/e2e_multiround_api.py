from __future__ import annotations

# ruff: noqa: E402,I001

import json
from collections import Counter
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import uvicorn

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.registry import ROUND_ORDER, ROUND_SPECS
from app.db.mysql import mysql_connection
from app.services import llm as llm_service
from main import create_app


ROUND_NAMES = {
    "resume": "简历面",
    "technical": "技术面",
    "manager": "主管面",
    "hr": "HR 面",
}


class DeterministicLLMClient:
    model_name = "codex-e2e-deterministic"

    def __init__(self) -> None:
        self.question_calls: list[dict[str, Any]] = []
        self.evaluation_calls: list[dict[str, Any]] = []

    def parse_resume(self, resume_text: str) -> dict[str, Any]:
        raise AssertionError("This E2E run must use the existing resume, not upload a new one.")

    def generate_question(
        self,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
        previous_answer: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        round_type = str(resume.get("_interview_round") or "unknown")
        main_count = sum(1 for item in qa_history if item.get("question_kind") == "main")
        follow_count = sum(1 for item in qa_history if item.get("question_kind") == "follow_up")
        last_kind = qa_history[-1].get("question_kind") if qa_history else None
        is_follow_up = previous_answer is not None and last_kind == "main"
        label = "追问" if is_follow_up else "主问题"
        index = follow_count + 1 if is_follow_up else main_count + 1
        question = (
            f"{ROUND_NAMES.get(round_type, round_type)}{label} {index}: "
            f"请结合目标岗位“{target_position}”说明一个具体证据。"
        )
        self.question_calls.append(
            {
                "round_type": round_type,
                "label": label,
                "history_size": len(qa_history),
                "previous_answer": previous_answer,
                "system_prompt": system_prompt,
            }
        )
        return {"question_type": f"{round_type}_{label}", "question": question}

    def generate_feedback(
        self,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {"score": 82, "weaknesses": ["需补充量化指标"], "suggestions": ["继续沉淀复盘材料"]}

    def generate_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        if "question_id" in user_payload:
            result = self._question_score(user_payload)
            call_type = "question"
        elif "qa_history" in user_payload:
            result = self._round_summary(user_payload)
            call_type = "round"
        elif "round_evaluations" in user_payload:
            result = self._final_report(user_payload)
            call_type = "final"
        else:
            raise AssertionError(f"Unknown evaluation payload: {user_payload.keys()}")
        self.evaluation_calls.append(
            {
                "type": call_type,
                "round_type": user_payload.get("round_type"),
                "round_id": user_payload.get("round_id"),
                "question_id": user_payload.get("question_id"),
                "payload": user_payload,
                "system_prompt": system_prompt,
            }
        )
        return result

    def _question_score(self, payload: dict[str, Any]) -> dict[str, Any]:
        dimensions = payload["dimensions"]
        question = str(payload["question"])
        should_follow_up = "主问题 1" in question
        return {
            "total_score": 82,
            "dimension_scores": [
                {"dimension": dimension, "score": 82, "reason": "回答包含岗位相关证据。"}
                for dimension in dimensions
            ],
            "strengths": ["回答结构完整，能结合项目经验说明。"],
            "issues": ["量化结果还可以更明确。"],
            "evidence": [payload["answer"][:80]],
            "should_follow_up": should_follow_up,
            "follow_up_direction": "请补充更具体的取舍和结果。" if should_follow_up else None,
        }

    def _round_summary(self, payload: dict[str, Any]) -> dict[str, Any]:
        dimensions = payload["dimensions"]
        return {
            "total_score": 82,
            "result": "passed",
            "dimension_scores": [
                {"dimension": dimension, "score": 82, "reason": "本轮回答证据充分。"}
                for dimension in dimensions
            ],
            "strengths": [f"{ROUND_NAMES[payload['round_type']]}能结合真实场景展开。"],
            "weaknesses": ["部分细节仍可继续量化。"],
            "suggestions": ["后续回答保持 STAR 结构并补充指标。"],
            "evidence": [
                item["question"]
                for item in payload["qa_history"]
                if item.get("answer")
            ][:4],
            "is_reference_only": bool(payload.get("is_reference_only")),
            "reference_note": None,
        }

    def _final_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "total_score": 82,
            "round_scores": [
                {
                    "round_type": item["round_type"],
                    "score": item.get("score"),
                    "result": item.get("result"),
                    "is_reference_only": bool(item.get("is_reference_only")),
                    "status": item.get("status"),
                }
                for item in payload["round_evaluations"]
            ],
            "ability_analysis": ["四轮均完成，表现稳定，能覆盖经历、技术、协作和动机。"],
            "job_match": "与后端开发岗位匹配度较高。",
            "core_strengths": ["项目理解清楚", "技术表达完整", "协作意识明确"],
            "main_risks": ["部分指标和业务影响还可进一步量化。"],
            "improvement_plan": ["补充关键项目的性能、成本和交付数据。"],
            "final_conclusion": "建议录用",
            "confidence": "high",
            "reference_note": None,
        }


def candidate_answer(round_type: str, question_kind: str, index: int) -> str:
    answers = {
        "resume": (
            "我在 InterviewArena 项目中主要负责多轮面试编排和评分链路。"
            "面对状态恢复、轮次切换和报告生成等需求，我先梳理领域模型，"
            "再把问题、回答、评分按 interview、round、question 三层关联，"
            "保证历史记录可追踪。"
        ),
        "technical": (
            "我的思路是先把核心流程建模为状态机，再用事务保证问题生成、回答保存和评分记录的一致性。"
            "实现上会把接口幂等性、外部模型失败降级和数据库唯一约束结合起来，避免重复评分或轮次错乱。"
        ),
        "manager": (
            "之前跨前后端推进报告页时，我会先对齐最小可交付目标，把接口字段、异常态和验收标准列清楚。"
            "遇到分歧时先用可运行 demo 统一认知，再分阶段补齐体验和边界，确保进度和质量都可控。"
        ),
        "hr": (
            "我希望继续在 AI 应用和后端工程方向深耕，岗位内容与我的项目经验比较匹配。"
            "我重视长期稳定地把复杂系统做扎实，也愿意在业务反馈中持续改进协作方式和交付质量。"
        ),
    }
    suffix = (
        "如果是追问，我会进一步补充具体取舍、结果指标和复盘结论。"
        if question_kind == "follow_up"
        else ""
    )
    return f"{answers[round_type]}{suffix}（第 {index} 次回答）"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_server(fake_llm: DeterministicLLMClient) -> tuple[uvicorn.Server, str]:
    app = create_app()

    def get_fake_llm() -> DeterministicLLMClient:
        return fake_llm

    app.dependency_overrides[llm_service.get_llm_client] = get_fake_llm

    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}/api"
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/health", timeout=1)
            if response.status_code == 200:
                return server, base_url
        except httpx.HTTPError:
            time.sleep(0.1)
    raise RuntimeError("API server did not become ready")


def api_request(
    client: httpx.Client,
    method: str,
    path: str,
    **kwargs: Any,
) -> httpx.Response:
    response = client.request(method, path, **kwargs)
    if response.status_code >= 400:
        raise AssertionError(
            f"{method} {path} failed: {response.status_code} {response.text}"
        )
    return response


def db_snapshot(interview_id: int) -> dict[str, Any]:
    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, status, overall_status, current_round, started_at, ended_at,
                       elapsed_seconds, question_count
                FROM interviews
                WHERE id = %s
                """,
                (interview_id,),
            )
            interview = cursor.fetchone()
            cursor.execute(
                """
                SELECT id, round_type, agent_type, status, score, result, summary,
                       started_at, ended_at
                FROM interview_rounds
                WHERE interview_id = %s
                ORDER BY FIELD(round_type, 'resume', 'technical', 'manager', 'hr')
                """,
                (interview_id,),
            )
            rounds = cursor.fetchall()
            cursor.execute(
                """
                SELECT id, interview_id, round_id, sequence, question_kind,
                       parent_question_id, question, answer
                FROM interview_qa
                WHERE interview_id = %s
                ORDER BY round_id, sequence
                """,
                (interview_id,),
            )
            qa = cursor.fetchall()
            cursor.execute(
                """
                SELECT id, evaluation_type, evaluation_key, interview_id, round_id,
                       question_id, status, total_score, model_name
                FROM evaluation_records
                WHERE interview_id = %s
                ORDER BY id
                """,
                (interview_id,),
            )
            evaluations = cursor.fetchall()
            cursor.execute(
                """
                SELECT interview_id, score, recommendation, confidence
                FROM feedback_reports
                WHERE interview_id = %s
                """,
                (interview_id,),
            )
            feedback_report = cursor.fetchone()
            cursor.execute(
                """
                SELECT question, COUNT(*) AS n
                FROM interview_qa
                WHERE interview_id = %s
                GROUP BY round_id, question
                HAVING COUNT(*) > 1
                """,
                (interview_id,),
            )
            duplicate_questions = cursor.fetchall()
            cursor.execute(
                """
                SELECT evaluation_type, evaluation_key, COUNT(*) AS n
                FROM evaluation_records
                WHERE interview_id = %s
                GROUP BY evaluation_type, evaluation_key
                HAVING COUNT(*) > 1
                """,
                (interview_id,),
            )
            duplicate_evaluations = cursor.fetchall()
    return {
        "interview": interview,
        "rounds": rounds,
        "qa": qa,
        "evaluations": evaluations,
        "feedback_report": feedback_report,
        "duplicate_questions": duplicate_questions,
        "duplicate_evaluations": duplicate_evaluations,
    }


def summarize_db_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    qa = snapshot["qa"]
    evaluations = snapshot["evaluations"]
    return {
        "interview": snapshot["interview"],
        "rounds": [
            {
                "id": item["id"],
                "round_type": item["round_type"],
                "agent_type": item["agent_type"],
                "status": item["status"],
                "score": item["score"],
                "result": item["result"],
                "summary_generated": bool(item["summary"]),
                "started_at": item["started_at"],
                "ended_at": item["ended_at"],
            }
            for item in snapshot["rounds"]
        ],
        "qa_counts": {
            round_type: {
                "main": sum(
                    1
                    for item in qa
                    if item["round_id"] == round_id and item["question_kind"] == "main"
                ),
                "follow_up": sum(
                    1
                    for item in qa
                    if item["round_id"] == round_id and item["question_kind"] == "follow_up"
                ),
                "answered": sum(
                    1 for item in qa if item["round_id"] == round_id and item["answer"]
                ),
            }
            for round_id, round_type in [
                (item["id"], item["round_type"]) for item in snapshot["rounds"]
            ]
        },
        "evaluation_counts": dict(Counter(item["evaluation_type"] for item in evaluations)),
        "all_evaluations_succeeded": all(
            item["status"] == "succeeded" for item in evaluations
        ),
        "feedback_report": snapshot["feedback_report"],
        "duplicate_questions": snapshot["duplicate_questions"],
        "duplicate_evaluations": snapshot["duplicate_evaluations"],
    }


def summarize_agent_calls(fake_llm: DeterministicLLMClient) -> dict[str, Any]:
    question_counts = Counter(item["round_type"] for item in fake_llm.question_calls)
    evaluation_counts = Counter(item["type"] for item in fake_llm.evaluation_calls)
    prompt_matches = {
        round_type: all(
            item["system_prompt"] == ROUND_SPECS[round_type].system_prompt
            for item in fake_llm.question_calls
            if item["round_type"] == round_type
        )
        for round_type in ROUND_ORDER
    }
    return {
        "question_counts_by_round": dict(question_counts),
        "evaluation_counts_by_type": dict(evaluation_counts),
        "independent_round_prompts": len(
            {ROUND_SPECS[round_type].system_prompt for round_type in ROUND_ORDER}
        )
        == 4,
        "prompt_matches": prompt_matches,
        "evaluation_round_types": [
            {
                "type": item["type"],
                "round_type": item.get("round_type"),
                "round_id": item.get("round_id"),
                "question_id": item.get("question_id"),
            }
            for item in fake_llm.evaluation_calls
        ],
    }


def validate_report(report: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for round_type in ROUND_ORDER:
        item = report["rounds"].get(round_type)
        if item is None:
            failures.append(f"{round_type}: round missing")
            continue
        if item["status_changes"] != ["pending", "in_progress", "completed"]:
            failures.append(f"{round_type}: invalid status changes {item['status_changes']}")
        if item["main_answered"] != 2:
            failures.append(f"{round_type}: expected 2 answered main questions")
        if not item["summary_generated"]:
            failures.append(f"{round_type}: round summary missing")
        if item["pre_finish_scores_visible"]:
            failures.append(f"{round_type}: question score visible before finish")
        if not item["post_finish_scores_visible"]:
            failures.append(f"{round_type}: question score missing after finish")
        if not item["stop_after_finish_verified"]:
            failures.append(f"{round_type}: round still allows questions after finish")
        if not item["refresh_recovered"]:
            failures.append(f"{round_type}: state endpoint did not recover progress")

    database = report["database"]
    if database["interview"]["overall_status"] != "finished":
        failures.append("interview: overall_status is not finished")
    if database["interview"]["current_round"] is not None:
        failures.append("interview: current_round was not cleared after finish")
    if database["duplicate_questions"]:
        failures.append("database: duplicate questions found")
    if database["duplicate_evaluations"]:
        failures.append("database: duplicate evaluations found")
    if not database["all_evaluations_succeeded"]:
        failures.append("database: not all evaluations succeeded")
    if not database["feedback_report"]:
        failures.append("database: feedback report missing")

    agent_calls = report["agent_calls"]
    if not agent_calls["independent_round_prompts"]:
        failures.append("agents: round prompts are not independent")
    for round_type, matched in agent_calls["prompt_matches"].items():
        if not matched:
            failures.append(f"agents: prompt mismatch for {round_type}")
    if agent_calls["evaluation_counts_by_type"] != {"question": 12, "round": 4, "final": 1}:
        failures.append("agents: unexpected evaluation call counts")
    return failures


def main() -> None:
    fake_llm = DeterministicLLMClient()
    server, base_url = start_server(fake_llm)
    username = "gy"
    password = "123456"
    report: dict[str, Any] = {
        "environment": {
            "base_url": base_url,
            "python": sys.version.split()[0],
            "database": "MySQL via backend/.env",
            "llm_model": fake_llm.model_name,
        },
        "rounds": {},
        "errors": [],
    }

    try:
        with httpx.Client(base_url=base_url, timeout=30) as client:
            api_request(
                client,
                "POST",
                "/auth/login",
                json={"username": username, "password": password},
            )
            headers: dict[str, str] = {}
            resumes = api_request(client, "GET", "/resumes", headers=headers).json()
            if not resumes:
                raise AssertionError("No existing resume found for user gy.")
            resume_id = resumes[0]["id"]
            create_payload = {
                "resume_id": resume_id,
                "target_position": "后端开发工程师",
                "job_description": "负责 FastAPI、MySQL、Vue 与多 Agent 面试系统的设计开发。",
                "selected_rounds": ROUND_ORDER,
            }
            interview = api_request(
                client,
                "POST",
                "/interviews",
                headers=headers,
                json=create_payload,
            ).json()
            interview_id = interview["id"]
            report["interview_id"] = interview_id
            report["created_rounds"] = interview["rounds"]

            for round_info in interview["rounds"]:
                round_type = round_info["round_type"]
                if round_type not in ROUND_ORDER:
                    continue
                round_id = round_info["id"]
                round_report = {
                    "round_id": round_id,
                    "status_changes": ["pending"],
                    "questions": [],
                    "main_answered": 0,
                    "follow_up_answered": 0,
                    "pre_finish_scores_visible": False,
                    "post_finish_scores_visible": False,
                    "summary_generated": False,
                    "stop_after_finish_verified": False,
                    "refresh_recovered": False,
                }
                start_response = api_request(
                    client,
                    "POST",
                    f"/interviews/{interview_id}/rounds/{round_id}/start",
                    headers=headers,
                ).json()
                round_report["status_changes"].append("in_progress")
                question = start_response["question"]
                while round_report["main_answered"] < 2:
                    if question is None:
                        raise AssertionError(f"{round_type} did not return a question")
                    kind = question["question_kind"]
                    if kind == "main" and round_report["main_answered"] >= 2:
                        break
                    index = round_report["main_answered"] + round_report["follow_up_answered"] + 1
                    answer = candidate_answer(round_type, kind, index)
                    response = api_request(
                        client,
                        "POST",
                        f"/interviews/{interview_id}/rounds/{round_id}/answers",
                        headers=headers,
                        json={"question_id": question["id"], "answer": answer},
                    ).json()
                    round_report["questions"].append(question)
                    if kind == "main":
                        round_report["main_answered"] += 1
                    elif kind == "follow_up":
                        round_report["follow_up_answered"] += 1

                    state = api_request(
                        client,
                        "GET",
                        f"/interviews/{interview_id}/state",
                        headers=headers,
                    ).json()
                    round_report["refresh_recovered"] = state["current_round"] == round_type
                    visible_scores = [
                        item
                        for item in state["qa_history"]
                        if item.get("round_id") == round_id and "question_evaluation" in item
                    ]
                    if visible_scores:
                        round_report["pre_finish_scores_visible"] = True
                    question = response.get("question")
                    if (
                        question is not None
                        and question["question_kind"] == "main"
                        and round_report["main_answered"] >= 2
                    ):
                        break

                finish = api_request(
                    client,
                    "POST",
                    f"/interviews/{interview_id}/rounds/{round_id}/finish",
                    headers=headers,
                    json={"finish_type": "normal"},
                ).json()
                state_after_finish = api_request(
                    client,
                    "GET",
                    f"/interviews/{interview_id}/state",
                    headers=headers,
                ).json()
                completed_round = next(
                    item for item in state_after_finish["rounds"] if item["id"] == round_id
                )
                round_report["status_changes"].append(completed_round["status"])
                round_report["summary_generated"] = bool(finish.get("round_summary")) and bool(
                    completed_round.get("summary")
                )
                round_report["post_finish_scores_visible"] = any(
                    item.get("round_id") == round_id and "question_evaluation" in item
                    for item in state_after_finish["qa_history"]
                )
                bad_start = client.post(
                    f"/interviews/{interview_id}/rounds/{round_id}/start",
                    headers=headers,
                )
                round_report["stop_after_finish_verified"] = bad_start.status_code >= 400
                report["rounds"][round_type] = round_report

            final_report = api_request(
                client,
                "POST",
                f"/interviews/{interview_id}/finish",
                headers=headers,
                json={"finish_type": "normal"},
            ).json()
            final_state = api_request(
                client,
                "GET",
                f"/interviews/{interview_id}/state",
                headers=headers,
            ).json()
            report["final_report"] = final_report
            report["final_state"] = {
                "overall_status": final_state["overall_status"],
                "current_round": final_state["current_round"],
                "rounds": [
                    {
                        "id": item["id"],
                        "round_type": item["round_type"],
                        "status": item["status"],
                        "score": item["score"],
                        "summary_generated": bool(item["summary"]),
                    }
                    for item in final_state["rounds"]
                ],
            }
            snapshot = db_snapshot(interview_id)
            report["database"] = summarize_db_snapshot(snapshot)
            report["agent_calls"] = summarize_agent_calls(fake_llm)
            failures = validate_report(report)
            report["validation_failures"] = failures
            if failures:
                raise AssertionError("; ".join(failures))
    except Exception as exc:
        report["errors"].append(str(exc))
        raise
    finally:
        server.should_exit = True
        print(json.dumps(report, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
