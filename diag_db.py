from sqlalchemy import text
from app.core.database import get_app_engine
e = get_app_engine()
print("engine:", e.url.render_as_string(hide_password=True) if e else None)
with e.connect() as c:
    print(c.execute(text("select current_database(), current_user, current_setting('transaction_read_only')")).one())
    print(c.execute(text("select name, setting, source from pg_settings where name='default_transaction_read_only'")).one())
