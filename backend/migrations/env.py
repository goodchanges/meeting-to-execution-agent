from alembic import context

from backend.app.config import Settings
from backend.app.db import engine_for

connection = context.config.attributes.get("connection")
if connection is None:
    with engine_for(Settings().db_path).connect() as db:
        context.configure(connection=db)
        with context.begin_transaction():
            context.run_migrations()
else:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
