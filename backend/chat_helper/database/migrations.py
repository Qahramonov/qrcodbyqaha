"""Versioned schema migrations. Each migration runs in its own transaction and is recorded once."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from .db import Database

log = logging.getLogger(__name__)

M001_CORE = r"""
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    language TEXT NOT NULL DEFAULT 'ru',
    status TEXT NOT NULL DEFAULT 'active',
    restricted_reason TEXT,
    bot_blocked INTEGER NOT NULL DEFAULT 0,
    broadcast_opt_in INTEGER NOT NULL DEFAULT 1,
    referrer_id INTEGER,
    created_at INTEGER NOT NULL,
    last_seen_at INTEGER
);
CREATE INDEX IF NOT EXISTS ix_users_last_seen ON users(last_seen_at);
CREATE INDEX IF NOT EXISTS ix_users_username ON users(username);

CREATE TABLE IF NOT EXISTS business_connections (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_chat_id INTEGER NOT NULL,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'connected',
    paused INTEGER NOT NULL DEFAULT 0,
    connected_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    last_event_at INTEGER,
    disconnected_at INTEGER,
    messages_in INTEGER NOT NULL DEFAULT 0,
    messages_out INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_bc_user ON business_connections(user_id);

CREATE TABLE IF NOT EXISTS business_rights (
    connection_id TEXT PRIMARY KEY REFERENCES business_connections(id) ON DELETE CASCADE,
    rights_json TEXT NOT NULL DEFAULT '{}',
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, key)
);

CREATE TABLE IF NOT EXISTS admin_roles (
    user_id INTEGER PRIMARY KEY,
    role TEXT NOT NULL CHECK (role IN ('super_admin','moderator')),
    granted_by INTEGER,
    granted_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id TEXT NOT NULL,
    device_name TEXT,
    platform TEXT,
    app_version TEXT,
    access_hash TEXT NOT NULL UNIQUE,
    refresh_hash TEXT NOT NULL UNIQUE,
    created_at INTEGER NOT NULL,
    last_used_at INTEGER,
    last_ip TEXT,
    access_expires_at INTEGER NOT NULL,
    refresh_expires_at INTEGER NOT NULL,
    revoked_at INTEGER,
    revoke_reason TEXT
);
CREATE INDEX IF NOT EXISTS ix_sessions_user ON admin_sessions(user_id);

CREATE TABLE IF NOT EXISTS pairing_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_hash TEXT NOT NULL UNIQUE,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    used_at INTEGER,
    attempts INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS login_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    ip TEXT,
    device_name TEXT,
    success INTEGER NOT NULL,
    reason TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_login_created ON login_events(created_at);

CREATE TABLE IF NOT EXISTS module_settings (
    user_id INTEGER NOT NULL,
    module TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    config_json TEXT NOT NULL DEFAULT '{}',
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, module)
);

CREATE TABLE IF NOT EXISTS chat_settings (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chat_id INTEGER NOT NULL,
    title TEXT,
    username TEXT,
    is_bot INTEGER NOT NULL DEFAULT 0,
    ai_enabled INTEGER,
    afk_enabled INTEGER,
    autoreply_enabled INTEGER,
    language TEXT,
    style TEXT,
    reply_limit INTEGER,
    priority INTEGER NOT NULL DEFAULT 0,
    manual_confirm INTEGER,
    muted_until INTEGER,
    ignored INTEGER NOT NULL DEFAULT 0,
    whitelisted INTEGER NOT NULL DEFAULT 0,
    tags_json TEXT NOT NULL DEFAULT '[]',
    first_seen_at INTEGER,
    last_incoming_at INTEGER,
    last_outgoing_at INTEGER,
    owner_paused_until INTEGER,
    unanswered INTEGER NOT NULL DEFAULT 0,
    last_preview TEXT,
    priority_score INTEGER NOT NULL DEFAULT 0,
    auto_replies_today INTEGER NOT NULL DEFAULT 0,
    auto_replies_day TEXT,
    last_auto_reply_at INTEGER,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, chat_id)
);
CREATE INDEX IF NOT EXISTS ix_chat_incoming ON chat_settings(user_id, last_incoming_at);

CREATE TABLE IF NOT EXISTS chat_permissions (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chat_id INTEGER NOT NULL,
    permission TEXT NOT NULL,
    allowed INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, chat_id, permission)
);

CREATE TABLE IF NOT EXISTS command_registry (
    command_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    min_plan TEXT NOT NULL DEFAULT 'free',
    enabled_global INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'IMPLEMENTED',
    calls INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    last_used_at INTEGER,
    synced_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS command_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    connection_id TEXT,
    chat_id INTEGER,
    command_id TEXT NOT NULL,
    source TEXT NOT NULL,
    ok INTEGER NOT NULL,
    error TEXT,
    duration_ms INTEGER,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_cmdhist_user ON command_history(user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_cmdhist_cmd ON command_history(command_id, created_at);

CREATE TABLE IF NOT EXISTS custom_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    actions_json TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    uses INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS ai_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'auto',
    model TEXT,
    mode TEXT NOT NULL DEFAULT 'friendly',
    system_prompt TEXT,
    temperature REAL,
    max_tokens INTEGER NOT NULL DEFAULT 600,
    language TEXT NOT NULL DEFAULT 'auto',
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_aiprof_user ON ai_profiles(user_id);

CREATE TABLE IF NOT EXISTS ai_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_aihist_chat ON ai_history(user_id, chat_id, id);

CREATE TABLE IF NOT EXISTS ai_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chat_id INTEGER,
    kind TEXT NOT NULL DEFAULT 'fact',
    content TEXT NOT NULL,
    source TEXT,
    created_at INTEGER NOT NULL,
    expires_at INTEGER
);
CREATE INDEX IF NOT EXISTS ix_aimem_user ON ai_memory(user_id, chat_id);

CREATE TABLE IF NOT EXISTS ai_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    model TEXT,
    kind TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    latency_ms INTEGER,
    ok INTEGER NOT NULL,
    error TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_aiusage_user ON ai_usage(user_id, created_at);

CREATE TABLE IF NOT EXISTS ai_costs (
    user_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    requests INTEGER NOT NULL DEFAULT 0,
    tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);

CREATE TABLE IF NOT EXISTS ai_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    connection_id TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    reply_to_message_id INTEGER,
    incoming_text TEXT,
    draft_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at INTEGER NOT NULL,
    decided_at INTEGER
);
CREATE INDEX IF NOT EXISTS ix_drafts_user ON ai_drafts(user_id, status);

CREATE TABLE IF NOT EXISTS afk_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reason TEXT,
    kind TEXT NOT NULL DEFAULT 'afk',
    started_at INTEGER NOT NULL,
    ends_at INTEGER,
    ended_at INTEGER,
    replies_sent INTEGER NOT NULL DEFAULT 0,
    messages_received INTEGER NOT NULL DEFAULT 0,
    chats_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_afk_user ON afk_sessions(user_id, ended_at);

CREATE TABLE IF NOT EXISTS autoresponse_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT,
    trigger_type TEXT NOT NULL,
    pattern TEXT,
    match_mode TEXT NOT NULL DEFAULT 'contains',
    response TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 0,
    cooldown_sec INTEGER NOT NULL DEFAULT 300,
    chat_filter_json TEXT NOT NULL DEFAULT '{}',
    schedule_json TEXT NOT NULL DEFAULT '{}',
    hits INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ar_user ON autoresponse_rules(user_id, enabled);

CREATE TABLE IF NOT EXISTS reply_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS automation_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    trigger_json TEXT NOT NULL,
    conditions_json TEXT NOT NULL DEFAULT '[]',
    actions_json TEXT NOT NULL,
    cooldown_sec INTEGER NOT NULL DEFAULT 60,
    template_id TEXT,
    run_count INTEGER NOT NULL DEFAULT 0,
    last_run_at INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_auto_user ON automation_rules(user_id, enabled);

CREATE TABLE IF NOT EXISTS automation_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL REFERENCES automation_rules(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    chat_id INTEGER,
    status TEXT NOT NULL,
    detail TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_autoexec_rule ON automation_executions(rule_id, created_at);
CREATE INDEX IF NOT EXISTS ix_autoexec_user ON automation_executions(user_id, created_at);

CREATE TABLE IF NOT EXISTS media_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    chat_id INTEGER,
    kind TEXT NOT NULL,
    params_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    input_size INTEGER,
    output_size INTEGER,
    created_at INTEGER NOT NULL,
    started_at INTEGER,
    finished_at INTEGER
);
CREATE INDEX IF NOT EXISTS ix_media_user ON media_jobs(user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_media_status ON media_jobs(status);

CREATE TABLE IF NOT EXISTS game_sessions (
    id TEXT PRIMARY KEY,
    owner_id INTEGER NOT NULL,
    connection_id TEXT,
    chat_id INTEGER NOT NULL,
    message_id INTEGER,
    game TEXT NOT NULL,
    state_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_games_owner ON game_sessions(owner_id, status);
CREATE INDEX IF NOT EXISTS ix_games_chat ON game_sessions(chat_id, status);

CREATE TABLE IF NOT EXISTS game_players (
    session_id TEXT NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL,
    name TEXT,
    role TEXT,
    joined_at INTEGER NOT NULL,
    PRIMARY KEY (session_id, player_id)
);

CREATE TABLE IF NOT EXISTS game_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    owner_id INTEGER NOT NULL,
    game TEXT NOT NULL,
    winner_id INTEGER,
    loser_id INTEGER,
    draw INTEGER NOT NULL DEFAULT 0,
    score_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_gres_owner ON game_results(owner_id, game, created_at);

CREATE TABLE IF NOT EXISTS game_ratings (
    owner_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    game TEXT NOT NULL,
    name TEXT,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    draws INTEGER NOT NULL DEFAULT 0,
    best_ms INTEGER,
    rating INTEGER NOT NULL DEFAULT 1000,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (owner_id, player_id, game)
);

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    run_at INTEGER NOT NULL,
    repeat_sec INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    dedup_key TEXT UNIQUE,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sched_due ON scheduled_tasks(status, run_at);

CREATE TABLE IF NOT EXISTS subscription_plans (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    price_stars INTEGER NOT NULL DEFAULT 0,
    duration_days INTEGER NOT NULL DEFAULT 30,
    limits_json TEXT NOT NULL DEFAULT '{}',
    modules_json TEXT NOT NULL DEFAULT '[]',
    description TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    sort INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id TEXT NOT NULL REFERENCES subscription_plans(id),
    status TEXT NOT NULL DEFAULT 'active',
    source TEXT NOT NULL,
    started_at INTEGER NOT NULL,
    expires_at INTEGER,
    granted_by INTEGER,
    payment_id INTEGER,
    note TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_subs_user ON subscriptions(user_id, status);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plan_id TEXT,
    amount INTEGER NOT NULL,
    currency TEXT NOT NULL,
    payload TEXT NOT NULL,
    telegram_charge_id TEXT UNIQUE,
    provider_charge_id TEXT,
    status TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    refunded_at INTEGER
);
CREATE INDEX IF NOT EXISTS ix_pay_user ON payments(user_id, created_at);

CREATE TABLE IF NOT EXISTS promo_codes (
    code TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES subscription_plans(id),
    days INTEGER NOT NULL,
    max_uses INTEGER NOT NULL DEFAULT 1,
    used_count INTEGER NOT NULL DEFAULT 0,
    expires_at INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS promo_redemptions (
    code TEXT NOT NULL REFERENCES promo_codes(code) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    redeemed_at INTEGER NOT NULL,
    PRIMARY KEY (code, user_id)
);

CREATE TABLE IF NOT EXISTS referrals (
    referred_id INTEGER PRIMARY KEY,
    referrer_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    rewarded INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS notification_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    level TEXT NOT NULL DEFAULT 'info',
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    read_at INTEGER,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_notif_user ON notification_events(user_id, created_at);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    actor_type TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    details_json TEXT NOT NULL DEFAULT '{}',
    ip TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_created ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS ix_audit_target ON audit_logs(target_type, target_id);

CREATE TABLE IF NOT EXISTS system_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL,
    logger TEXT,
    message TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_syslog_created ON system_logs(created_at);

CREATE TABLE IF NOT EXISTS rate_limits (
    key TEXT PRIMARY KEY,
    window_start INTEGER NOT NULL,
    count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS feature_flags (
    key TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0,
    user_ids_json TEXT NOT NULL DEFAULT '[]',
    description TEXT,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_metrics (
    day TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (day, user_id, metric)
);
CREATE INDEX IF NOT EXISTS ix_metrics_metric ON daily_metrics(metric, day);

CREATE TABLE IF NOT EXISTS processed_updates (
    key TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_processed_created ON processed_updates(created_at);

CREATE TABLE IF NOT EXISTS broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_by INTEGER NOT NULL,
    text TEXT,
    media_type TEXT,
    media_file_id TEXT,
    buttons_json TEXT NOT NULL DEFAULT '[]',
    segment_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'draft',
    scheduled_at INTEGER,
    total INTEGER NOT NULL DEFAULT 0,
    sent INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    started_at INTEGER,
    finished_at INTEGER
);
CREATE TABLE IF NOT EXISTS broadcast_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    broadcast_id INTEGER NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    error TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS profile_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    source TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_profhist_user ON profile_history(user_id, created_at);
"""

M002_ACTIVITY = r"""
CREATE TABLE IF NOT EXISTS user_activity (
    user_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    events INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, day)
);
CREATE INDEX IF NOT EXISTS ix_activity_day ON user_activity(day);
CREATE INDEX IF NOT EXISTS ix_users_created ON users(created_at);
CREATE INDEX IF NOT EXISTS ix_payments_status ON payments(status, created_at)
"""

M003_V3 = r"""
CREATE TABLE IF NOT EXISTS chat_control_states (
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chat_id INTEGER NOT NULL,
    module TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    state_json TEXT NOT NULL DEFAULT '{}',
    until_at INTEGER,
    connection_id TEXT,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (owner_id, chat_id, module)
);
CREATE INDEX IF NOT EXISTS ix_ccs_until ON chat_control_states(until_at);
CREATE INDEX IF NOT EXISTS ix_ccs_module ON chat_control_states(module, enabled);

CREATE TABLE IF NOT EXISTS control_messages (
    token TEXT PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    connection_id TEXT,
    chat_id INTEGER NOT NULL,
    module TEXT NOT NULL,
    location TEXT NOT NULL CHECK (location IN ('chat','dm')),
    host_chat_id INTEGER NOT NULL,
    message_id INTEGER,
    version INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ctl_owner ON control_messages(owner_id, chat_id, module, status);

CREATE TABLE IF NOT EXISTS control_actions (
    callback_id TEXT PRIMARY KEY,
    token TEXT NOT NULL,
    actor_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    result TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ctlact_created ON control_actions(created_at);

CREATE TABLE IF NOT EXISTS mute_rules (
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chat_id INTEGER NOT NULL DEFAULT 0,
    types_json TEXT NOT NULL DEFAULT '["all"]',
    keep_types_json TEXT NOT NULL DEFAULT '[]',
    whitelist_json TEXT NOT NULL DEFAULT '[]',
    report INTEGER NOT NULL DEFAULT 1,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (owner_id, chat_id)
);

CREATE TABLE IF NOT EXISTS mute_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    msg_type TEXT,
    source TEXT NOT NULL,
    result TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_mute_events ON mute_events(owner_id, chat_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS ux_mute_events_msg ON mute_events(owner_id, chat_id, message_id, source);

CREATE TABLE IF NOT EXISTS ai_twin_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    mode TEXT NOT NULL DEFAULT 'disabled',
    name TEXT,
    language TEXT NOT NULL DEFAULT 'auto',
    manner TEXT,
    style TEXT NOT NULL DEFAULT 'friendly',
    formality INTEGER NOT NULL DEFAULT 50,
    humor INTEGER NOT NULL DEFAULT 30,
    length TEXT NOT NULL DEFAULT 'medium',
    emoji INTEGER NOT NULL DEFAULT 30,
    slang INTEGER NOT NULL DEFAULT 10,
    profanity_filter INTEGER NOT NULL DEFAULT 1,
    reply_delay_sec INTEGER NOT NULL DEFAULT 0,
    active_from TEXT,
    active_to TEXT,
    model TEXT,
    custom_prompt TEXT,
    persona TEXT NOT NULL DEFAULT 'neutral',
    examples_json TEXT NOT NULL DEFAULT '[]',
    consent_at INTEGER,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS animation_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    connection_id TEXT,
    chat_id INTEGER NOT NULL,
    message_id INTEGER,
    kind TEXT NOT NULL,
    speed TEXT NOT NULL,
    frames INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',
    error TEXT,
    created_at INTEGER NOT NULL,
    finished_at INTEGER
);
CREATE INDEX IF NOT EXISTS ix_anim_owner ON animation_jobs(owner_id, created_at);

CREATE TABLE IF NOT EXISTS repetition_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    connection_id TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    interval_sec INTEGER NOT NULL,
    ends_at INTEGER NOT NULL,
    last_message_id INTEGER,
    sends INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',
    error TEXT,
    created_at INTEGER NOT NULL,
    finished_at INTEGER
);
CREATE INDEX IF NOT EXISTS ix_rep_owner ON repetition_jobs(owner_id, created_at);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('dm','chat')),
    connection_id TEXT,
    chat_id INTEGER,
    text TEXT NOT NULL,
    run_at INTEGER NOT NULL,
    task_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    created_at INTEGER NOT NULL,
    done_at INTEGER
);
CREATE INDEX IF NOT EXISTS ix_reminders_owner ON reminders(owner_id, status, run_at);

CREATE TABLE IF NOT EXISTS permission_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id TEXT NOT NULL,
    owner_id INTEGER NOT NULL,
    is_enabled INTEGER NOT NULL,
    rights_json TEXT NOT NULL,
    status TEXT NOT NULL,
    change TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_permsnap_conn ON permission_snapshots(connection_id, created_at);

CREATE TABLE IF NOT EXISTS delegated_permissions (
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scope TEXT NOT NULL,
    granted_at INTEGER NOT NULL,
    expires_at INTEGER,
    revoked_at INTEGER,
    PRIMARY KEY (owner_id, scope)
);

CREATE TABLE IF NOT EXISTS delegation_consents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    scope TEXT NOT NULL,
    action TEXT NOT NULL,
    actor_id INTEGER NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_delegcons_owner ON delegation_consents(owner_id, created_at);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    outgoing INTEGER NOT NULL,
    msg_type TEXT,
    text TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_chatmsg_chat ON chat_messages(owner_id, chat_id, id);
CREATE INDEX IF NOT EXISTS ix_chatmsg_created ON chat_messages(created_at)
"""

MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "core_schema", M001_CORE),
    (2, "user_activity_analytics", M002_ACTIVITY),
    (3, "v3_chat_controls_mute_twin_reminders_delegation", M003_V3),
]


def _split(sql: str) -> list[str]:
    return [s.strip() for s in sql.split(";\n") if s.strip() and not s.strip().startswith("--")]


async def apply_migrations(db: Database, backup_dir: "Path | None" = None) -> list[int]:
    """Apply pending migrations in order. An existing database is backed up first (``pre_migration_v{N}``)."""
    await db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, "
                     "name TEXT NOT NULL, applied_at INTEGER NOT NULL)")
    done = {r["version"] for r in await db.fetchall("SELECT version FROM schema_migrations")}
    applied: list[int] = []
    pending = [m for m in MIGRATIONS if m[0] not in done]
    if pending and done and backup_dir is not None:
        target = Path(backup_dir) / time.strftime(f"chat_helper_%Y%m%d_%H%M%S_pre_migration_v{pending[0][0]}.db")
        await db.backup_to(target)
        log.info("database backed up before migration to %s", target)
    for version, name, sql in MIGRATIONS:
        if version in done:
            continue
        async with db.transaction() as tx:
            for stmt in _split(sql):
                await tx.execute(stmt)
            await tx.execute("INSERT INTO schema_migrations(version, name, applied_at) VALUES (?,?,?)",
                             (version, name, int(time.time())))
        log.info("applied migration %s %s", version, name)
        applied.append(version)
    return applied


async def current_version(db: Database) -> int:
    return int(await db.fetchval("SELECT MAX(version) FROM schema_migrations", default=0))
