CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(64) NOT NULL,
    description VARCHAR(255) NOT NULL,
    applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS users (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    username VARCHAR(64) NOT NULL,
    display_name VARCHAR(64) NULL,
    avatar_url VARCHAR(512) NULL,
    password_hash VARCHAR(255) NOT NULL,
    memory_enabled TINYINT(1) NOT NULL DEFAULT 1,
    memory_updated_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS evolution_version_bundles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    bundle_key VARCHAR(128) NOT NULL,
    parent_bundle_id BIGINT UNSIGNED NULL,
    scope_type VARCHAR(32) NOT NULL DEFAULT 'global',
    scope_key VARCHAR(128) NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'candidate',
    risk_level VARCHAR(32) NOT NULL DEFAULT 'low',
    content_hash CHAR(64) NOT NULL,
    diff JSON NOT NULL,
    validation_summary JSON NOT NULL,
    rollback_point JSON NULL,
    created_by_run_id BIGINT UNSIGNED NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activated_at DATETIME NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_evolution_version_bundles_key (bundle_key),
    KEY idx_evolution_version_bundles_scope_status (scope_type, scope_key, status),
    KEY idx_evolution_version_bundles_parent (parent_bundle_id),
    CONSTRAINT fk_evolution_version_bundles_parent
        FOREIGN KEY (parent_bundle_id) REFERENCES evolution_version_bundles (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS resumes (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    original_file_path VARCHAR(512) NOT NULL,
    display_name VARCHAR(128) NULL,
    content_hash CHAR(64) NULL,
    structured_data JSON NOT NULL,
    is_default TINYINT(1) NOT NULL DEFAULT 0,
    default_key VARCHAR(16) NULL,
    deleted_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_resumes_user_id (user_id),
    KEY idx_resumes_user_deleted_default (user_id, deleted_at, is_default),
    UNIQUE KEY uk_resumes_user_content_hash (user_id, content_hash),
    UNIQUE KEY uk_resumes_user_default_key (user_id, default_key),
    CONSTRAINT fk_resumes_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS usage_limits (
    user_id BIGINT UNSIGNED NOT NULL,
    scope VARCHAR(64) NOT NULL,
    usage_date DATE NOT NULL,
    used_count INT NOT NULL DEFAULT 0,
    next_allowed_at DATETIME NULL,
    active_token VARCHAR(64) NULL,
    active_expires_at DATETIME NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, scope, usage_date),
    KEY idx_usage_limits_active (active_expires_at),
    CONSTRAINT fk_usage_limits_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS resume_parse_tasks (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    original_file_path VARCHAR(512) NOT NULL,
    content_hash CHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    resume_id BIGINT UNSIGNED NULL,
    error_message VARCHAR(1000) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME NULL,
    completed_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY idx_resume_parse_tasks_user_created (user_id, created_at, id),
    KEY idx_resume_parse_tasks_status_created (status, created_at),
    KEY idx_resume_parse_tasks_resume_id (resume_id),
    CONSTRAINT fk_resume_parse_tasks_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_resume_parse_tasks_resume_id
        FOREIGN KEY (resume_id) REFERENCES resumes (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS interviews (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    resume_id BIGINT UNSIGNED NOT NULL,
    target_position VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'created',
    mode VARCHAR(32) NOT NULL DEFAULT 'multi_round',
    job_description TEXT NULL,
    selected_rounds JSON NULL,
    version_bundle_id BIGINT UNSIGNED NULL,
    current_round VARCHAR(32) NULL,
    overall_status VARCHAR(32) NOT NULL DEFAULT 'created',
    started_at DATETIME NULL,
    ended_at DATETIME NULL,
    last_active_at DATETIME NULL,
    elapsed_seconds INT NOT NULL DEFAULT 0,
    question_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_interviews_user_id (user_id),
    KEY idx_interviews_resume_id (resume_id),
    KEY idx_interviews_version_bundle_id (version_bundle_id),
    KEY idx_interviews_status_started_at (status, started_at),
    KEY idx_interviews_mode_overall_status (mode, overall_status),
    CONSTRAINT fk_interviews_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_interviews_resume_id
        FOREIGN KEY (resume_id) REFERENCES resumes (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_interviews_version_bundle_id
        FOREIGN KEY (version_bundle_id) REFERENCES evolution_version_bundles (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS evolution_artifacts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    bundle_id BIGINT UNSIGNED NOT NULL,
    artifact_type VARCHAR(64) NOT NULL,
    artifact_key VARCHAR(128) NOT NULL,
    version VARCHAR(64) NOT NULL,
    content JSON NOT NULL,
    content_hash CHAR(64) NOT NULL,
    parent_artifact_id BIGINT UNSIGNED NULL,
    diff JSON NOT NULL,
    risk_level VARCHAR(32) NOT NULL DEFAULT 'low',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_evolution_artifacts_bundle_key (bundle_id, artifact_type, artifact_key),
    KEY idx_evolution_artifacts_parent (parent_artifact_id),
    CONSTRAINT fk_evolution_artifacts_bundle_id
        FOREIGN KEY (bundle_id) REFERENCES evolution_version_bundles (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_evolution_artifacts_parent
        FOREIGN KEY (parent_artifact_id) REFERENCES evolution_artifacts (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS interview_rounds (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    interview_id BIGINT UNSIGNED NOT NULL,
    agent_type VARCHAR(64) NOT NULL,
    round_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    min_main_questions INT NOT NULL,
    max_main_questions INT NOT NULL,
    min_total_questions INT NOT NULL,
    max_total_questions INT NOT NULL,
    score INT NULL,
    result VARCHAR(32) NULL,
    summary JSON NULL,
    is_reference_only TINYINT(1) NOT NULL DEFAULT 0,
    started_at DATETIME NULL,
    ended_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_interview_rounds_interview_round (interview_id, round_type),
    KEY idx_interview_rounds_interview_id (interview_id),
    CONSTRAINT fk_interview_rounds_interview_id
        FOREIGN KEY (interview_id) REFERENCES interviews (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS interview_operation_tasks (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    interview_id BIGINT UNSIGNED NOT NULL,
    round_id BIGINT UNSIGNED NULL,
    operation VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    result_json JSON NULL,
    error_code VARCHAR(64) NULL,
    error_message TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME NULL,
    completed_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY idx_interview_operation_tasks_user_created (user_id, created_at, id),
    KEY idx_interview_operation_tasks_interview_id (interview_id),
    CONSTRAINT fk_interview_operation_tasks_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_interview_operation_tasks_interview_id
        FOREIGN KEY (interview_id) REFERENCES interviews (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_interview_operation_tasks_round_id
        FOREIGN KEY (round_id) REFERENCES interview_rounds (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS interview_qa (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    interview_id BIGINT UNSIGNED NOT NULL,
    round_id BIGINT UNSIGNED NULL,
    sequence INT NOT NULL,
    question_type VARCHAR(64) NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NULL,
    question_kind VARCHAR(32) NOT NULL DEFAULT 'main',
    question_status VARCHAR(32) NOT NULL DEFAULT 'active',
    parent_question_id BIGINT UNSIGNED NULL,
    regenerated_from_question_id BIGINT UNSIGNED NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_interview_qa_round_sequence (round_id, sequence),
    KEY idx_interview_qa_interview_id (interview_id),
    KEY idx_interview_qa_round_sequence (round_id, sequence),
    KEY idx_interview_qa_round_status (round_id, question_status),
    KEY idx_interview_qa_parent_question_id (parent_question_id),
    KEY idx_interview_qa_regenerated_from (regenerated_from_question_id),
    CONSTRAINT fk_interview_qa_interview_id
        FOREIGN KEY (interview_id) REFERENCES interviews (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_interview_qa_round_id
        FOREIGN KEY (round_id) REFERENCES interview_rounds (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_interview_qa_parent_question_id
        FOREIGN KEY (parent_question_id) REFERENCES interview_qa (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_interview_qa_regenerated_from_question_id
        FOREIGN KEY (regenerated_from_question_id) REFERENCES interview_qa (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS feedback_reports (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    interview_id BIGINT UNSIGNED NOT NULL,
    score INT NOT NULL,
    weaknesses JSON NOT NULL,
    suggestions JSON NOT NULL,
    recommendation VARCHAR(32) NULL,
    round_scores JSON NULL,
    strengths JSON NULL,
    ability_analysis JSON NULL,
    job_match TEXT NULL,
    final_conclusion TEXT NULL,
    confidence VARCHAR(16) NULL,
    reference_note VARCHAR(255) NULL,
    used_candidate_memory TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_feedback_reports_interview_id (interview_id),
    CONSTRAINT fk_feedback_reports_interview_id
        FOREIGN KEY (interview_id) REFERENCES interviews (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS candidate_memories (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    memory_type VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    structured_data JSON NOT NULL,
    tokens JSON NOT NULL,
    confidence DECIMAL(5,4) NOT NULL DEFAULT 0.0000,
    confidence_detail JSON NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending_review',
    index_status VARCHAR(32) NOT NULL DEFAULT 'pending_index',
    source_interview_id BIGINT UNSIGNED NULL,
    source_round_id BIGINT UNSIGNED NULL,
    version INT NOT NULL DEFAULT 1,
    superseded_by_id BIGINT UNSIGNED NULL,
    last_evidence_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_candidate_memories_user_status (user_id, status),
    KEY idx_candidate_memories_user_type_status (user_id, memory_type, status),
    KEY idx_candidate_memories_index_status (index_status),
    KEY idx_candidate_memories_source_interview (source_interview_id),
    UNIQUE KEY uk_candidate_memory_summary (
        user_id, memory_type, title, source_interview_id, source_round_id, version
    ),
    CONSTRAINT fk_candidate_memories_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_candidate_memories_source_interview_id
        FOREIGN KEY (source_interview_id) REFERENCES interviews (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_candidate_memories_source_round_id
        FOREIGN KEY (source_round_id) REFERENCES interview_rounds (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_candidate_memories_superseded_by_id
        FOREIGN KEY (superseded_by_id) REFERENCES candidate_memories (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS interviewer_memories (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    agent_type VARCHAR(64) NOT NULL,
    position_key VARCHAR(128) NOT NULL DEFAULT '',
    memory_type VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    structured_data JSON NOT NULL,
    tokens JSON NOT NULL,
    confidence DECIMAL(5,4) NOT NULL DEFAULT 0.0000,
    confidence_detail JSON NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending_review',
    index_status VARCHAR(32) NOT NULL DEFAULT 'pending_index',
    source_interview_id BIGINT UNSIGNED NULL,
    source_round_id BIGINT UNSIGNED NULL,
    version INT NOT NULL DEFAULT 1,
    superseded_by_id BIGINT UNSIGNED NULL,
    last_evidence_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_interviewer_memories_agent_position_status (agent_type, position_key, status),
    KEY idx_interviewer_memories_type_status (memory_type, status),
    KEY idx_interviewer_memories_index_status (index_status),
    UNIQUE KEY uk_interviewer_memory_summary (
        agent_type, position_key, memory_type, title, source_interview_id, source_round_id, version
    ),
    CONSTRAINT fk_interviewer_memories_source_interview_id
        FOREIGN KEY (source_interview_id) REFERENCES interviews (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_interviewer_memories_source_round_id
        FOREIGN KEY (source_round_id) REFERENCES interview_rounds (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_interviewer_memories_superseded_by_id
        FOREIGN KEY (superseded_by_id) REFERENCES interviewer_memories (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agent_memories (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    agent_type VARCHAR(64) NOT NULL,
    scenario VARCHAR(64) NOT NULL DEFAULT '',
    memory_type VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    structured_data JSON NOT NULL,
    tokens JSON NOT NULL,
    confidence DECIMAL(5,4) NOT NULL DEFAULT 0.0000,
    confidence_detail JSON NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending_review',
    index_status VARCHAR(32) NOT NULL DEFAULT 'pending_index',
    source_interview_id BIGINT UNSIGNED NULL,
    source_round_id BIGINT UNSIGNED NULL,
    version INT NOT NULL DEFAULT 1,
    superseded_by_id BIGINT UNSIGNED NULL,
    last_evidence_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_agent_memories_agent_scenario_status (agent_type, scenario, status),
    KEY idx_agent_memories_type_status (memory_type, status),
    KEY idx_agent_memories_index_status (index_status),
    UNIQUE KEY uk_agent_memory_summary (
        agent_type, scenario, memory_type, title, source_interview_id, source_round_id, version
    ),
    CONSTRAINT fk_agent_memories_source_interview_id
        FOREIGN KEY (source_interview_id) REFERENCES interviews (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_agent_memories_source_round_id
        FOREIGN KEY (source_round_id) REFERENCES interview_rounds (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_agent_memories_superseded_by_id
        FOREIGN KEY (superseded_by_id) REFERENCES agent_memories (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS memory_tasks (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    task_type VARCHAR(64) NOT NULL,
    user_id BIGINT UNSIGNED NULL,
    interview_id BIGINT UNSIGNED NULL,
    memory_collection VARCHAR(64) NULL,
    memory_id BIGINT UNSIGNED NULL,
    dedupe_key VARCHAR(128) NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    retry_count INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 3,
    next_retry_at DATETIME NULL,
    error_message VARCHAR(1000) NULL,
    result JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME NULL,
    completed_at DATETIME NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_memory_tasks_summary_interview (task_type, interview_id),
    UNIQUE KEY uk_memory_tasks_dedupe_key (dedupe_key),
    KEY idx_memory_tasks_claim (status, next_retry_at, created_at),
    KEY idx_memory_tasks_user_type_status (user_id, task_type, status),
    KEY idx_memory_tasks_memory (memory_collection, memory_id),
    CONSTRAINT fk_memory_tasks_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_memory_tasks_interview_id
        FOREIGN KEY (interview_id) REFERENCES interviews (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS notifications (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    summary VARCHAR(500) NOT NULL,
    notification_type VARCHAR(64) NOT NULL,
    is_read TINYINT(1) NOT NULL DEFAULT 0,
    related_type VARCHAR(64) NULL,
    related_id BIGINT UNSIGNED NULL,
    interview_id BIGINT UNSIGNED NULL,
    round_id BIGINT UNSIGNED NULL,
    question_id BIGINT UNSIGNED NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY idx_notifications_user_created (user_id, created_at, id),
    KEY idx_notifications_user_unread_created (user_id, is_read, created_at, id),
    KEY idx_notifications_related (related_type, related_id),
    KEY idx_notifications_interview (interview_id),
    KEY idx_notifications_round (round_id),
    KEY idx_notifications_question (question_id),
    CONSTRAINT fk_notifications_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS rag_audit_logs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    request_id VARCHAR(64) NOT NULL,
    user_id BIGINT UNSIGNED NULL,
    interview_id BIGINT UNSIGNED NULL,
    round_id BIGINT UNSIGNED NULL,
    agent_type VARCHAR(64) NULL,
    usage_scene VARCHAR(64) NOT NULL,
    original_intent VARCHAR(1000) NULL,
    rewritten_query VARCHAR(1000) NULL,
    candidate_memory_ids JSON NOT NULL,
    injected_memory_ids JSON NOT NULL,
    scores JSON NOT NULL,
    timings JSON NOT NULL,
    hit_count INT NOT NULL DEFAULT 0,
    fallback_reason VARCHAR(1000) NULL,
    embedding_version VARCHAR(128) NULL,
    reranker_version VARCHAR(128) NULL,
    prompt_version VARCHAR(64) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_rag_audit_logs_request_id (request_id),
    KEY idx_rag_audit_logs_user_created (user_id, created_at),
    KEY idx_rag_audit_logs_interview_round (interview_id, round_id),
    CONSTRAINT fk_rag_audit_logs_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_rag_audit_logs_interview_id
        FOREIGN KEY (interview_id) REFERENCES interviews (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_rag_audit_logs_round_id
        FOREIGN KEY (round_id) REFERENCES interview_rounds (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS evaluation_records (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    evaluation_type VARCHAR(32) NOT NULL,
    evaluation_key VARCHAR(128) NOT NULL,
    interview_id BIGINT UNSIGNED NOT NULL,
    round_id BIGINT UNSIGNED NULL,
    question_id BIGINT UNSIGNED NULL,
    status VARCHAR(32) NOT NULL,
    dimension_scores JSON NOT NULL,
    total_score INT NULL,
    evidence JSON NOT NULL,
    result JSON NULL,
    error_message VARCHAR(1000) NULL,
    prompt_version VARCHAR(64) NOT NULL,
    model_name VARCHAR(128) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_evaluation_records_type_key (evaluation_type, evaluation_key),
    KEY idx_evaluation_records_interview_type (interview_id, evaluation_type),
    KEY idx_evaluation_records_round_question (round_id, question_id),
    CONSTRAINT fk_evaluation_records_interview_id
        FOREIGN KEY (interview_id) REFERENCES interviews (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE interviews
    ADD COLUMN IF NOT EXISTS version_bundle_id BIGINT UNSIGNED NULL,
    ADD COLUMN IF NOT EXISTS harness_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS last_checkpoint_id BIGINT UNSIGNED NULL,
    ADD COLUMN IF NOT EXISTS recovery_count INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_recovered_at DATETIME NULL,
    ADD COLUMN IF NOT EXISTS last_harness_error VARCHAR(1000) NULL,
    ADD COLUMN IF NOT EXISTS had_degradation TINYINT(1) NOT NULL DEFAULT 0;

ALTER TABLE interview_rounds
    ADD COLUMN IF NOT EXISTS execution_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS retry_count INT NOT NULL DEFAULT 0;

ALTER TABLE feedback_reports
    ADD COLUMN IF NOT EXISTS report_reliability_status VARCHAR(32) NOT NULL DEFAULT 'normal';

CREATE TABLE IF NOT EXISTS harness_traces (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_trace_id BIGINT UNSIGNED NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    interview_id BIGINT UNSIGNED NOT NULL,
    round_id BIGINT UNSIGNED NULL,
    node_id VARCHAR(128) NOT NULL,
    node_type VARCHAR(64) NOT NULL,
    agent_type VARCHAR(64) NOT NULL,
    purpose VARCHAR(128) NOT NULL,
    prompt_version VARCHAR(64) NULL,
    model_name VARCHAR(128) NULL,
    model_params JSON NOT NULL,
    schema_version VARCHAR(64) NULL,
    expected_schema JSON NULL,
    input_snapshot JSON NOT NULL,
    output_snapshot JSON NULL,
    context_summary JSON NOT NULL,
    tool_summary JSON NOT NULL,
    token_usage JSON NOT NULL,
    retry_records JSON NOT NULL,
    degradation_records JSON NOT NULL,
    validation_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    event_write_failed TINYINT(1) NOT NULL DEFAULT 0,
    error_code VARCHAR(128) NULL,
    error_detail VARCHAR(2000) NULL,
    elapsed_ms INT UNSIGNED NULL,
    execution_mode VARCHAR(32) NOT NULL DEFAULT 'normal',
    idempotency_key VARCHAR(128) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_harness_traces_idempotency (user_id, interview_id, idempotency_key),
    KEY idx_harness_traces_interview_created (interview_id, created_at),
    KEY idx_harness_traces_node (interview_id, node_id, node_type),
    KEY idx_harness_traces_status (status),
    KEY idx_harness_traces_source (source_trace_id),
    CONSTRAINT fk_harness_traces_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_harness_traces_interview_id
        FOREIGN KEY (interview_id) REFERENCES interviews (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_harness_traces_round_id
        FOREIGN KEY (round_id) REFERENCES interview_rounds (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_harness_traces_source_trace_id
        FOREIGN KEY (source_trace_id) REFERENCES harness_traces (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS harness_trace_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    trace_id BIGINT UNSIGNED NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'succeeded',
    payload JSON NOT NULL,
    error_message VARCHAR(1000) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_harness_trace_events_trace_created (trace_id, created_at),
    KEY idx_harness_trace_events_type (event_type),
    CONSTRAINT fk_harness_trace_events_trace_id
        FOREIGN KEY (trace_id) REFERENCES harness_traces (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS harness_checkpoints (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    interview_id BIGINT UNSIGNED NOT NULL,
    round_id BIGINT UNSIGNED NULL,
    trace_id BIGINT UNSIGNED NULL,
    node_id VARCHAR(128) NOT NULL,
    checkpoint_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'available',
    snapshot JSON NOT NULL,
    resume_version VARCHAR(64) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_harness_checkpoints_interview_created (interview_id, created_at),
    KEY idx_harness_checkpoints_node (interview_id, node_id, checkpoint_type),
    CONSTRAINT fk_harness_checkpoints_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_harness_checkpoints_interview_id
        FOREIGN KEY (interview_id) REFERENCES interviews (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_harness_checkpoints_round_id
        FOREIGN KEY (round_id) REFERENCES interview_rounds (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_harness_checkpoints_trace_id
        FOREIGN KEY (trace_id) REFERENCES harness_traces (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS harness_replay_runs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    interview_id BIGINT UNSIGNED NOT NULL,
    source_trace_id BIGINT UNSIGNED NOT NULL,
    new_trace_id BIGINT UNSIGNED NULL,
    mode VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    parameters JSON NOT NULL,
    result_snapshot JSON NULL,
    diff_summary JSON NOT NULL,
    error_message VARCHAR(1000) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY idx_harness_replay_runs_source (source_trace_id),
    KEY idx_harness_replay_runs_interview_created (interview_id, created_at),
    CONSTRAINT fk_harness_replay_runs_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_harness_replay_runs_interview_id
        FOREIGN KEY (interview_id) REFERENCES interviews (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_harness_replay_runs_source_trace_id
        FOREIGN KEY (source_trace_id) REFERENCES harness_traces (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_harness_replay_runs_new_trace_id
        FOREIGN KEY (new_trace_id) REFERENCES harness_traces (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS harness_rule_evaluations (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    interview_id BIGINT UNSIGNED NOT NULL,
    trace_id BIGINT UNSIGNED NULL,
    replay_run_id BIGINT UNSIGNED NULL,
    rule_name VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    evidence JSON NOT NULL,
    failure_reason VARCHAR(1000) NULL,
    overall_grade VARCHAR(32) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_harness_rule_evaluations_interview_created (interview_id, created_at),
    KEY idx_harness_rule_evaluations_trace (trace_id),
    KEY idx_harness_rule_evaluations_status (status, severity),
    CONSTRAINT fk_harness_rule_evaluations_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_harness_rule_evaluations_interview_id
        FOREIGN KEY (interview_id) REFERENCES interviews (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_harness_rule_evaluations_trace_id
        FOREIGN KEY (trace_id) REFERENCES harness_traces (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_harness_rule_evaluations_replay_run_id
        FOREIGN KEY (replay_run_id) REFERENCES harness_replay_runs (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS harness_improvement_candidates (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NULL,
    interview_id BIGINT UNSIGNED NULL,
    source_trace_id BIGINT UNSIGNED NULL,
    candidate_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'proposed',
    proposal JSON NOT NULL,
    sandbox_result JSON NULL,
    regression_result JSON NULL,
    approval_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    applied_version VARCHAR(64) NULL,
    rollback_point VARCHAR(128) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_harness_improvement_candidates_status (status, approval_status),
    KEY idx_harness_improvement_candidates_interview (interview_id),
    CONSTRAINT fk_harness_improvement_candidates_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_harness_improvement_candidates_interview_id
        FOREIGN KEY (interview_id) REFERENCES interviews (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_harness_improvement_candidates_source_trace_id
        FOREIGN KEY (source_trace_id) REFERENCES harness_traces (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS evolution_quality_signals (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    interview_id BIGINT UNSIGNED NOT NULL,
    version_bundle_id BIGINT UNSIGNED NULL,
    job_family VARCHAR(128) NULL,
    signal_type VARCHAR(64) NOT NULL,
    severity VARCHAR(32) NOT NULL DEFAULT 'info',
    metrics JSON NOT NULL,
    hard_trigger TINYINT(1) NOT NULL DEFAULT 0,
    threshold_trigger TINYINT(1) NOT NULL DEFAULT 0,
    source_refs JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_evolution_quality_signals_interview_type (interview_id, signal_type),
    KEY idx_evolution_quality_signals_user_created (user_id, created_at),
    KEY idx_evolution_quality_signals_bundle_created (version_bundle_id, created_at),
    KEY idx_evolution_quality_signals_trigger (hard_trigger, threshold_trigger, severity),
    CONSTRAINT fk_evolution_quality_signals_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_evolution_quality_signals_interview_id
        FOREIGN KEY (interview_id) REFERENCES interviews (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_evolution_quality_signals_version_bundle_id
        FOREIGN KEY (version_bundle_id) REFERENCES evolution_version_bundles (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS evolution_runs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NULL,
    dedupe_key VARCHAR(191) NULL,
    trigger_type VARCHAR(32) NOT NULL,
    trigger_reason VARCHAR(1000) NOT NULL,
    scope_type VARCHAR(32) NOT NULL DEFAULT 'global',
    scope_key VARCHAR(128) NULL,
    sample_count INT NOT NULL DEFAULT 0,
    data_scope JSON NOT NULL,
    anonymization_status VARCHAR(32) NOT NULL DEFAULT 'not_required',
    audit_metadata JSON NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME NULL,
    error_message VARCHAR(1000) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_evolution_runs_dedupe_key (dedupe_key),
    KEY idx_evolution_runs_user_started (user_id, started_at),
    KEY idx_evolution_runs_status_started (status, started_at),
    KEY idx_evolution_runs_trigger_started (trigger_type, started_at),
    KEY idx_evolution_runs_scope (scope_type, scope_key),
    CONSTRAINT fk_evolution_runs_user_id
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS evolution_candidates (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    run_id BIGINT UNSIGNED NOT NULL,
    candidate_type VARCHAR(64) NOT NULL,
    target_artifact_key VARCHAR(128) NULL,
    risk_level VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending_validation',
    proposal JSON NOT NULL,
    diff JSON NOT NULL,
    impact_scope JSON NOT NULL,
    root_cause JSON NOT NULL,
    validation_summary JSON NULL,
    approval_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    approved_by BIGINT UNSIGNED NULL,
    approved_at DATETIME NULL,
    manual_note TEXT NULL,
    rollback_point JSON NULL,
    application_result JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_evolution_candidates_run_id (run_id),
    KEY idx_evolution_candidates_status_risk (status, risk_level),
    KEY idx_evolution_candidates_type (candidate_type),
    CONSTRAINT fk_evolution_candidates_run_id
        FOREIGN KEY (run_id) REFERENCES evolution_runs (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE evolution_runs
    ADD COLUMN IF NOT EXISTS user_id BIGINT UNSIGNED NULL,
    ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(191) NULL,
    ADD COLUMN IF NOT EXISTS audit_metadata JSON NULL;

ALTER TABLE evolution_candidates
    ADD COLUMN IF NOT EXISTS application_result JSON NULL;

CREATE TABLE IF NOT EXISTS evolution_validation_runs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    candidate_id BIGINT UNSIGNED NOT NULL,
    validation_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    sample_count INT NOT NULL DEFAULT 0,
    baseline_bundle_id BIGINT UNSIGNED NULL,
    candidate_bundle_id BIGINT UNSIGNED NULL,
    hard_rule_result JSON NOT NULL,
    soft_rule_diff JSON NOT NULL,
    schema_result JSON NOT NULL,
    api_contract_result JSON NOT NULL,
    report_quality_diff JSON NOT NULL,
    repeat_rate_diff JSON NOT NULL,
    score_distribution_diff JSON NOT NULL,
    test_result JSON NOT NULL,
    details JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_evolution_validation_runs_candidate (candidate_id, created_at),
    KEY idx_evolution_validation_runs_status (status),
    CONSTRAINT fk_evolution_validation_runs_candidate_id
        FOREIGN KEY (candidate_id) REFERENCES evolution_candidates (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_evolution_validation_runs_baseline_bundle_id
        FOREIGN KEY (baseline_bundle_id) REFERENCES evolution_version_bundles (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_evolution_validation_runs_candidate_bundle_id
        FOREIGN KEY (candidate_bundle_id) REFERENCES evolution_version_bundles (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS evolution_audit_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(100) NOT NULL,
    run_id BIGINT UNSIGNED NULL,
    candidate_id BIGINT UNSIGNED NULL,
    validation_run_id BIGINT UNSIGNED NULL,
    version_bundle_id BIGINT UNSIGNED NULL,
    actor_user_id BIGINT UNSIGNED NULL,
    metadata JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_evolution_audit_events_run_created (run_id, created_at),
    KEY idx_evolution_audit_events_candidate_created (candidate_id, created_at),
    KEY idx_evolution_audit_events_type_created (event_type, created_at),
    KEY idx_evolution_audit_events_actor_created (actor_user_id, created_at),
    CONSTRAINT fk_evolution_audit_events_run_id
        FOREIGN KEY (run_id) REFERENCES evolution_runs (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_evolution_audit_events_candidate_id
        FOREIGN KEY (candidate_id) REFERENCES evolution_candidates (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_evolution_audit_events_validation_run_id
        FOREIGN KEY (validation_run_id) REFERENCES evolution_validation_runs (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_evolution_audit_events_version_bundle_id
        FOREIGN KEY (version_bundle_id) REFERENCES evolution_version_bundles (id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_evolution_audit_events_actor_user_id
        FOREIGN KEY (actor_user_id) REFERENCES users (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO evolution_version_bundles (
    bundle_key, parent_bundle_id, scope_type, scope_key, status, risk_level,
    content_hash, diff, validation_summary, rollback_point, activated_at
)
VALUES (
    'global-default-v3.2-bootstrap',
    NULL,
    'global',
    NULL,
    'active',
    'low',
    SHA2('global-default-v3.2-bootstrap', 256),
    JSON_OBJECT('reason', 'v3.2 bootstrap default bundle'),
    JSON_OBJECT('status', 'bootstrap', 'phase', 'stage_1'),
    JSON_OBJECT('type', 'bootstrap_default'),
    CURRENT_TIMESTAMP
);

UPDATE interviews
SET version_bundle_id = (
    SELECT id
    FROM evolution_version_bundles
    WHERE bundle_key = 'global-default-v3.2-bootstrap'
    LIMIT 1
)
WHERE version_bundle_id IS NULL;
