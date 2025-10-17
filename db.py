# db.py
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import create_engine, text

USE_DB = bool(os.getenv("DATABASE_URL"))
engine = None

if USE_DB:
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

# ---------- SCHEMA ----------
SQL_INIT = """
CREATE TABLE IF NOT EXISTS messages (
  id SERIAL PRIMARY KEY,
  direction TEXT NOT NULL,            -- 'out' (manifest->pilot) / 'in' (pilot->manifest)
  text TEXT NOT NULL,
  ts TIMESTAMP NOT NULL DEFAULT NOW(),
  status TEXT NOT NULL DEFAULT 'sent', -- 'sent','delivered','read'
  remote_id TEXT                       -- id fra modpart (hvis brugt)
);

CREATE TABLE IF NOT EXISTS lifts (
  id INTEGER PRIMARY KEY,
  name TEXT,
  status TEXT,
  totals_jumpers INTEGER,
  totals_canopies INTEGER,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lift_rows (
  lift_id INTEGER REFERENCES lifts(id) ON DELETE CASCADE,
  alt INTEGER NOT NULL,
  jumpers INTEGER NOT NULL,
  overflights INTEGER NOT NULL
);
"""

def init():
    if USE_DB:
        with engine.begin() as conn:
            for stmt in SQL_INIT.strip().split(";"):
                s = stmt.strip()
                if s:
                    conn.execute(text(s))
    # intet at gøre for in-memory

# ---------- MESSAGES ----------
def add_message(direction: str, text: str, status: str = "sent", remote_id: Optional[str] = None) -> Dict[str, Any]:
    if USE_DB:
        with engine.begin() as conn:
            row = conn.execute(
                text("INSERT INTO messages(direction,text,status,remote_id) VALUES(:d,:t,:s,:r) RETURNING id, ts"),
                {"d": direction, "t": text, "s": status, "r": remote_id}
            ).mappings().first()
            return {"id": row["id"], "direction": direction, "text": text, "status": status, "remote_id": remote_id, "ts": row["ts"].isoformat()}
    else:
        # simple in-memory store
        m = {"id": add_message._next_id, "direction": direction, "text": text, "status": status, "remote_id": remote_id, "ts": datetime.utcnow().isoformat()}
        add_message._store.append(m)
        add_message._next_id += 1
        return m
add_message._store = []
add_message._next_id = 1

def list_messages(limit: int = 200) -> List[Dict[str, Any]]:
    if USE_DB:
        with engine.begin() as conn:
            rows = conn.execute(text("SELECT * FROM messages ORDER BY ts DESC LIMIT :n"), {"n": limit}).mappings().all()
            return [dict(r) | {"ts": r["ts"].isoformat()} for r in rows]
    else:
        return list(reversed(add_message._store[-limit:]))

def update_message_status(msg_id: int, status: str):
    if USE_DB:
        with engine.begin() as conn:
            conn.execute(text("UPDATE messages SET status=:s WHERE id=:i"), {"s": status, "i": msg_id})
    else:
        for m in add_message._store:
            if m["id"] == msg_id:
                m["status"] = status
                break

# ---------- LIFTS ----------
def upsert_lift(lift: Dict[str, Any]):
    # lift: {id, name, status, totals:{jumpers,canopies}, rows:[{alt,jumpers,overflights}]}
    if USE_DB:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO lifts(id,name,status,totals_jumpers,totals_canopies)
                VALUES(:i,:n,:s,:tj,:tc)
                ON CONFLICT (id) DO UPDATE SET
                  name=EXCLUDED.name,
                  status=EXCLUDED.status,
                  totals_jumpers=EXCLUDED.totals_jumpers,
                  totals_canopies=EXCLUDED.totals_canopies
            """), {
                "i": lift["id"], "n": lift.get("name"), "s": lift.get("status","active"),
                "tj": lift.get("totals",{}).get("jumpers"), "tc": lift.get("totals",{}).get("canopies")
            })
            conn.execute(text("DELETE FROM lift_rows WHERE lift_id=:i"), {"i": lift["id"]})
            for r in lift.get("rows", []):
                conn.execute(text("""
                    INSERT INTO lift_rows(lift_id,alt,jumpers,overflights)
                    VALUES(:i,:a,:j,:o)
                """), {"i": lift["id"], "a": r["alt"], "j": r["jumpers"], "o": r["overflights"]})
    else:
        upsert_lift._store[lift["id"]] = lift
upsert_lift._store = {}

def list_lifts() -> List[Dict[str, Any]]:
    if USE_DB:
        with engine.begin() as conn:
            base = conn.execute(text("SELECT * FROM lifts ORDER BY id DESC")).mappings().all()
            out = []
            for b in base:
                rows = conn.execute(text("SELECT alt,jumpers,overflights FROM lift_rows WHERE lift_id=:i ORDER BY alt"),
                                    {"i": b["id"]}).mappings().all()
                out.append({
                    "id": b["id"], "name": b["name"], "status": b["status"],
                    "totals": {"jumpers": b["totals_jumpers"], "canopies": b["totals_canopies"]},
                    "rows": [dict(r) for r in rows]
                })
            return out
    else:
        return sorted(upsert_lift._store.values(), key=lambda x: x["id"], reverse=True)

def set_lift_status(lift_id: int, status: str):
    if USE_DB:
        with engine.begin() as conn:
            conn.execute(text("UPDATE lifts SET status=:s WHERE id=:i"), {"s": status, "i": lift_id})
    else:
        if lift_id in upsert_lift._store:
            upsert_lift._store[lift_id]["status"] = status
