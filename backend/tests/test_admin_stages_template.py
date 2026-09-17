import pytest
from flask_jwt_extended import create_access_token
from app.infrastructure.database.models.models import User, Role, Organization, PlatformSettings

def test_get_stages_template_super_admin(client, super_admin_context):
    """Ensure SuperAdmin with org_id=None gets 200 and stages config without error."""
    headers = super_admin_context['headers']

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


def test_get_stages_template_org_admin(client, auth_context):
    """Ensure Org Admin with valid org_id gets 200 and stages config."""
    headers = auth_context['headers']

    res = client.get('/api/admin/stages-template', headers=headers)
    assert res.status_code == 200
    data = res.get_json()
    assert 'stages' in data
    assert isinstance(data['stages'], list)
    assert len(data['stages']) >= 8
