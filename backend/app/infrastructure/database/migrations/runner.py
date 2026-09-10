"""
QCMS Automated Database Schema Migration and Synchronization Runner
===================================================================
Invoked on container deploy:
    python -m app.infrastructure.database.migrations.runner

Tasks:
1. Executes db.create_all() to ensure all tables defined in SQLAlchemy models exist.
2. Inspects existing tables against model metadata and executes:
   ALTER TABLE "tablename" ADD COLUMN IF NOT EXISTS "columnname" <type>;
   for any column added to models that may be missing in existing production databases.
3. Automatically sets default values for newly added columns.
"""
import sys
import os
import logging
from sqlalchemy import inspect, text

logger = logging.getLogger('qcms.migration_runner')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] [SchemaRunner] %(message)s')

def sync_database_schema(app=None):
    if app is None:
        from app import create_app
        app = create_app()

    with app.app_context():
        from app.infrastructure.database.models.models import db
        dialect_name = db.engine.dialect.name
        logger.info(f"Starting database schema synchronization on dialect: {dialect_name}...")

        # Step 1: Create all tables defined in models that do not exist yet
        try:
            db.create_all()
            logger.info("db.create_all() successfully verified/created tables.")
        except Exception as e:
            logger.warning(f"db.create_all() encountered notice: {e}")

        # Step 2: Synchronize missing columns on existing tables
        try:
            inspector = inspect(db.engine)
            synced_columns = 0

            for table_name in db.metadata.tables.keys():
                try:
                    if not inspector.has_table(table_name):
                        continue

                    existing_cols = {c['name']: c for c in inspector.get_columns(table_name)}
                    model_table = db.metadata.tables[table_name]

                    for col in model_table.columns:
                        if col.name not in existing_cols:
                            col_type = col.type.compile(db.engine.dialect)
                            
                            # Compile safe ALTER TABLE statement
                            if dialect_name == 'postgresql':
                                sql = f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{col.name}" {col_type};'
                            elif dialect_name == 'sqlite':
                                sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {col_type};'
                            else:
                                sql = f'ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type};'

                            try:
                                db.session.execute(text(sql))
                                db.session.commit()
                                synced_columns += 1
                                logger.info(f"Added missing column: {table_name}.{col.name} ({col_type})")
                            except Exception as add_err:
                                db.session.rollback()
                                logger.warning(f"Could not add {table_name}.{col.name}: {add_err}")
                except Exception as t_err:
                    try:
                        db.session.rollback()
                    except Exception:
                        pass
                    logger.warning(f"Inspection error on table {table_name}: {t_err}")

            logger.info(f"Schema synchronization completed. Added {synced_columns} missing columns.")

            # Step 3: Default data normalization for core columns
            try:
                if dialect_name == 'postgresql':
                    db.session.execute(text("UPDATE organizations SET is_platform_org = FALSE WHERE is_platform_org IS NULL;"))
                    db.session.execute(text("UPDATE organizations SET is_deleted = FALSE WHERE is_deleted IS NULL;"))
                    db.session.execute(text("UPDATE organizations SET is_white_label = FALSE WHERE is_white_label IS NULL;"))
                    db.session.execute(text("UPDATE organizations SET api_access = FALSE WHERE api_access IS NULL;"))
                    db.session.execute(text("UPDATE organizations SET multi_plant = FALSE WHERE multi_plant IS NULL;"))
                    db.session.commit()
                    logger.info("Normalized null boolean flags in organizations.")
            except Exception as norm_err:
                db.session.rollback()
                logger.warning(f"Data normalization notice: {norm_err}")

        except Exception as e:
            logger.error(f"Schema synchronization error: {e}", exc_info=True)
            try:
                db.session.rollback()
            except Exception:
                pass

if __name__ == '__main__':
    sync_database_schema()
