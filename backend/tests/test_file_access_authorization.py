import os
import pytest
from app import create_app, db
from app.infrastructure.database.models.models import (
    User, Organization, Role, Project, ProjectMember, SupportTicket, OfflinePaymentProof
)
from app.domain.services.file_access_service import verify_file_access_authorization, sanitize_file_path

def test_sanitize_file_path():
    assert sanitize_file_path('../../etc/passwd') is None
    assert sanitize_file_path('org_1/../../secret.txt') is None
    assert sanitize_file_path('/absolute/path.txt') is None
    assert sanitize_file_path('projects/org_55/proj_1/report.pdf') == 'projects/org_55/proj_1/report.pdf'
    assert sanitize_file_path('branding\\logo.png') == 'branding/logo.png'

def test_public_asset_authorization(app):
    with app.app_context():
        is_auth, reason, status = verify_file_access_authorization(
            user=None,
            file_path='branding/logo.png'
        )
        assert is_auth is True
        assert status == 200
        assert 'PUBLIC_ASSET' in reason

def test_unauthenticated_private_file_access(app):
    with app.app_context():
        is_auth, reason, status = verify_file_access_authorization(
            user=None,
            file_path='projects/org_55/proj_1/deliverable.pdf'
        )
        assert is_auth is False
        assert status == 401
        assert 'AUTHENTICATION_REQUIRED' in reason

@pytest.fixture
def file_auth_context(app):
    with app.app_context():
        org = Organization.query.filter_by(name="File Auth Test Org").first()
        if not org:
            org = Organization(name="File Auth Test Org", email="file_auth_org@test.org", subscription_plan="Enterprise")
            db.session.add(org)
            db.session.commit()

        admin_role = Role.query.filter_by(name='Admin').first()
        if not admin_role:
            admin_role = Role(name='Admin', description='Administrator')
            db.session.add(admin_role)
            db.session.commit()

        team_role = Role.query.filter_by(name='Team Member').first()
        if not team_role:
            team_role = Role(name='Team Member', description='Team Member')
            db.session.add(team_role)
            db.session.commit()

        admin_user = User.query.filter_by(email='file_admin@test.org').first()
        if not admin_user:
            admin_user = User(
                email='file_admin@test.org',
                username='file_admin',
                full_name='File Admin',
                org_id=org.id,
                role_id=admin_role.id,
                is_active=True,
                status='Active'
            )
            admin_user.set_password('Password123!')
            db.session.add(admin_user)

        team_user = User.query.filter_by(email='file_team@test.org').first()
        if not team_user:
            team_user = User(
                email='file_team@test.org',
                username='file_team',
                full_name='File Team',
                org_id=org.id,
                role_id=team_role.id,
                is_active=True,
                status='Active'
            )
            team_user.set_password('Password123!')
            db.session.add(team_user)

        other_user = User.query.filter_by(email='file_other@test.org').first()
        if not other_user:
            other_user = User(
                email='file_other@test.org',
                username='file_other',
                full_name='File Other',
                org_id=org.id,
                role_id=team_role.id,
                is_active=True,
                status='Active'
            )
            other_user.set_password('Password123!')
            db.session.add(other_user)

        db.session.commit()

        return {
            'org_id': org.id,
            'admin_user_id': admin_user.id,
            'team_user_id': team_user.id,
            'other_user_id': other_user.id,
        }

def test_cross_tenant_file_access_blocked(app, file_auth_context):
    with app.app_context():
        admin_user = db.session.get(User, file_auth_context['admin_user_id'])
        org_id = file_auth_context['org_id']
        assert admin_user is not None
        assert admin_user.org_id == org_id

        # Attempt to access Org 9999 file
        other_org_id = org_id + 9999
        is_auth, reason, status = verify_file_access_authorization(
            user=admin_user,
            file_path=f'projects/org_{other_org_id}/proj_10/confidential.pdf'
        )
        assert is_auth is False
        assert status == 403
        assert 'CROSS_TENANT_FORBIDDEN' in reason

def test_billing_invoice_permission_restricted_to_admin(app, file_auth_context):
    with app.app_context():
        admin_user = db.session.get(User, file_auth_context['admin_user_id'])
        team_user = db.session.get(User, file_auth_context['team_user_id'])
        org_id = file_auth_context['org_id']
        assert admin_user is not None
        assert team_user is not None

        # Admin accessing Org invoice
        is_auth, reason, status = verify_file_access_authorization(
            user=admin_user,
            file_path=f'invoices/org_{org_id}/inv_202608.pdf'
        )
        assert is_auth is True
        assert status == 200

        # Team member attempting to access Org invoice
        is_auth_tm, reason_tm, status_tm = verify_file_access_authorization(
            user=team_user,
            file_path=f'invoices/org_{org_id}/inv_202608.pdf'
        )
        assert is_auth_tm is False
        assert status_tm == 403
        assert 'BILLING_ACCESS_RESTRICTED' in reason_tm

def test_support_ticket_ownership_authorization(app, file_auth_context):
    with app.app_context():
        admin_user = db.session.get(User, file_auth_context['admin_user_id'])
        team_user = db.session.get(User, file_auth_context['team_user_id'])
        other_user = db.session.get(User, file_auth_context['other_user_id'])
        org_id = file_auth_context['org_id']

        ticket = SupportTicket.query.filter_by(org_id=org_id, user_id=team_user.id).first()
        if not ticket:
            ticket = SupportTicket(
                org_id=org_id,
                user_id=team_user.id,
                ticket_number='TICK-TEST-99',
                subject='Test Storage Issue',
                message='Testing storage access',
                priority='Low',
                status='Open'
            )
            db.session.add(ticket)
            db.session.commit()

        file_path = f'support/org_{org_id}/ticket_{ticket.id}/screenshot.png'

        # Ticket author can access
        is_auth, _, status = verify_file_access_authorization(user=team_user, file_path=file_path)
        assert is_auth is True
        assert status == 200

        # Admin can access
        is_auth_admin, _, status_admin = verify_file_access_authorization(user=admin_user, file_path=file_path)
        assert is_auth_admin is True
        assert status_admin == 200

        # Other regular team member cannot access
        is_auth_other, reason_other, status_other = verify_file_access_authorization(user=other_user, file_path=file_path)
        assert is_auth_other is False
        assert status_other == 403
        assert 'TICKET_OWNERSHIP_REQUIRED' in reason_other

@pytest.mark.skip(reason="[DEAD CODE - UNUSED BY FRONTEND / REMOVED FEATURE] signed-url endpoint was removed from storage routes.")
def test_signed_url_endpoint(client, app):
    with app.app_context():
        import uuid
        from flask_jwt_extended import create_access_token
        admin_user = User.query.filter_by(email='gelala@fxzig.com').first()
        team_user = User.query.filter_by(email='nitin.murthy9@example.com').first()
        
        admin_token = create_access_token(identity=str(admin_user.id), additional_claims={'session_id': str(uuid.uuid4())})
        team_token = create_access_token(identity=str(team_user.id), additional_claims={'session_id': str(uuid.uuid4())})

        # Admin requests invoice signed url
        res = client.post('/api/storage/signed-url', json={'file_path': 'invoices/org_55/inv_01.pdf'}, headers={'Authorization': f'Bearer {admin_token}'})
        # If file not in storage, returns 404, but auth passed (not 403)
        assert res.status_code in (200, 404)

        # Team user requests billing invoice signed url -> 403 Forbidden
        res_tm = client.post('/api/storage/signed-url', json={'file_path': 'invoices/org_55/inv_01.pdf'}, headers={'Authorization': f'Bearer {team_token}'})
        assert res_tm.status_code == 403
        assert 'BILLING_ACCESS_RESTRICTED' in res_tm.get_json()['message']

        # Cross-tenant request -> 403 Forbidden
        res_xt = client.post('/api/storage/signed-url', json={'file_path': 'projects/org_999/proj_1/specs.pdf'}, headers={'Authorization': f'Bearer {admin_token}'})
        assert res_xt.status_code == 403
        assert 'CROSS_TENANT_FORBIDDEN' in res_xt.get_json()['message']
