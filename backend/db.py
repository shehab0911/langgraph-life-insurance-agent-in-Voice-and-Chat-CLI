# backend/db.py
import os
from sqlalchemy import create_engine, Table, Column, Integer, String, MetaData, Text
from sqlalchemy.sql import select

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.getenv("CHAT_DB_PATH", os.path.join(BASE_DIR, "chat_history.db"))
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, future=True)
meta = MetaData()

sessions = Table(
    "sessions", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(128), nullable=False),
    Column("role", String(16), nullable=False),
    Column("content", Text, nullable=False)
)

meta.create_all(engine)

def append_message(session_id: str, role: str, content: str):
    with engine.connect() as conn:
        ins = sessions.insert().values(session_id=session_id, role=role, content=content)
        conn.execute(ins)
        conn.commit()

def get_history(session_id: str):
    with engine.connect() as conn:
        s = select([sessions.c.role, sessions.c.content]).where(sessions.c.session_id == session_id).order_by(sessions.c.id)
        res = conn.execute(s).fetchall()
        return [{"role": r[0], "content": r[1]} for r in res]
