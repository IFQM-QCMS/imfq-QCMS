from __future__ import with_statement
import logging
from logging.config import fileConfig
from flask import current_app
from alembic import context

import os
config = context.config
if config.config_file_name is not None and os.path.exists(config.config_file_name):
    fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')


def get_engine():
    try:
        return current_app.extensions['migrate'].db.get_engine()
    except (TypeError, AttributeError):
        return current_app.extensions['migrate'].db.engine


def get_engine_url():
    try:
        return get_engine().url.render_as_string(hide_password=False).replace('%', '%%')
    except AttributeError:
        return str(get_engine().url).replace('%', '%%')


config.set_main_option('sqlalchemy.url', get_engine_url())
target_db = current_app.extensions['migrate'].db


def get_metadata():
    if hasattr(target_db, 'metadatas'):
        return target_db.metadatas[None]
    return target_db.metadata


def run_migrations_offline():
    url = config.get_main_option('sqlalchemy.url')
    opts = {
        'url': url,
        'target_metadata': get_metadata(),
        'literal_binds': True,
        'compare_type': True
    }
    context.configure(**opts)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    def process_revision_directives(ctx, revision, directives):
        if getattr(config.cmd_opts, 'autogenerate', False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info('No schema changes detected.')
    conf_args = dict(current_app.extensions['migrate'].configure_args)
    if conf_args.get('process_revision_directives') is None:
        conf_args['process_revision_directives'] = process_revision_directives
    if 'compare_type' not in conf_args:
        conf_args['compare_type'] = True
    connectable = get_engine()
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            **conf_args,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
