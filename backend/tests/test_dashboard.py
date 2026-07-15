from datetime import datetime

from app.repositories.history import (
    FeedbackReportRecord,
    HistoryInterviewRecord,
    HistoryQARecord,
    HistoryRoundRecord,
    ResumeSummaryRecord,
    WeaknessPracticeProgressRecord,
)
from app.repositories.users import UserRecord
from app.services.dashboard import DashboardService
from app.services.weakness_practice_progress import weakness_key


class FakeDashboardHistoryRepository:
    def __init__(
        self,
        records: list[HistoryInterviewRecord],
        practice_progress: list[WeaknessPracticeProgressRecord] | None = None,
    ) -> None:
        self.records = records
        self.practice_progress = practice_progress or []

    def list_by_user(self, user_id: int) -> list[HistoryInterviewRecord]:
        return [
            record
            for record in self.records
            if record.user_id == user_id
        ]

    def get_by_id(self, interview_id: int) -> HistoryInterviewRecord | None:
        return next((record for record in self.records if record.id == interview_id), None)

    def list_weakness_practice_progress_by_user(
        self,
        user_id: int,
    ) -> list[WeaknessPracticeProgressRecord]:
        return [
            record
            for record in self.practice_progress
            if record.user_id == user_id
        ]


class FakeDashboardMemoryRepository:
    def __init__(self, count: int = 0, fail: bool = False) -> None:
        self.count = count
        self.fail = fail

    def count_active_candidate_memories(self, user_id: int) -> int:
        del user_id
        if self.fail:
            raise RuntimeError("memory unavailable")
        return self.count


class FakeDashboardMemoryTaskRepository:
    def __init__(self, counts: dict[str, int] | None = None) -> None:
        self.counts = counts or {}

    def count_summary_tasks_by_status(self, user_id: int) -> dict[str, int]:
        del user_id
        return self.counts


def test_dashboard_summary_uses_history_and_report_data() -> None:
    service = DashboardService(
        FakeDashboardHistoryRepository(
            [
                _record(
                    1,
                    started_at=datetime(2026, 6, 11, 10, 0, 0),
                    feedback_report=FeedbackReportRecord(
                        score=82,
                        weaknesses=["项目复盘不够量化"],
                        suggestions=["补充业务指标和对比数据"],
                        created_at=datetime(2026, 6, 11, 10, 30, 0),
                    ),
                ),
                _record(
                    2,
                    started_at=datetime(2026, 6, 12, 10, 0, 0),
                    feedback_report=FeedbackReportRecord(
                        score=90,
                        weaknesses=["系统设计边界说明不足", "追问应对略急"],
                        suggestions=["先说明容量假设", "先澄清再给方案"],
                        round_scores=[
                            {
                                "round_type": "resume",
                                "score": 88,
                                "result": "passed",
                                "status": "completed",
                            },
                            {
                                "round_type": "technical",
                                "score": 92,
                                "result": "passed",
                                "status": "completed",
                            },
                        ],
                        used_candidate_memory=True,
                        report_reliability_status="reference_only",
                        created_at=datetime(2026, 6, 12, 10, 30, 0),
                    ),
                ),
            ]
        )
    )

    response = service.get_summary(_user(1))

    assert response.interview_count == 2
    assert response.report_count == 2
    assert response.personalized_feedback_used is True
    assert response.latest_interview is not None
    assert response.latest_interview.interview_id == 2
    assert response.latest_report is not None
    assert response.latest_report.interview_id == 2
    assert response.latest_report.used_candidate_memory is True
    assert response.latest_report.report_reliability_status == "reference_only"
    assert [point.score for point in response.score_trend] == [82, 90]
    assert response.score_delta == 8
    assert [(item.round_type, item.score) for item in response.abilities] == [
        ("resume", 88),
        ("technical", 92),
    ]
    assert [(item.title, item.suggestion) for item in response.weak_points] == [
        ("系统设计边界说明不足", "先说明容量假设"),
        ("追问应对略急", "先澄清再给方案"),
        ("项目复盘不够量化", "补充业务指标和对比数据"),
    ]
    assert response.weak_points[0].summary
    assert response.weak_points[0].sources[0].interview_id == 2
    assert response.memory_status == "enabled"
    assert response.candidate_memory_count == 0


def test_dashboard_memory_status_uses_actual_saved_memories() -> None:
    service = DashboardService(
        FakeDashboardHistoryRepository(
            [
                _record(
                    1,
                    started_at=datetime(2026, 6, 11, 10, 0, 0),
                    feedback_report=FeedbackReportRecord(
                        score=82,
                        weaknesses=["项目复盘不够量化"],
                        suggestions=["补充业务指标和对比数据"],
                        used_candidate_memory=False,
                        created_at=datetime(2026, 6, 11, 10, 30, 0),
                    ),
                )
            ]
        ),
        memory_repository=FakeDashboardMemoryRepository(count=2),
        memory_task_repository=FakeDashboardMemoryTaskRepository(),
    )

    response = service.get_summary(_user(1))

    assert response.personalized_feedback_used is False
    assert response.memory_status == "ready"
    assert response.candidate_memory_count == 2


def test_dashboard_memory_status_shows_pending_summary_task() -> None:
    service = DashboardService(
        FakeDashboardHistoryRepository([]),
        memory_repository=FakeDashboardMemoryRepository(count=0),
        memory_task_repository=FakeDashboardMemoryTaskRepository({"pending": 1}),
    )

    response = service.get_summary(_user(1))

    assert response.memory_status == "summarizing"
    assert response.candidate_memory_count == 0


def test_dashboard_weak_points_use_completed_round_when_report_is_missing() -> None:
    service = DashboardService(
        FakeDashboardHistoryRepository(
            [
                _record(
                    1,
                    started_at=datetime(2026, 6, 12, 10, 0, 0),
                    feedback_report=None,
                    rounds=[
                        HistoryRoundRecord(
                            id=11,
                            round_type="technical",
                            status="completed",
                            score=64,
                            result="needs_improvement",
                            summary={
                                "main_issues": ["架构边界说明不完整"],
                                "suggestions": ["先明确容量、依赖和失败边界"],
                                "evidence": ["回答中缺少降级策略和数据一致性说明"],
                            },
                            is_reference_only=False,
                            started_at=datetime(2026, 6, 12, 10, 0, 0),
                            ended_at=datetime(2026, 6, 12, 10, 20, 0),
                        )
                    ],
                    qa_history=[
                        HistoryQARecord(
                            id=101,
                            round_id=11,
                            round_type="technical",
                            sequence=1,
                            question_type="system_design",
                            question="如何设计订单超时取消？",
                            answer="用定时任务扫描。",
                            question_kind="main",
                            parent_question_id=None,
                            created_at=datetime(2026, 6, 12, 10, 5, 0),
                            question_evaluation={
                                "issues": ["异常场景覆盖不足"],
                                "evidence": ["没有说明消息重复投递和补偿逻辑"],
                                "follow_up_direction": "补充失败重试和幂等设计",
                            },
                        )
                    ],
                )
            ]
        )
    )

    response = service.get_summary(_user(1))

    assert response.report_count == 0
    assert [(item.title, item.suggestion) for item in response.weak_points] == [
        ("架构边界说明不完整", "先明确容量、依赖和失败边界"),
        ("异常场景覆盖不足", "补充失败重试和幂等设计"),
    ]
    assert response.weak_points[0].sources[0].round_type == "technical"
    assert "回答中缺少降级策略和数据一致性说明" in response.weak_points[0].evidence
    assert "没有说明消息重复投递和补偿逻辑" in response.weak_points[0].evidence


def test_dashboard_replaces_generic_final_report_weakness_with_evidence_notice() -> None:
    service = DashboardService(
        FakeDashboardHistoryRepository(
            [
                _record(
                    1,
                    started_at=datetime(2026, 6, 12, 10, 0, 0),
                    feedback_report=FeedbackReportRecord(
                        score=70,
                        weaknesses=["部分能力维度仍需结合后续面试继续验证。"],
                        suggestions=["复盘每轮回答，补充更具体的项目证据、技术取舍和结果数据。"],
                        created_at=datetime(2026, 6, 12, 10, 30, 0),
                    ),
                    rounds=[
                        HistoryRoundRecord(
                            id=11,
                            round_type="resume",
                            status="finished_early",
                            score=70,
                            result="reference_only",
                            summary={"is_reference_only": True},
                            is_reference_only=True,
                            started_at=datetime(2026, 6, 12, 10, 0, 0),
                            ended_at=datetime(2026, 6, 12, 10, 12, 0),
                        )
                    ],
                    qa_history=[],
                )
            ]
        )
    )

    response = service.get_summary(_user(1))

    assert [(item.title, item.suggestion) for item in response.weak_points] == [
        (
            "回答证据仍需补充",
            "下次至少完整完成一个核心轮次，并在回答中补充项目背景、个人动作、结果指标和技术取舍。",
        )
    ]
    assert "最终报告只给出了参考性结论" in response.weak_points[0].evidence[1]


def test_dashboard_weak_points_include_practice_progress() -> None:
    practiced_at = datetime(2026, 6, 13, 11, 0, 0)
    service = DashboardService(
        FakeDashboardHistoryRepository(
            [
                _record(
                    1,
                    started_at=datetime(2026, 6, 12, 10, 0, 0),
                    feedback_report=FeedbackReportRecord(
                        score=70,
                        weaknesses=["系统设计边界说明不足"],
                        suggestions=["先说明容量假设"],
                        created_at=datetime(2026, 6, 12, 10, 30, 0),
                    ),
                )
            ],
            practice_progress=[
                WeaknessPracticeProgressRecord(
                    id=1,
                    user_id=1,
                    source_interview_id=1,
                    practice_interview_id=2,
                    weakness_title="系统设计边界说明不足",
                    weakness_key=weakness_key("系统设计边界说明不足"),
                    suggestion="先说明容量假设",
                    round_type="technical",
                    status="improving",
                    source_score=70,
                    practice_score=76,
                    last_practiced_at=practiced_at,
                    created_at=datetime(2026, 6, 13, 10, 0, 0),
                    updated_at=practiced_at,
                )
            ],
        )
    )

    response = service.get_summary(_user(1))

    assert response.weak_points[0].title == "系统设计边界说明不足"
    assert response.weak_points[0].practice_status == "improving"
    assert response.weak_points[0].practice_score == 76
    assert response.weak_points[0].practice_count == 1
    assert response.weak_points[0].last_practiced_at == practiced_at


def test_dashboard_summary_supports_empty_history() -> None:
    service = DashboardService(FakeDashboardHistoryRepository([]))

    response = service.get_summary(_user(1))

    assert response.interview_count == 0
    assert response.report_count == 0
    assert response.personalized_feedback_used is False
    assert response.latest_interview is None
    assert response.latest_report is None
    assert response.score_trend == []
    assert response.score_delta is None
    assert response.abilities == []
    assert response.weak_points == []


def _user(user_id: int) -> UserRecord:
    return UserRecord(id=user_id, username=f"user-{user_id}", password_hash="hash")


def _record(
    interview_id: int,
    started_at: datetime,
    feedback_report: FeedbackReportRecord | None,
    rounds: list[HistoryRoundRecord] | None = None,
    qa_history: list[HistoryQARecord] | None = None,
) -> HistoryInterviewRecord:
    return HistoryInterviewRecord(
        id=interview_id,
        user_id=1,
        resume_id=101,
        target_position="后端开发",
        status="finished",
        mode="multi_round",
        job_description=None,
        overall_status="finished",
        elapsed_seconds=1800,
        started_at=started_at,
        ended_at=None,
        last_active_at=started_at,
        created_at=started_at,
        resume=ResumeSummaryRecord(
            id=101,
            structured_data={"skills": ["Python"]},
            created_at=started_at,
        ),
        feedback_report=feedback_report,
        rounds=rounds,
        qa_history=qa_history,
    )
