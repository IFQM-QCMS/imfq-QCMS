import pytest
from app import db
from app.infrastructure.database.models.models import SaaSPlan, SaaSPlanPricing, SaaSPlanLimits, Organization, Subscription


def test_delete_plan_lifecycle(client, app, super_admin_context):
    with app.app_context():
        headers = super_admin_context['headers']

        # 1. Create a dummy plan to delete
        test_plan = SaaSPlan(
            name="Test Delete Plan Alpha",
            code="test_delete_plan_alpha",
            status="Active",
            plan_type="Custom",
            pricing_model="fixed"
        )
        db.session.add(test_plan)
        db.session.commit()
        plan_id = test_plan.id

        # Also add pricing & limits to test cascade delete
        pricing = SaaSPlanPricing(
            plan_id=plan_id,
            billing_cycle="Monthly",
            price=99.0
        )
        limits = SaaSPlanLimits(
            plan_id=plan_id,
            max_users=10
        )
        db.session.add(pricing)
        db.session.add(limits)
        db.session.commit()

        # 2. Delete the plan via DELETE /api/subscriptions/plans/<id>
        res = client.delete(f'/api/subscriptions/plans/{plan_id}', headers=headers)
        assert res.status_code == 200
        data = res.get_json()
        assert data['status'] == 'success'
        assert 'deleted successfully' in data['message'].lower()

        # 3. Verify it was removed from database along with cascades
        db.session.expire_all()
        deleted_plan = db.session.get(SaaSPlan, plan_id)
        assert deleted_plan is None
        assert SaaSPlanPricing.query.filter_by(plan_id=plan_id).count() == 0
        assert SaaSPlanLimits.query.filter_by(plan_id=plan_id).count() == 0


def test_delete_plan_protected_trial(client, app, super_admin_context):
    with app.app_context():
        headers = super_admin_context['headers']

        trial_plan = SaaSPlan(
            name="Test System Default Trial",
            code="trial_test_protected",
            status="Active",
            plan_type="Trial",
            is_default_trial=True
        )
        db.session.add(trial_plan)
        db.session.commit()
        plan_id = trial_plan.id

        res = client.delete(f'/api/subscriptions/plans/{plan_id}', headers=headers)
        assert res.status_code == 400
        data = res.get_json()
        assert 'default trial plan cannot be deleted' in data.get('error', '').lower()

        # Cleanup
        db.session.delete(trial_plan)
        db.session.commit()


def test_delete_plan_not_found(client, app, super_admin_context):
    with app.app_context():
        headers = super_admin_context['headers']
        res = client.delete('/api/subscriptions/plans/999999', headers=headers)
        assert res.status_code == 404
