import pytest
from app.infrastructure.database.models.models import db, SalesEnquiry, SupportTicket

def test_export_enquiries_endpoint(client, auth_context):
    """Verify that export_enquiries generates valid CSV data."""
    # Seed a test enquiry
    enquiry = SalesEnquiry(
        name="Test Lead",
        email="lead@example.com",
        phone="+91 9876543210",
        company_name="Acme Corp",
        status="New",
        source="Talk to Sales",
        message="Interested in Enterprise Plan",
        notes="High priority lead"
    )
    db.session.add(enquiry)
    db.session.commit()

    res = client.post('/api/support/enquiries/export', json={'status': 'All'}, headers=auth_context['headers'])
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'success'
    csv_text = data['csv']
    assert "Enquiry ID,Submitted Date,Prospect Name,Work Email" in csv_text
    assert "Test Lead" in csv_text
    assert "lead@example.com" in csv_text
    assert "Acme Corp" in csv_text

def test_export_tickets_endpoint(client, auth_context):
    """Verify that tickets export still functions correctly."""
    res = client.post('/api/support/tickets/export', json={}, headers=auth_context['headers'])
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'success'
    assert "Ticket ID,Ticket Number,Subject,Requester" in data['csv']
