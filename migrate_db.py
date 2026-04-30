"""
Database migration script — adds missing columns to existing tables.
Run automatically on app startup via run_migrations().
"""

import sqlite3
import logging

logger = logging.getLogger("migrate_db")


def run_migrations(db_path: str = "app.db"):
    """Add any missing columns to existing tables. Safe to run multiple times."""
    conn = sqlite3.connect(db_path, timeout=10)
    cursor = conn.cursor()

    # Ensure users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email VARCHAR(255) UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name VARCHAR(100),
        avatar_url TEXT,
        role VARCHAR(20) NOT NULL DEFAULT 'user',
        is_active BOOLEAN NOT NULL DEFAULT 1,
        last_login DATETIME,
        last_ip VARCHAR(50),
        created_at DATETIME
    )
    ''')

    # Ensure error_logs table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS error_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level VARCHAR(10) NOT NULL DEFAULT 'ERROR',
        source VARCHAR(50) NOT NULL,
        message TEXT NOT NULL,
        details TEXT,
        campaign_id INTEGER,
        created_at DATETIME
    )
    ''')

    # ─── campaigns table ───
    campaign_columns = [
        ("user_id", "INTEGER REFERENCES users(id)"),
        ("campaign_type", "VARCHAR(20) NOT NULL DEFAULT 'comment'"),
        ("story_id", "VARCHAR(100)"),
        ("post_thumbnail_url", "TEXT"),
        ("post_caption", "TEXT"),
        ("trigger_count", "INTEGER NOT NULL DEFAULT 0"),
        ("reply_sent_count", "INTEGER NOT NULL DEFAULT 0"),
        ("dm_sent_count", "INTEGER NOT NULL DEFAULT 0"),
        ("failed_count", "INTEGER NOT NULL DEFAULT 0"),
        ("cta_enabled", "BOOLEAN NOT NULL DEFAULT 0"),
        ("cta_label", "VARCHAR(100)"),
        ("cta_url", "TEXT"),
        ("require_follow", "BOOLEAN NOT NULL DEFAULT 0"),
        ("not_following_message", "TEXT"),
        ("opening_dm_enabled", "BOOLEAN NOT NULL DEFAULT 0"),
        ("opening_dm_text", "TEXT"),
        ("ask_email_enabled", "BOOLEAN NOT NULL DEFAULT 0"),
        ("ask_email_message", "TEXT"),
        ("updated_at", "DATETIME"),
    ]

    # ─── processed_comments table ───
    pc_columns = [
        ("username", "VARCHAR(100)"),
        ("comment_text", "TEXT"),
        ("reply_status", "VARCHAR(20) NOT NULL DEFAULT 'pending'"),
        ("dm_status", "VARCHAR(20) NOT NULL DEFAULT 'pending'"),
        ("reply_error", "TEXT"),
        ("dm_error", "TEXT"),
    ]

    # ─── config table (OAuth fields) ───
    config_columns = [
        ("user_id", "INTEGER REFERENCES users(id)"),
        ("ig_username", "VARCHAR(100)"),
        ("ig_profile_pic", "TEXT"),
        ("ig_followers", "INTEGER"),
        ("ig_account_type", "VARCHAR(50)"),
        ("token_expires_at", "DATETIME"),
        ("oauth_connected", "BOOLEAN NOT NULL DEFAULT 0"),
    ]

    # ─── users table migrations (if migrating from old schema) ───
    users_columns = [
        ("full_name", "VARCHAR(100)"),
        ("avatar_url", "TEXT"),
        ("role", "VARCHAR(20) NOT NULL DEFAULT 'user'"),
        ("is_active", "BOOLEAN NOT NULL DEFAULT 1"),
        ("last_login", "DATETIME"),
        ("last_ip", "VARCHAR(50)"),
    ]

    all_migrations = [
        ("campaigns", campaign_columns),
        ("processed_comments", pc_columns),
        ("config", config_columns),
        ("users", users_columns),
    ]

    added = 0
    for table, columns in all_migrations:
        for col_name, col_type in columns:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                logger.info("Added %s.%s", table, col_name)
                added += 1
            except sqlite3.OperationalError as e:
                pass # duplicate column

    # Migration step: assign orphan records to first admin user
    cursor.execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id ASC LIMIT 1")
    admin_row = cursor.fetchone()
    if admin_row:
        admin_id = admin_row[0]
        # Assign orphan campaigns
        cursor.execute("UPDATE campaigns SET user_id = ? WHERE user_id IS NULL", (admin_id,))
        # Assign orphan config
        cursor.execute("UPDATE config SET user_id = ? WHERE user_id IS NULL", (admin_id,))
        # Processed comments don't have user_id, they link to campaigns which have user_id

    conn.commit()
    conn.close()

    if added:
        logger.info("Migration complete — %d columns added", added)
    return added


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migrations()
