import pytest
from datetime import datetime, timezone
from app import db
from app.infrastructure.database.models.audit import AuditLog
from app.presentation.routes.audit_routes import extract_audit_diff_and_summary


def test_audit_diff_extracts_previous_values_correctly(app, super_admin_context):
    with app.app_context():
        user = super_admin_context['user']
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # 1. First login event for a test user
        log_login_1 = AuditLog(
            user_id=user.id,
            action="USER_LOGIN",
            target_table="users",
            target_id=user.id,
            ip_address="106.192.248.100",
            details={"username": user.username, "ip": "106.192.248.100"},
            created_at=now
        )
        db.session.add(log_login_1)
        db.session.commit()

        diffs_1, has_diff_1, summary_1 = extract_audit_diff_and_summary(log_login_1)
        assert has_diff_1 is True
        # For the first login, before is cleanly marked as First Login, never (Previous Value)
        assert "(Previous Value)" not in str(diffs_1)
        assert diffs_1["ip"]["after"] == "106.192.248.100"

        # 2. Second login event with a new IP
        log_login_2 = AuditLog(
            user_id=user.id,
            action="USER_LOGIN",
            target_table="users",
            target_id=user.id,
            ip_address="106.192.248.234",
            details={"username": user.username, "ip": "106.192.248.234"},
            created_at=now
        )
        db.session.add(log_login_2)
        db.session.commit()

        diffs_2, has_diff_2, summary_2 = extract_audit_diff_and_summary(log_login_2)
        assert has_diff_2 is True
        assert "(Previous Value)" not in str(diffs_2)
        # It must extract the real preceding IP!
        assert diffs_2["ip"]["before"] == "106.192.248.100"
        assert diffs_2["ip"]["after"] == "106.192.248.234"
        assert diffs_2["username"]["before"] == user.username
        assert diffs_2["username"]["after"] == user.username

        # 3. Entity creation followed by update
        log_create = AuditLog(
            user_id=user.id,
            action="CREATE_RECORD",
            target_table="test_items",
            target_id=9999,
            details={"title": "Original Title", "status": "Draft"},
            created_at=now
        )
        db.session.add(log_create)
        db.session.commit()

        log_update = AuditLog(
            user_id=user.id,
            action="UPDATE_RECORD",
            target_table="test_items",
            target_id=9999,
            details={"title": "Updated Title", "status": "Published"},
            created_at=now
        )
        db.session.add(log_update)
        db.session.commit()

        diffs_update, has_diff_up, summary_up = extract_audit_diff_and_summary(log_update)
        assert has_diff_up is True
        assert "(Previous Value)" not in str(diffs_update)
        assert diffs_update["title"]["before"] == "Original Title"
        assert diffs_update["title"]["after"] == "Updated Title"
        assert diffs_update["status"]["before"] == "Draft"
        assert diffs_update["status"]["after"] == "Published"
