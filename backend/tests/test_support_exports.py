import pytest
from app.infrastructure.database.models.models import db, SalesEnquiry, SupportTicket

def test_export_enquiries_endpoint(app, client, auth_context):
    """Verify that export_enquiries generates valid CSV data."""
    # Seed a test enquiry
    with app.app_context():
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


def test_get_ticket_details_without_attachments(app, client, auth_context):
    """Verify that tickets without attachments can be opened and retrieved with 200 OK."""
    with app.app_context():
        ticket = SupportTicket(
            subject="Cannot Open Ticket Bug Test",
            message="Testing opening a ticket with no attachments",
            priority="Medium",
            status="Open",
            category="Technical",
            user_id=auth_context['user'].id,
            org_id=auth_context['user'].org_id
        )
        db.session.add(ticket)
        db.session.commit()
        t_id = ticket.id

    res = client.get(f'/api/support/tickets/{t_id}', headers=auth_context['headers'])
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'success'
    assert data['data']['id'] == t_id
    assert data['data']['subject'] == "Cannot Open Ticket Bug Test"
    assert data['data']['attachments'] == []
    assert data['data']['requester']['name'] is not None

