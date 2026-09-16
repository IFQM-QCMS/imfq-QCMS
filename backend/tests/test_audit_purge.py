import pytest
from datetime import datetime, timedelta, timezone
from app import db
from app.infrastructure.database.models.audit import AuditLog


def test_purge_preview_default_and_custom_date(client, super_admin_context):
    headers = super_admin_context['headers']
    user = super_admin_context['user']

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Seed test audit log entries
    log_old = AuditLog(
        user_id=user.id,
        action="TEST_ACTION_OLD",
        created_at=now - timedelta(days=400)
    )
    log_recent = AuditLog(
        user_id=user.id,
        action="TEST_ACTION_RECENT",
        created_at=now - timedelta(days=2)
    )
    db.session.add(log_old)
    db.session.add(log_recent)
    db.session.commit()

    # 1. Default preview (7 years ago) -> recent logs not included
    res_default = client.get('/api/admin/audit/purge-preview', headers=headers)
    assert res_default.status_code == 200
    data_default = res_default.get_json()
    assert data_default['status'] == 'success'
    assert 'cutoff_date' in data_default

    # 2. Query with retention_years=1 -> log_old should match
    res_1yr = client.get('/api/admin/audit/purge-preview?retention_years=1', headers=headers)
    assert res_1yr.status_code == 200
    data_1yr = res_1yr.get_json()
    assert data_1yr['status'] == 'success'
    assert data_1yr['match_count'] >= 1

    # 3. Query with custom before_date (today formatted as YYYY-MM-DD)
    today_str = now.strftime('%Y-%m-%d')
    res_custom = client.get(f'/api/admin/audit/purge-preview?before_date={today_str}', headers=headers)
    assert res_custom.status_code == 200
    data_custom = res_custom.get_json()
    assert data_custom['status'] == 'success'
    assert data_custom['cutoff_date'] == today_str
    # Both old and recent logs should match since cutoff is end of today
    assert data_custom['match_count'] >= 2


def test_purge_audit_logs_execution(client, super_admin_context):
    headers = super_admin_context['headers']
    user = super_admin_context['user']

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Seed an audit log from 10 days ago
    past_date = now - timedelta(days=10)
    test_log = AuditLog(
        user_id=user.id,
        action="PURGE_TEST_ENTRY",
        created_at=past_date
    )
    db.session.add(test_log)
    db.session.commit()
    log_id = test_log.id

    # Purge with before_date set to 5 days ago
    cutoff_str = (now - timedelta(days=5)).strftime('%Y-%m-%d')
    res = client.post('/api/admin/audit/purge', json={"before_date": cutoff_str}, headers=headers)
    assert res.status_code == 200

    # Verify the test log was deleted
    deleted_check = db.session.get(AuditLog, log_id)
    assert deleted_check is None
