from datetime import datetime

import pytest
from app.core.errors import AppError, ErrorCode
from app.repositories.history import (
    FeedbackReportRecord,
    HistoryInterviewRecord,
    HistoryQARecord,
    HistoryRoundRecord,
    ReportListRecord,
    ResumeSummaryRecord,
)
from app.repositories.users import UserRecord
from app.services.history import HistoryService
from app.services.short_term_memory_store import ShortTermMemoryStoreError

DEFAULT_FEEDBACK_REPORT = FeedbackReportRecord(
    score=88,
    weaknesses=["项目细节不足"],
    suggestions=["补充量化结果"],
    report_reliability_status="reference_only",
)


class FakeHistoryRepository:
    def __init__(self, records: list[HistoryInterviewRecord]) -> None:
        self.records = records
        self.get_by_id_calls = 0
        self.get_by_id_for_user_calls = 0
        self.delete_by_id_for_user_calls = 0

    def list_by_user(self, user_id: int) -> list[HistoryInterviewRecord]:
        return self._list_interviews(user_id)

    def list_interviews_by_user(
        self,
        user_id: int,
        *,
        limit: int | None = None,
        offset: int = 0,
        query: str = "",
        status_filter: str | None = None,
    ) -> list[HistoryInterviewRecord]:
        records = self._list_interviews(user_id)
        keyword = query.strip().lower()
        if keyword:
            records = [
                record
                for record in records
                if keyword in record.target_position.lower() or keyword == str(record.id)
            ]
        if status_filter:
            records = [record for record in records if record.overall_status == status_filter]
        return records[offset:] if limit is None else records[offset : offset + limit]

    def _list_interviews(self, user_id: int) -> list[HistoryInterviewRecord]:
        filtered = [record for record in self.records if record.user_id == user_id]
        return sorted(
            filtered,
            key=lambda record: (record.started_at or record.created_at, record.id),
            reverse=True,
        )

    def list_reports_by_user(
        self,
        user_id: int,
        *,
        limit: int | None = None,
        offset: int = 0,
        query: str = "",
        score_filter: str | None = None,
        sort: str = "recent",
    ) -> list[ReportListRecord]:
        records = [
            ReportListRecord(
                interview_id=record.id,
                user_id=record.user_id,
                target_position=record.target_position,
                score=record.feedback_report.score,
                report_reliability_status=record.feedback_report.report_reliability_status,
                used_candidate_memory=record.feedback_report.used_candidate_memory,
                created_at=record.feedback_report.created_at,
            )
            for record in self.records
            if record.user_id == user_id and record.feedback_report is not None
        ]
        keyword = query.strip().lower()
        if keyword:
            records = [
                record
                for record in records
                if keyword in record.target_position.lower() or keyword == str(record.interview_id)
            ]
        if score_filter == "high":
            records = [record for record in records if record.score >= 80]
        elif score_filter == "middle":
            records = [record for record in records if 60 <= record.score < 80]
        if sort == "score-desc":
            records.sort(key=lambda record: (record.score, record.interview_id), reverse=True)
        elif sort == "score-asc":
            records.sort(key=lambda record: (record.score, -record.interview_id))
        else:
            records.sort(
                key=lambda record: (record.created_at or datetime.min, record.interview_id),
                reverse=True,
            )
        return records[offset:] if limit is None else records[offset : offset + limit]

    def get_by_id(self, interview_id: int) -> HistoryInterviewRecord | None:
        self.get_by_id_calls += 1
        return next((record for record in self.records if record.id == interview_id), None)

    def get_by_id_for_user(
        self,
        interview_id: int,
        user_id: int,
    ) -> HistoryInterviewRecord | None:
        self.get_by_id_for_user_calls += 1
        return next(
            (
                record
                for record in self.records
                if record.id == interview_id and record.user_id == user_id
            ),
            None,
        )

    def delete_by_id_for_user(self, interview_id: int, user_id: int) -> bool:
        self.delete_by_id_for_user_calls += 1
        original_count = len(self.records)
        self.records = [
            record
            for record in self.records
            if not (record.id == interview_id and record.user_id == user_id)
        ]
        return len(self.records) < original_count

    def delete_all_by_user(self, user_id: int) -> int:
        original_count = len(self.records)
        self.records = [record for record in self.records if record.user_id != user_id]
        return original_count - len(self.records)

    def delete_ids_by_user(self, interview_ids: list[int], user_id: int) -> int:
        target_ids = set(interview_ids)
        original_count = len(self.records)
        self.records = [
            record
            for record in self.records
            if not (record.id in target_ids and record.user_id == user_id)
        ]
        return original_count - len(self.records)

    def list_interview_ids_by_user(self, user_id: int) -> list[int]:
        return [record.id for record in self.records if record.user_id == user_id]


class FakeShortTermMemoryStore:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.deleted: list[tuple[int, int]] = []
        self.batch_deleted: list[tuple[int, list[int]]] = []

    def delete(self, user_id: int, interview_id: int) -> bool:
        if self.fail:
            raise ShortTermMemoryStoreError("redis unavailable")
        self.deleted.append((user_id, interview_id))
        return True

    def delete_many(self, user_id: int, interview_ids: list[int]) -> int:
        if self.fail:
            raise ShortTermMemoryStoreError("redis unavailable")
        self.batch_deleted.append((user_id, interview_ids))
        return len(interview_ids)


def test_history_list_only_returns_current_user_records() -> None:
    service = HistoryService(_fake_repository([_record(1, 1), _record(2, 2)]))

    response = service.list_history_page(_user(1), limit=20, offset=0).items

    assert [item.interview_id for item in response] == [1]
    assert not hasattr(response[0], "score")
    assert not hasattr(response[0], "report_reliability_status")


def test_report_list_only_returns_persisted_reports_for_current_user() -> None:
    service = HistoryService(
        _fake_repository([
            _record(1, 1, feedback_report=DEFAULT_FEEDBACK_REPORT),
            _record(2, 1, feedback_report=None),
            _record(3, 2, feedback_report=DEFAULT_FEEDBACK_REPORT),
        ])
    )

    response = service.list_reports(_user(1))

    assert [item.interview_id for item in response] == [1]
    assert response[0].score == 88
    assert response[0].report_reliability_status == "reference_only"


def test_history_list_orders_by_started_or_created_time_desc() -> None:
    records = [
        _record(1, 1, started_at=datetime(2026, 6, 11, 10, 0, 0)),
        _record(2, 1, started_at=None, created_at=datetime(2026, 6, 11, 12, 0, 0)),
        _record(3, 1, started_at=datetime(2026, 6, 11, 11, 0, 0)),
    ]
    service = HistoryService(_fake_repository(records))

    response = service.list_history_page(_user(1), limit=20, offset=0).items

    assert [item.interview_id for item in response] == [2, 3, 1]


def test_history_page_filters_before_pagination() -> None:
    records = [
        _record(index, 1, target_position="稀有岗位" if index == 1 else "后端开发")
        for index in range(1, 22)
    ]
    service = HistoryService(_fake_repository(records))

    response = service.list_history_page(_user(1), limit=20, offset=0, query="稀有岗位")

    assert [item.interview_id for item in response.items] == [1]
    assert response.next_offset is None


def test_report_page_sorts_globally_before_pagination() -> None:
    records = [
        _record(
            index,
            1,
            feedback_report=FeedbackReportRecord(
                score=score,
                weaknesses=[],
                suggestions=[],
                created_at=datetime(2026, 6, index, 10, 0, 0),
            ),
        )
        for index, score in ((1, 70), (2, 99), (3, 80))
    ]
    service = HistoryService(_fake_repository(records))

    response = service.list_reports_page(
        _user(1),
        limit=1,
        offset=0,
        sort="score-desc",
    )

    assert [item.interview_id for item in response.items] == [2]
    assert response.next_offset == 1


def test_history_detail_returns_multi_round_fields_without_qa_history() -> None:
    service = HistoryService(_fake_repository([_record(1, 1)]))

    response = service.get_detail(1, _user(1))

    assert response.model_dump() == {
        "interview_id": 1,
        "target_position": "后端开发",
        "status": "finished",
        "mode": "multi_round",
        "experience_mode": "training",
        "job_description": None,
        "overall_status": "finished",
        "rounds": [],
        "qa_history": [],
        "report_quality": {
            "completed_round_count": 0,
            "selected_round_count": 0,
            "answered_question_count": 0,
            "evaluated_question_count": 0,
            "score_coverage_percent": 0,
            "reliability_reasons": [
                "存在提前结束或恢复降级，报告仅供参考。",
                "缺少可用于评分的有效回答。",
            ],
            "score_sources": [],
        },
        "resume": {
            "id": 101,
            "created_at": datetime(2026, 6, 11, 9, 30, 0),
            "structured_data": {"basic_info": {"name": "Alice"}, "skills": ["Python"]},
        },
        "feedback_report": {
            "score": 88,
            "weaknesses": ["项目细节不足"],
            "suggestions": ["补充量化结果"],
            "recommendation": None,
            "round_scores": None,
            "strengths": None,
            "reference_note": None,
            "report_reliability_status": "reference_only",
            "detailed_feedback": {
                "problem_diagnosis": [
                    {
                        "title": "项目细节不足",
                        "severity": "medium",
                        "evidence": ["来自最终总评的主要不足。"],
                        "impact": "可能影响岗位匹配度和最终录用建议。",
                        "suggestion": "结合对应轮次问答补充可验证案例，并在下次面试中主动说明。",
                    }
                ],
                "round_reviews": [],
                "action_plan": [
                    {
                        "title": "优先修复报告中的高影响问题",
                        "priority": "high",
                        "steps": [
                            "结合对应轮次问答补充可验证案例，并在下次面试中主动说明。",
                            "为每个薄弱点准备一个具体项目案例。",
                            "回答时补充量化结果、个人贡献和复盘结论。",
                        ],
                        "expected_outcome": "提升下一次面试中问题回答的证据密度和可信度。",
                    },
                    {
                        "title": "补充量化结果",
                        "priority": "medium",
                        "steps": [
                            "把建议拆成一个可练习的问题清单。",
                            "准备 2 分钟结构化回答，覆盖背景、行动和结果。",
                            "用本次报告中的问题逐条校验是否已经补齐。",
                        ],
                        "expected_outcome": "让改进建议落到可执行的面试准备动作。",
                    },
                ],
                "follow_up_questions": [
                    "针对“项目细节不足”，请补充一个具体案例、你的行动和最终结果。"
                ],
            },
        },
        "started_at": datetime(2026, 6, 11, 10, 0, 0),
        "ended_at": datetime(2026, 6, 11, 10, 30, 0),
        "harness_status": None,
        "recovery_count": 0,
        "had_degradation": False,
        "last_harness_error": None,
    }


def test_history_detail_returns_multi_round_rounds_summary_and_qa_history() -> None:
    service = HistoryService(_fake_repository([_multi_round_record()]))

    response = service.get_detail(10, _user(1))
    payload = response.model_dump()

    assert payload["mode"] == "multi_round"
    assert payload["job_description"] == "负责后端平台建设"
    assert payload["overall_status"] == "finished"
    assert payload["harness_status"] == "degraded"
    assert payload["recovery_count"] == 2
    assert payload["had_degradation"] is True
    assert payload["last_harness_error"] == "LLM timeout"
    assert payload["feedback_report"]["recommendation"] == "建议录用"
    assert payload["feedback_report"]["round_scores"] == [
        {"round_type": "resume", "score": 82, "result": "passed"}
    ]
    assert payload["feedback_report"]["report_reliability_status"] == "unavailable"
    assert payload["report_quality"] == {
        "completed_round_count": 1,
        "selected_round_count": 1,
        "answered_question_count": 1,
        "evaluated_question_count": 0,
        "score_coverage_percent": 0,
        "reliability_reasons": [
            "执行校验失败，报告不可用。",
            "面试过程中发生过降级或自动恢复。",
            "部分有效回答没有题目级评分。",
        ],
        "score_sources": [
            {
                "round_type": "resume",
                "status": "completed",
                "score": 82,
                "source": "final_report",
                "answered_question_count": 1,
                "evaluated_question_count": 0,
                "is_reference_only": False,
            }
        ],
    }
    assert payload["rounds"] == [
        {
            "id": 201,
            "round_type": "resume",
            "status": "completed",
            "score": 82,
            "result": "passed",
            "summary": {
                "score": 82,
                "result": "passed",
                "main_issues": ["项目深度还可以更具体"],
            },
            "started_at": datetime(2026, 6, 11, 10, 0, 0),
            "ended_at": datetime(2026, 6, 11, 10, 8, 0),
            "elapsed_seconds": 480,
        }
    ]
    assert payload["qa_history"] == [
        {
            "id": 301,
            "round_id": 201,
            "round_type": "resume",
            "sequence": 1,
            "question_type": "resume_question",
            "question": "介绍一个项目",
            "answer": "我做过订单系统",
            "question_kind": "main",
            "parent_question_id": None,
            "created_at": datetime(2026, 6, 11, 10, 1, 0),
        }
    ]


def test_simulation_history_hides_active_round_evaluation_from_detail_and_feedback() -> None:
    record = HistoryInterviewRecord(
        id=11,
        user_id=1,
        resume_id=101,
        target_position="后端开发",
        status="in_progress",
        mode="multi_round",
        job_description=None,
        overall_status="in_progress",
        elapsed_seconds=300,
        started_at=datetime(2026, 6, 11, 10, 0, 0),
        ended_at=None,
        last_active_at=datetime(2026, 6, 11, 10, 5, 0),
        created_at=datetime(2026, 6, 11, 9, 0, 0),
        resume=ResumeSummaryRecord(
            id=101,
            structured_data={"skills": ["Python"]},
            created_at=datetime(2026, 6, 11, 9, 30, 0),
        ),
        feedback_report=FeedbackReportRecord(score=70, weaknesses=[], suggestions=[]),
        rounds=[
            HistoryRoundRecord(
                id=201,
                round_type="resume",
                status="completed",
                score=80,
                result="passed",
                summary={"score": 80, "result": "passed"},
                is_reference_only=False,
                started_at=datetime(2026, 6, 11, 10, 0, 0),
                ended_at=datetime(2026, 6, 11, 10, 3, 0),
            ),
            HistoryRoundRecord(
                id=202,
                round_type="technical",
                status="in_progress",
                score=None,
                result=None,
                summary=None,
                is_reference_only=False,
                started_at=datetime(2026, 6, 11, 10, 3, 0),
                ended_at=None,
            ),
        ],
        qa_history=[
            HistoryQARecord(
                id=301,
                round_id=201,
                round_type="resume",
                sequence=1,
                question_type="resume_question",
                question="介绍项目",
                answer="我负责项目",
                question_kind="main",
                parent_question_id=None,
                created_at=datetime(2026, 6, 11, 10, 1, 0),
                question_evaluation={"total_score": 80, "issues": ["已结束轮次问题"]},
            ),
            HistoryQARecord(
                id=302,
                round_id=202,
                round_type="technical",
                sequence=1,
                question_type="technical_question",
                question="解释索引",
                answer="索引可以减少扫描",
                question_kind="main",
                parent_question_id=None,
                created_at=datetime(2026, 6, 11, 10, 4, 0),
                question_evaluation={
                    "total_score": 42,
                    "issues": ["ACTIVE_EVALUATION_SECRET"],
                    "evidence": ["ACTIVE_EVIDENCE_SECRET"],
                },
            ),
        ],
        experience_mode="simulation",
    )
    service = HistoryService(_fake_repository([record]))

    payload = service.get_detail(record.id, _user(1)).model_dump()

    assert payload["qa_history"][0]["question_evaluation"]["total_score"] == 80
    assert "question_evaluation" not in payload["qa_history"][1]
    assert payload["report_quality"]["evaluated_question_count"] == 1
    assert "ACTIVE_EVALUATION_SECRET" not in str(payload)
    assert "ACTIVE_EVIDENCE_SECRET" not in str(payload)


def test_training_history_keeps_active_round_evaluation() -> None:
    record = _multi_round_record()
    active_round = HistoryRoundRecord(
        id=202,
        round_type="technical",
        status="in_progress",
        score=None,
        result=None,
        summary=None,
        is_reference_only=False,
        started_at=datetime(2026, 6, 11, 10, 8, 0),
        ended_at=None,
    )
    active_qa = HistoryQARecord(
        id=302,
        round_id=202,
        round_type="technical",
        sequence=1,
        question_type="technical_question",
        question="解释索引",
        answer="索引可以减少扫描",
        question_kind="main",
        parent_question_id=None,
        created_at=datetime(2026, 6, 11, 10, 9, 0),
        question_evaluation={"total_score": 72},
    )
    training_record = HistoryInterviewRecord(
        **{
            **record.__dict__,
            "status": "in_progress",
            "overall_status": "in_progress",
            "ended_at": None,
            "rounds": [*(record.rounds or []), active_round],
            "qa_history": [*(record.qa_history or []), active_qa],
            "experience_mode": "training",
        }
    )
    service = HistoryService(_fake_repository([training_record]))

    payload = service.get_detail(training_record.id, _user(1)).model_dump()

    assert payload["qa_history"][-1]["question_evaluation"]["total_score"] == 72


def test_history_detail_returns_not_found_for_other_users_record() -> None:
    repository = _fake_repository([_record(1, 2)])
    service = HistoryService(repository)

    with pytest.raises(AppError) as error_info:
        service.get_detail(1, _user(1))

    assert error_info.value.status_code == 404
    assert error_info.value.code == ErrorCode.NOT_FOUND
    assert repository.get_by_id_calls == 0
    assert repository.get_by_id_for_user_calls == 1


def test_history_detail_supports_missing_feedback_report() -> None:
    service = HistoryService(_fake_repository([_record(1, 1, feedback_report=None)]))

    response = service.get_detail(1, _user(1))

    assert response.feedback_report is None
    assert response.interview_id == 1
    assert response.target_position == "后端开发"


def test_delete_history_item_removes_current_user_record() -> None:
    repository = _fake_repository([_record(1, 1), _record(2, 1), _record(3, 2)])
    service = HistoryService(repository)

    service.delete_history_item(1, _user(1))

    assert [record.id for record in repository.records] == [2, 3]


def test_delete_history_item_returns_not_found_for_other_users_record() -> None:
    repository = _fake_repository([_record(1, 2)])
    service = HistoryService(repository)

    with pytest.raises(AppError) as error_info:
        service.delete_history_item(1, _user(1))

    assert error_info.value.status_code == 404
    assert error_info.value.code == ErrorCode.NOT_FOUND
    assert repository.get_by_id_calls == 0
    assert repository.delete_by_id_for_user_calls == 1
    assert [record.id for record in repository.records] == [1]


def test_clear_history_removes_only_current_user_records() -> None:
    repository = _fake_repository([_record(1, 1), _record(2, 1), _record(3, 2)])
    service = HistoryService(repository)

    service.clear_history(_user(1))

    assert [record.id for record in repository.records] == [3]


def test_clear_history_does_not_delete_interviews_created_after_snapshot() -> None:
    class ConcurrentCreateRepository(FakeHistoryRepository):
        def list_interview_ids_by_user(self, user_id: int) -> list[int]:
            interview_ids = super().list_interview_ids_by_user(user_id)
            self.records.append(_record(99, user_id))
            return interview_ids

    repository = ConcurrentCreateRepository([_record(1, 1)])

    HistoryService(repository).clear_history(_user(1))

    assert [record.id for record in repository.records] == [99]


def test_delete_history_item_clears_short_term_memory() -> None:
    repository = _fake_repository([_record(1, 1), _record(2, 1)])
    store = FakeShortTermMemoryStore()
    service = HistoryService(repository, store)

    service.delete_history_item(1, _user(1))

    assert store.deleted == [(1, 1)]


def test_clear_history_clears_all_short_term_memory_keys_for_user() -> None:
    repository = _fake_repository([_record(1, 1), _record(2, 1), _record(3, 2)])
    store = FakeShortTermMemoryStore()
    service = HistoryService(repository, store)

    service.clear_history(_user(1))

    assert store.batch_deleted == [(1, [1, 2])]


def test_history_delete_succeeds_when_short_term_memory_cleanup_is_unavailable() -> None:
    repository = _fake_repository([_record(1, 1)])
    service = HistoryService(repository, FakeShortTermMemoryStore(fail=True))

    service.delete_history_item(1, _user(1))

    assert repository.records == []


def test_history_delete_commits_under_interview_mutation_lock() -> None:
    source = __import__("inspect").getsource(HistoryService.delete_history_item)

    assert "_lock_interviews" in source
    assert "_commit_repository" in source
    assert source.index("_commit_repository") < source.index("short_term_memory_store.delete")


def _fake_repository(records: list[HistoryInterviewRecord]) -> FakeHistoryRepository:
    return FakeHistoryRepository(records)


def _user(user_id: int) -> UserRecord:
    return UserRecord(id=user_id, username=f"user-{user_id}", password_hash="hash")


def _record(
    interview_id: int,
    user_id: int,
    started_at: datetime | None = datetime(2026, 6, 11, 10, 0, 0),
    created_at: datetime = datetime(2026, 6, 11, 9, 0, 0),
    feedback_report: FeedbackReportRecord | None = DEFAULT_FEEDBACK_REPORT,
    target_position: str = "后端开发",
) -> HistoryInterviewRecord:
    return HistoryInterviewRecord(
        id=interview_id,
        user_id=user_id,
        resume_id=101,
        target_position=target_position,
        status="finished",
        mode="multi_round",
        job_description=None,
        overall_status="finished",
        elapsed_seconds=1800,
        started_at=started_at,
        ended_at=datetime(2026, 6, 11, 10, 30, 0),
        last_active_at=datetime(2026, 6, 11, 10, 20, 0),
        created_at=created_at,
        resume=ResumeSummaryRecord(
            id=101,
            structured_data={"basic_info": {"name": "Alice"}, "skills": ["Python"]},
            created_at=datetime(2026, 6, 11, 9, 30, 0),
        ),
        feedback_report=feedback_report,
    )


def _multi_round_record() -> HistoryInterviewRecord:
    return HistoryInterviewRecord(
        id=10,
        user_id=1,
        resume_id=101,
        target_position="后端开发",
        status="finished",
        mode="multi_round",
        job_description="负责后端平台建设",
        overall_status="finished",
        elapsed_seconds=480,
        started_at=datetime(2026, 6, 11, 10, 0, 0),
        ended_at=datetime(2026, 6, 11, 10, 8, 0),
        last_active_at=datetime(2026, 6, 11, 10, 8, 0),
        created_at=datetime(2026, 6, 11, 9, 0, 0),
        resume=ResumeSummaryRecord(
            id=101,
            structured_data={"basic_info": {"name": "Alice"}, "skills": ["Python"]},
            created_at=datetime(2026, 6, 11, 9, 30, 0),
        ),
        feedback_report=FeedbackReportRecord(
            score=82,
            weaknesses=["项目深度还可以更具体"],
            suggestions=["补充技术取舍"],
            recommendation="建议录用",
            round_scores=[{"round_type": "resume", "score": 82, "result": "passed"}],
            strengths=["表达清晰"],
            reference_note=None,
            report_reliability_status="unavailable",
        ),
        rounds=[
            HistoryRoundRecord(
                id=201,
                round_type="resume",
                status="completed",
                score=82,
                result="passed",
                summary={
                    "score": 82,
                    "result": "passed",
                    "main_issues": ["项目深度还可以更具体"],
                },
                is_reference_only=False,
                started_at=datetime(2026, 6, 11, 10, 0, 0),
                ended_at=datetime(2026, 6, 11, 10, 8, 0),
            )
        ],
        qa_history=[
            HistoryQARecord(
                id=301,
                round_id=201,
                round_type="resume",
                sequence=1,
                question_type="resume_question",
                question="介绍一个项目",
                answer="我做过订单系统",
                question_kind="main",
                parent_question_id=None,
                created_at=datetime(2026, 6, 11, 10, 1, 0),
            )
        ],
        harness_status="degraded",
        recovery_count=2,
        had_degradation=True,
        last_harness_error="LLM timeout",
    )
