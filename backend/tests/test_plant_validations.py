import pytest
from app.infrastructure.database.models.models import db, Plant, User

def test_plant_code_required_and_unique(client, auth_context):
    headers = auth_context['headers']

    # 1. Attempt to create plant without code -> 400 Bad Request
    res1 = client.post('/api/admin/plants', json={
        "name": "Validation Plant Alpha",
        "code": "",
        "location": "Sector 1"
    }, headers=headers)
    assert res1.status_code == 400
    assert "code" in res1.get_json()['message'].lower()

    # 2. Create plant with valid unique code
    res2 = client.post('/api/admin/plants', json={
        "name": "Validation Plant Alpha",
        "code": "VPA-01",
        "location": "Sector 1"
    }, headers=headers)
    assert res2.status_code == 201
    plant_a_id = res2.get_json()['plant']['id']

    # 3. Attempt to create another plant with same code (different case: vpa-01) -> 409 Conflict
    res3 = client.post('/api/admin/plants', json={
        "name": "Validation Plant Beta",
        "code": "vpa-01",
        "location": "Sector 2"
    }, headers=headers)
    assert res3.status_code == 409
    assert "already exists" in res3.get_json()['message'].lower()
    assert res3.get_json().get('field') == 'code'

    # 4. Create second plant with unique code
    res4 = client.post('/api/admin/plants', json={
        "name": "Validation Plant Beta",
        "code": "VPB-02",
        "location": "Sector 2"
    }, headers=headers)
    assert res4.status_code == 201
    plant_b_id = res4.get_json()['plant']['id']

    # 5. Attempt to update plant Beta to plant Alpha's code -> 409 Conflict
    res5 = client.put(f'/api/admin/plants/{plant_b_id}', json={
        "code": "VPA-01"
    }, headers=headers)
    assert res5.status_code == 409
    assert res5.get_json().get('field') == 'code'

    # 6. Updating plant Alpha keeping its own code -> 200 OK
    res6 = client.put(f'/api/admin/plants/{plant_a_id}', json={
        "code": "VPA-01",
        "name": "Validation Plant Alpha Updated"
    }, headers=headers)
    assert res6.status_code == 200
