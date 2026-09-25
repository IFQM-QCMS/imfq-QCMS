import pytest
from app.utils.pdf_filler import extract_evidence_photos, generate_evidence_collage_html
from pdf_template_helper import extract_evidence_photos as helper_extract, generate_evidence_collage_html as helper_collage

def test_extract_evidence_photos_before_and_after():
    d2 = {
        'current_state': {
            'media_files': [
                {'name': 'bef.png', 'url': '/uploads/project_evidence/ev_20260828_054804_pc04_before_defect_trend.jpg'}
            ]
        }
    }
    d6 = {
        'implementation_evidence': [
            {
                'document_name': 'pc04_voltage_trigger_config',
                'link': 'Evidence Repository',
                'uploaded_by': 'Pooja Bhatt',
                'file_url': '/uploads/project_evidence/ev_20260828_054804_pc04_electrode_wear.jpg',
                'file_name': 'pc04_voltage_trigger_config.jpg'
            }
        ]
    }

    # Test pdf_filler
    photos = extract_evidence_photos(d2, d6)
    assert len(photos) == 2, f"Expected 2 photos (Before + After), got {len(photos)}"
    assert photos[0]['tag'] == 'Before'
    assert photos[0]['stage'] == 'Stage 2.7'
    assert photos[1]['tag'] == 'After'
    assert photos[1]['stage'] == 'Stage 6.6'
    assert 'Pooja Bhatt' in photos[1]['name']
    assert photos[0]['url'].startswith('data:image/')
    assert photos[1]['url'].startswith('data:image/')

    html_out = generate_evidence_collage_html(1, d2, d6)
    assert 'Stage 2.7: Before Evidence' in html_out
    assert 'Stage 6.6: Implementation Proof' in html_out
    assert 'Total Evidence Photos: 2' in html_out

    # Test pdf_template_helper
    h_photos = helper_extract(d2, d6)
    assert len(h_photos) == 2
    assert h_photos[1]['tag'] == 'After'
    assert h_photos[1]['url'].startswith('data:image/')

    h_html = helper_collage(1, d2, d6)
    assert 'Stage 6.6: Implementation Proof' in h_html


def test_extract_evidence_photos_disk_lookup_fallback():
    """Verify that when file_url is missing and link='Evidence Repository', disk lookup finds matching image."""
    d2 = {
        'current_state': {
            'media_files': [
                {'name': 'bef.png', 'url': '/uploads/project_evidence/ev_20260828_054804_pc04_before_defect_trend.jpg'}
            ]
        }
    }
    d6 = {
        'implementation_evidence': [
            {
                'document_name': 'pc04_electrode_wear',
                'link': 'Evidence Repository',
                'uploaded_by': 'Pooja Bhatt'
            }
        ]
    }

    photos = extract_evidence_photos(d2, d6)
    assert len(photos) == 2
    assert photos[1]['tag'] == 'After'
    assert photos[1]['stage'] == 'Stage 6.6'
    assert photos[1]['url'].startswith('data:image/')


def test_extract_countermeasure_and_verification_evidence():
    """Verify that countermeasure actions and Stage 7 verification evidence photos are captured."""
    d2 = {}
    d6 = {
        'countermeasures': [
            {'action': 'Replace Bushings', 'photo': '/uploads/project_evidence/ev_20260903_062525_pr05_bushings_replaced.jpg', 'owner': 'Pooja Bhatt'}
        ]
    }
    d7 = {
        'verification_evidence': [
            {'name': 'Post-Fix Verification', 'file_url': '/uploads/project_evidence/ev_20260828_054804_pc04_electrode_wear.jpg'}
        ]
    }

    photos = extract_evidence_photos(d2, d6, d7)
    assert len(photos) == 2
    tags = [p['tag'] for p in photos]
    assert tags == ['After', 'After']
    assert any('Replace Bushings' in p['name'] for p in photos)
    assert any('Post-Fix Verification' in p['name'] for p in photos)
