"""Enterprise schema sync

Revision ID: 0001_enterprise_schema_sync
Revises: 
Create Date: 2026-08-25
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_enterprise_schema_sync'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    statements = [
        # 1. STATE SYNCHRONIZATION (Reconcile organizations with active subscriptions)
        """
        UPDATE organizations o
        SET subscription_plan = COALESCE(sp.name, s.plan_name, o.subscription_plan),
            subscription_status = COALESCE(s.subscription_status, o.subscription_status)
        FROM subscriptions s
        LEFT JOIN saas_plans sp ON (
            (s.payg_rules->>'plan_id')::integer = sp.id 
            OR lower(s.plan_name) = lower(sp.name) 
            OR lower(s.plan_name) = lower(sp.code)
        )
        WHERE s.org_id = o.id 
          AND s.subscription_status IN ('Active', 'Trialing', 'Trial', 'Paid')
          AND (o.subscription_plan IS NULL OR o.subscription_plan != COALESCE(sp.name, s.plan_name) OR o.subscription_status != s.subscription_status);
        """,

        # 2. CONVERT FLOAT FINANCIAL COLUMNS TO NUMERIC(12, 2)
        """
        ALTER TABLE subscription_payments 
            ALTER COLUMN amount TYPE NUMERIC(12,2) USING COALESCE(amount, 0)::numeric(12,2),
            ALTER COLUMN final_amount TYPE NUMERIC(12,2) USING COALESCE(final_amount, 0)::numeric(12,2),
            ALTER COLUMN gst_amount TYPE NUMERIC(12,2) USING COALESCE(gst_amount, 0)::numeric(12,2),
            ALTER COLUMN gst_percent TYPE NUMERIC(5,2) USING COALESCE(gst_percent, 18.00)::numeric(5,2),
            ALTER COLUMN discount_amount TYPE NUMERIC(12,2) USING COALESCE(discount_amount, 0)::numeric(12,2),
            ALTER COLUMN refund_amount TYPE NUMERIC(12,2) USING COALESCE(refund_amount, 0)::numeric(12,2);
        """,
        """
        ALTER TABLE subscription_invoices 
            ALTER COLUMN base_amount TYPE NUMERIC(12,2) USING COALESCE(base_amount, 0)::numeric(12,2),
            ALTER COLUMN total_amount TYPE NUMERIC(12,2) USING COALESCE(total_amount, 0)::numeric(12,2),
            ALTER COLUMN gst_amount TYPE NUMERIC(12,2) USING COALESCE(gst_amount, 0)::numeric(12,2),
            ALTER COLUMN gst_percent TYPE NUMERIC(5,2) USING COALESCE(gst_percent, 18.00)::numeric(5,2),
            ALTER COLUMN discount_amount TYPE NUMERIC(12,2) USING COALESCE(discount_amount, 0)::numeric(12,2),
            ALTER COLUMN discount_percent TYPE NUMERIC(5,2) USING COALESCE(discount_percent, 0)::numeric(5,2);
        """,
        """
        ALTER TABLE subscriptions 
            ALTER COLUMN base_price TYPE NUMERIC(12,2) USING COALESCE(base_price, 0)::numeric(12,2),
            ALTER COLUMN final_amount TYPE NUMERIC(12,2) USING COALESCE(final_amount, 0)::numeric(12,2),
            ALTER COLUMN gst_amount TYPE NUMERIC(12,2) USING COALESCE(gst_amount, 0)::numeric(12,2);
        """,
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'subscription_refunds') THEN
                ALTER TABLE subscription_refunds ALTER COLUMN amount TYPE NUMERIC(12,2) USING COALESCE(amount, 0)::numeric(12,2);
            END IF;
        END $$;
        """,

        # 3. PRE-DEDUPLICATION BEFORE UNIQUE INDEX CREATION
        "DELETE FROM plants p1 USING plants p2 WHERE p1.id < p2.id AND p1.org_id = p2.org_id AND lower(p1.name) = lower(p2.name);",
        "DELETE FROM departments d1 USING departments d2 WHERE d1.id < d2.id AND d1.plant_id = d2.plant_id AND lower(d1.name) = lower(d2.name) AND d1.plant_id IS NOT NULL;",
        "DO $$ BEGIN IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'user_custom_fields') THEN DELETE FROM user_custom_fields c1 USING user_custom_fields c2 WHERE c1.id < c2.id AND c1.org_id = c2.org_id AND c1.field_key = c2.field_key; END IF; END $$;",
        "UPDATE subscription_invoices SET invoice_number = invoice_number || '-dup-' || id WHERE id IN (SELECT id FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY invoice_number ORDER BY id) as rnum FROM subscription_invoices WHERE invoice_number IS NOT NULL) s WHERE s.rnum > 1);",
        "UPDATE subscriptions SET subscription_status = 'Cancelled' WHERE id IN (SELECT id FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY org_id ORDER BY created_at DESC) as rnum FROM subscriptions WHERE subscription_status = 'Active') s WHERE s.rnum > 1);",
        "DELETE FROM project_reviews r1 USING project_reviews r2 WHERE r1.id < r2.id AND r1.project_id = r2.project_id AND r1.stage_number = r2.stage_number AND r1.reviewer_id = r2.reviewer_id;",

        # 4. HIGH-PERFORMANCE B-TREE INDEXES ON ALL HIGH-TRAFFIC FOREIGN KEYS
        "CREATE INDEX IF NOT EXISTS idx_projects_org_status_created ON projects(org_id, status, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_projects_creator_id ON projects(creator_id);",
        "CREATE INDEX IF NOT EXISTS idx_projects_dept_id ON projects(department_id);",
        "CREATE INDEX IF NOT EXISTS idx_project_members_user_proj ON project_members(user_id, project_id);",
        "CREATE INDEX IF NOT EXISTS idx_proj_stage_tracker ON project_stage_tracker(project_id, stage_number);",
        "CREATE INDEX IF NOT EXISTS idx_proj_workflow_stage ON project_workflow(project_id, stage_id);",
        "CREATE INDEX IF NOT EXISTS idx_project_reviews_proj_stage ON project_reviews(project_id, stage_number);",

        # 7 QC Tools Parent Lookups
        "DO $$ BEGIN IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'qc_fishbone_diagrams') THEN CREATE INDEX IF NOT EXISTS idx_qc_fishbone_proj ON qc_fishbone_diagrams(project_id); END IF; END $$;",
        "DO $$ BEGIN IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'qc_pareto_charts') THEN CREATE INDEX IF NOT EXISTS idx_qc_pareto_proj ON qc_pareto_charts(project_id); END IF; END $$;",
        "DO $$ BEGIN IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'qc_control_charts') THEN CREATE INDEX IF NOT EXISTS idx_qc_control_proj ON qc_control_charts(project_id); END IF; END $$;",
        "DO $$ BEGIN IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'qc_check_sheets') THEN CREATE INDEX IF NOT EXISTS idx_qc_checksheet_proj ON qc_check_sheets(project_id); END IF; END $$;",
        "DO $$ BEGIN IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'qc_scatter_diagrams') THEN CREATE INDEX IF NOT EXISTS idx_qc_scatter_proj ON qc_scatter_diagrams(project_id); END IF; END $$;",
        "DO $$ BEGIN IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'qc_stratifications') THEN CREATE INDEX IF NOT EXISTS idx_qc_strat_proj ON qc_stratifications(project_id); END IF; END $$;",
        "DO $$ BEGIN IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'qc_process_maps') THEN CREATE INDEX IF NOT EXISTS idx_qc_procmap_proj ON qc_process_maps(project_id); END IF; END $$;",

        # User & Authentication Lookups
        "CREATE INDEX IF NOT EXISTS idx_users_org_email_status ON users(org_id, email, status);",
        "CREATE INDEX IF NOT EXISTS idx_users_role_id ON users(role_id);",
        "CREATE INDEX IF NOT EXISTS idx_users_plant_id ON users(plant_id);",
        "CREATE INDEX IF NOT EXISTS idx_users_dept_id ON users(department_id);",

        # Billing & Invoicing Lookups
        "CREATE INDEX IF NOT EXISTS idx_sub_invoices_org_status_due ON subscription_invoices(org_id, invoice_status, due_date);",
        "CREATE INDEX IF NOT EXISTS idx_sub_payments_status_org_date ON subscription_payments(payment_status, org_id, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_subscriptions_org_status ON subscriptions(org_id, subscription_status);",
        "DO $$ BEGIN IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'invoice_items') THEN CREATE INDEX IF NOT EXISTS idx_invoice_items_inv_id ON invoice_items(invoice_id); END IF; END $$;",

        # SOP, Audit & Governance Lookups
        "CREATE INDEX IF NOT EXISTS idx_sop_master_org_id ON sop_master(org_id);",
        "DO $$ BEGIN IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'sop_steps') THEN CREATE INDEX IF NOT EXISTS idx_sop_steps_sop_id ON sop_steps(sop_id); END IF; END $$;",
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_org_created ON audit_logs(org_id, created_at DESC);",
        "DO $$ BEGIN IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'email_notification_logs') THEN CREATE INDEX IF NOT EXISTS idx_ann_delivery_user_status ON email_notification_logs(rule_id, status); END IF; END $$;",

        # 5. DATABASE-LEVEL UNIQUE CONSTRAINTS (PREVENT RACE-CONDITION DUPLICATE RECORDS)
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_plants_org_name ON plants(org_id, name);",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_departments_plant_name ON departments(plant_id, name) WHERE plant_id IS NOT NULL;",
        "DO $$ BEGIN IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'user_custom_fields') THEN CREATE UNIQUE INDEX IF NOT EXISTS uq_custom_fields_org_key ON user_custom_fields(org_id, field_key); END IF; END $$;",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_saas_plans_code ON saas_plans(code);",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_invoices_number ON subscription_invoices(invoice_number) WHERE invoice_number IS NOT NULL;",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_org_sub ON subscriptions(org_id) WHERE subscription_status = 'Active';",

        # 6. OTP NULLABILITY CONSTRAINTS
        "ALTER TABLE email_verifications ALTER COLUMN otp DROP NOT NULL;",
        "ALTER TABLE phone_verifications ALTER COLUMN otp DROP NOT NULL;"
    ]

    conn = op.get_bind()
    for stmt in statements:
        conn.execute(sa.text(stmt))


def downgrade():
    pass
