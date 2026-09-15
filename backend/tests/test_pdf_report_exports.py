import pytest
from unittest.mock import patch
from app.infrastructure.database.models.models import Project, KPIMetric, Organization, db
from app.utils.report_gen import generate_pdf_summary


def test_generate_pdf_summary_no_fpdf_align_error(app, auth_context):
    """Verify that generate_pdf_summary runs cleanly without FPDF alignment error."""
    with app.app_context():
        p = Project.query.first()
        if not p:
            p = Project(
                org_id=auth_context['org_id'],
                title="Test Summary Project",
                status="Closed",
                project_uid="PRJ-SUMMARY-TEST"
            )
            db.session.add(p)
            db.session.commit()
        kpi = KPIMetric.query.filter_by(project_id=p.id).first()
        pdf_bytes = generate_pdf_summary(p, kpi, p.org_id)
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 0


def test_export_pdf_endpoint_multi_tier_fallback(client, auth_context):
    """Test PDF export endpoint with headless browser, PyMuPDF fallback, and FPDF fallback."""
    org_id = auth_context['org_id']
    with client.application.app_context():
        p = Project.query.filter_by(status='Closed', org_id=org_id).first()
        if not p:
            p = Project(
                org_id=org_id,
                title="Test Closed Project",
                status="Closed",
                project_uid="PRJ-TEST-EXP"
            )
            db.session.add(p)
            db.session.commit()
        project_id = p.id

    headers = auth_context['headers']

    # Tier 1: Normal generation (or PyMuPDF fallback if no browser)
    res1 = client.get(f'/api/reports/export/pdf/{project_id}', headers=headers)
    assert res1.status_code == 200
    assert res1.content_type == 'application/pdf'
    assert len(res1.data) > 0

    # Tier 2: Force browser failure -> PyMuPDF fallback
    with patch('app.utils.pdf_filler.render_html_to_pdf_browser', side_effect=RuntimeError('No browser')):
        res2 = client.get(f'/api/reports/export/pdf/{project_id}', headers=headers)
        assert res2.status_code == 200
        assert res2.content_type == 'application/pdf'
        assert len(res2.data) > 0

    # Tier 3: Force browser & PyMuPDF failure -> FPDF summary fallback
    with patch('app.utils.pdf_filler.render_html_to_pdf_browser', side_effect=RuntimeError('No browser')):
        with patch('app.utils.pdf_filler.render_html_to_pdf_pymupdf', side_effect=RuntimeError('PyMuPDF failed')):
            res3 = client.get(f'/api/reports/export/pdf/{project_id}', headers=headers)
            assert res3.status_code == 200
            assert res3.content_type == 'application/pdf'
            assert len(res3.data) > 0


def test_ceo_export_endpoint(client, auth_context):
    """Test CEO dashboard CSV export endpoint."""
    headers = auth_context['headers']
    res = client.get('/api/ceo/export', headers=headers)
    assert res.status_code == 200
    assert 'text/csv' in res.content_type
    assert len(res.data) > 0
