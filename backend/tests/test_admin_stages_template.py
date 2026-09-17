import pytest
from flask_jwt_extended import create_access_token
from app.infrastructure.database.models.models import User, Role, Organization, PlatformSettings

def test_get_stages_template_super_admin(client, app):
    """Ensure SuperAdmin with org_id=None gets 200 and stages config without error."""
    with app.app_context():
        sa_user = User.query.filter_by(org_id=None).first()
        if not sa_user:
            sa_role = Role.query.filter_by(name='SuperAdmin').first()
            sa_user = User(
                username='sa_test_user',
                email='sa_test_user@octaqube.io',
                role_id=sa_role.id if sa_role else None,
                org_id=None
            )
            from app import db
            db.session.add(sa_user)
            db.session.commit()

        token = create_access_token(identity=str(sa_user.id))
        headers = {'Authorization': f'Bearer {token}'}

        res = client.get('/api/admin/stages-template', headers=headers)
        assert res.status_code == 200
        data = res.get_json()
        assert 'stages' in data
        assert isinstance(data['stages'], list)
        assert len(data['stages']) >= 8

        # Test status endpoint
        res_status = client.get('/api/admin/stages-template/status', headers=headers)
        assert res_status.status_code == 200
        assert res_status.get_json().get('status') == 'success'

        # Test diff endpoint
        res_diff = client.get('/api/admin/stages-template/diff', headers=headers)
        assert res_diff.status_code == 200
        assert res_diff.get_json().get('status') == 'success'

def test_get_stages_template_org_admin(client, app):
    """Ensure Org Admin with valid org_id gets 200 and stages config."""
    with app.app_context():
        admin_user = User.query.filter(User.org_id.isnot(None)).first()
        assert admin_user is not None, "At least one org user should exist"

        token = create_access_token(identity=str(admin_user.id))
        headers = {'Authorization': f'Bearer {token}'}

        res = client.get('/api/admin/stages-template', headers=headers)
        assert res.status_code == 200
        data = res.get_json()
        assert 'stages' in data
        assert isinstance(data['stages'], list)
        assert len(data['stages']) >= 8
