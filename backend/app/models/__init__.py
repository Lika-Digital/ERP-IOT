"""All models, registered in one place.

create_all (tests, init_db), Alembic autogenerate and `alembic check` all import
this package, so they always see the same set of tables.
"""
from . import berth, billing, cabinet, cache, marina, metering, security, user  # noqa: F401
