import os
import json
import time
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_db(retries=3, delay=1):
    """Koneksi ke database dengan auto-retry"""
    last_error = None
    for attempt in range(retries):
        try:
            conn = psycopg2.connect(
                DATABASE_URL,
                connect_timeout=10,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5
            )
            conn.autocommit = False
            return conn
        except psycopg2.OperationalError as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(delay)
            continue
    raise last_error


def init_db():
    """Inisialisasi semua tabel"""
    conn   = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id           SERIAL PRIMARY KEY,
            username     TEXT NOT NULL UNIQUE,
            password     TEXT NOT NULL,
            display_name TEXT NOT NULL,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER NOT NULL DEFAULT 1,
            name       TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id         SERIAL PRIMARY KEY,
            subject_id INTEGER NOT NULL,
            role       TEXT NOT NULL,
            message    TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject_id) REFERENCES subjects(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roadmap_topics (
            id           SERIAL PRIMARY KEY,
            subject_id   INTEGER NOT NULL,
            topic_name   TEXT NOT NULL,
            is_completed INTEGER DEFAULT 0,
            order_index  INTEGER NOT NULL,
            parent_id    INTEGER DEFAULT NULL,
            level        INTEGER DEFAULT 0,
            FOREIGN KEY (subject_id) REFERENCES subjects(id)
        )
    """)

    # Tambah kolom baru kalau belum ada (untuk database lama)
    try:
        cursor.execute("""
            ALTER TABLE roadmap_topics
            ADD COLUMN IF NOT EXISTS parent_id INTEGER DEFAULT NULL
        """)
    except Exception:
        conn.rollback()

    try:
        cursor.execute("""
            ALTER TABLE roadmap_topics
            ADD COLUMN IF NOT EXISTS level INTEGER DEFAULT 0
        """)
    except Exception:
        conn.rollback()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weakness_report (
            id         SERIAL PRIMARY KEY,
            subject_id INTEGER NOT NULL,
            topic_name TEXT NOT NULL,
            score      INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject_id) REFERENCES subjects(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_references (
            id         SERIAL PRIMARY KEY,
            subject_id INTEGER NOT NULL,
            title      TEXT NOT NULL,
            type       TEXT NOT NULL,
            author     TEXT,
            year       TEXT,
            summary    TEXT,
            url        TEXT,
            tags       TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject_id) REFERENCES subjects(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recent_subjects (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            subject_id  INTEGER NOT NULL,
            accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id)    REFERENCES users(id),
            FOREIGN KEY (subject_id) REFERENCES subjects(id)
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("Database ready!")


# ===== HELPERS =====
def fetchall_as_dict(cursor):
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetchone_as_dict(cursor):
    if cursor.description is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    row = cursor.fetchone()
    return dict(zip(columns, row)) if row else None


# ===== USER AUTH =====
def create_user(username, password, display_name):
    import hashlib
    hashed = hashlib.sha256(password.encode()).hexdigest()
    conn   = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, password, display_name) VALUES (%s, %s, %s)",
            (username, hashed, display_name)
        )
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def login_user(username, password):
    import hashlib
    hashed = hashlib.sha256(password.encode()).hexdigest()
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM users WHERE username = %s AND password = %s",
        (username, hashed)
    )
    user = fetchone_as_dict(cursor)
    cursor.close()
    conn.close()
    return user


def get_user_by_id(user_id):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = fetchone_as_dict(cursor)
    cursor.close()
    conn.close()
    return user


# ===== SUBJECTS =====
def get_all_subjects(user_id):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM subjects WHERE user_id = %s ORDER BY created_at DESC",
        (user_id,)
    )
    subjects = fetchall_as_dict(cursor)
    cursor.close()
    conn.close()
    return subjects


def add_subject(name, user_id):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO subjects (name, user_id) VALUES (%s, %s)",
        (name, user_id)
    )
    conn.commit()
    cursor.close()
    conn.close()


def get_subject_by_id(subject_id):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM subjects WHERE id = %s", (subject_id,))
    subject = fetchone_as_dict(cursor)
    cursor.close()
    conn.close()
    return subject


def delete_subject(subject_id):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM saved_references  WHERE subject_id = %s", (subject_id,))
    cursor.execute("DELETE FROM weakness_report   WHERE subject_id = %s", (subject_id,))
    cursor.execute("DELETE FROM roadmap_topics    WHERE subject_id = %s", (subject_id,))
    cursor.execute("DELETE FROM conversations     WHERE subject_id = %s", (subject_id,))
    cursor.execute("DELETE FROM recent_subjects   WHERE subject_id = %s", (subject_id,))
    cursor.execute("DELETE FROM subjects          WHERE id = %s",         (subject_id,))
    conn.commit()
    cursor.close()
    conn.close()


# ===== CONVERSATIONS =====
def save_message(subject_id, role, message):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO conversations (subject_id, role, message) VALUES (%s, %s, %s)",
        (subject_id, role, message)
    )
    conn.commit()
    cursor.close()
    conn.close()


def get_conversations(subject_id):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM conversations WHERE subject_id = %s ORDER BY created_at ASC",
        (subject_id,)
    )
    messages = fetchall_as_dict(cursor)
    cursor.close()
    conn.close()
    return messages


def clear_conversations(subject_id):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM conversations WHERE subject_id = %s", (subject_id,))
    conn.commit()
    cursor.close()
    conn.close()


# ===== STATS =====
def get_completed_topics_count(subject_id):
    """Hitung sub-topik yang selesai (level=1), fallback ke level=0"""
    conn   = get_db()
    cursor = conn.cursor()
    # Prioritas hitung subtopik
    cursor.execute("""
        SELECT COUNT(*) FROM roadmap_topics
        WHERE subject_id = %s AND is_completed = 1 AND level = 1
    """, (subject_id,))
    count = cursor.fetchone()[0]

    # Kalau belum ada subtopik, hitung parent
    if count == 0:
        cursor.execute("""
            SELECT COUNT(*) FROM roadmap_topics
            WHERE subject_id = %s AND is_completed = 1 AND level = 0
        """, (subject_id,))
        count = cursor.fetchone()[0]

    cursor.close()
    conn.close()
    return count


def get_total_topics_count(subject_id):
    """Total subtopik, fallback ke parent"""
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM roadmap_topics
        WHERE subject_id = %s AND level = 1
    """, (subject_id,))
    count = cursor.fetchone()[0]

    if count == 0:
        cursor.execute("""
            SELECT COUNT(*) FROM roadmap_topics
            WHERE subject_id = %s AND level = 0
        """, (subject_id,))
        count = cursor.fetchone()[0]

    cursor.close()
    conn.close()
    return count


def get_chat_count(subject_id):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM conversations WHERE subject_id = %s AND role = 'user'",
        (subject_id,)
    )
    count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return count


# ===== ROADMAP =====
def get_roadmap(subject_id):
    """Ambil semua roadmap flat (untuk backward compatibility)"""
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM roadmap_topics WHERE subject_id = %s ORDER BY order_index ASC",
        (subject_id,)
    )
    topics = fetchall_as_dict(cursor)
    cursor.close()
    conn.close()
    return topics


def get_roadmap_structured(subject_id):
    """Ambil roadmap dalam bentuk hierarki parent → subtopics"""
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM roadmap_topics
        WHERE subject_id = %s
        ORDER BY order_index ASC
    """, (subject_id,))
    all_topics = fetchall_as_dict(cursor)
    cursor.close()
    conn.close()

    parents  = [t for t in all_topics if t["level"] == 0]
    children = [t for t in all_topics if t["level"] == 1]

    result = []
    for parent in parents:
        subs = [c for c in children if c["parent_id"] == parent["id"]]
        result.append({
            "id":           parent["id"],
            "topic_name":   parent["topic_name"],
            "is_completed": parent["is_completed"],
            "order_index":  parent["order_index"],
            "level":        0,
            "subtopics":    subs
        })

    return result


def save_roadmap(subject_id, topics):
    """Save roadmap flat (list of string) — untuk backward compatibility"""
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM roadmap_topics WHERE subject_id = %s", (subject_id,))
    for index, topic_name in enumerate(topics):
        cursor.execute(
            """INSERT INTO roadmap_topics
               (subject_id, topic_name, is_completed, order_index, level)
               VALUES (%s, %s, 0, %s, 0)""",
            (subject_id, topic_name, index)
        )
    conn.commit()
    cursor.close()
    conn.close()


def save_roadmap_with_subtopics(subject_id, roadmap_data):
    """
    Save roadmap hierarki.
    roadmap_data = [{"title": "...", "subtopics": ["...", "..."]}]
    """
    conn   = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM roadmap_topics WHERE subject_id = %s",
        (subject_id,)
    )

    order = 0
    for topic in roadmap_data:
        # Insert parent
        cursor.execute("""
            INSERT INTO roadmap_topics
            (subject_id, topic_name, is_completed, order_index, parent_id, level)
            VALUES (%s, %s, 0, %s, NULL, 0)
            RETURNING id
        """, (subject_id, topic["title"], order))

        parent_id = cursor.fetchone()[0]
        order += 1

        # Insert subtopics
        for subtopic in topic.get("subtopics", []):
            cursor.execute("""
                INSERT INTO roadmap_topics
                (subject_id, topic_name, is_completed, order_index, parent_id, level)
                VALUES (%s, %s, 0, %s, %s, 1)
            """, (subject_id, subtopic, order, parent_id))
            order += 1

    conn.commit()
    cursor.close()
    conn.close()


def toggle_topic(topic_id):
    """Toggle completed state"""
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE roadmap_topics
        SET is_completed = CASE WHEN is_completed = 1 THEN 0 ELSE 1 END
        WHERE id = %s
    """, (topic_id,))
    conn.commit()
    cursor.close()
    conn.close()


# ===== WEAKNESS =====
def save_weakness(subject_id, topic_name, score):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO weakness_report (subject_id, topic_name, score) VALUES (%s, %s, %s)",
        (subject_id, topic_name, score)
    )
    conn.commit()
    cursor.close()
    conn.close()


def get_weakness_report(subject_id):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            topic_name,
            ROUND(AVG(score))  AS avg_score,
            COUNT(*)           AS attempt_count,
            MAX(created_at)    AS last_attempt
        FROM weakness_report
        WHERE subject_id = %s
        GROUP BY topic_name
        ORDER BY AVG(score) ASC
    """, (subject_id,))
    results = fetchall_as_dict(cursor)
    cursor.close()
    conn.close()
    return results


# ===== REFERENCES =====
def save_reference(subject_id, ref_data):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO saved_references
        (subject_id, title, type, author, year, summary, url, tags)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        subject_id,
        ref_data.get("title",   ""),
        ref_data.get("type",    ""),
        ref_data.get("author",  ""),
        ref_data.get("year",    ""),
        ref_data.get("summary", ""),
        ref_data.get("url",     ""),
        json.dumps(ref_data.get("tags", []))
    ))
    conn.commit()
    cursor.close()
    conn.close()


def get_saved_references(subject_id):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM saved_references WHERE subject_id = %s ORDER BY created_at DESC",
        (subject_id,)
    )
    refs = fetchall_as_dict(cursor)
    cursor.close()
    conn.close()
    return refs


def delete_reference(ref_id):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM saved_references WHERE id = %s", (ref_id,))
    conn.commit()
    cursor.close()
    conn.close()


# ===== RECENT SUBJECTS =====
def log_recent_subject(user_id, subject_id):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM recent_subjects WHERE user_id = %s AND subject_id = %s",
        (user_id, subject_id)
    )
    cursor.execute(
        "INSERT INTO recent_subjects (user_id, subject_id) VALUES (%s, %s)",
        (user_id, subject_id)
    )
    conn.commit()
    cursor.close()
    conn.close()


def get_recent_subjects(user_id, limit=3):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.id, s.name
        FROM recent_subjects r
        JOIN subjects s ON r.subject_id = s.id
        WHERE r.user_id = %s
        ORDER BY r.accessed_at DESC
        LIMIT %s
    """, (user_id, limit))
    results = fetchall_as_dict(cursor)
    cursor.close()
    conn.close()
    return results