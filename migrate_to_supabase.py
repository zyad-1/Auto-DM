import sqlite3
from database import SessionLocal
from models import User, Campaign, Config

def migrate():
    # Read from old SQLite
    sqlite_conn = sqlite3.connect('app.db')
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()
    
    db = SessionLocal()
    
    try:
        # Migrate Users
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
        for u in users:
            user = User(
                id=u['id'],
                email=u['email'],
                password_hash=u['password_hash'],
                full_name=u['full_name'],
                role=u['role'],
                is_active=u['is_active'],
                created_at=u['created_at']
            )
            db.merge(user)
        db.commit()
        print(f"✅ Migrated {len(users)} users")
        
        # Migrate Campaigns
        cursor.execute("SELECT * FROM campaigns")
        campaigns = cursor.fetchall()
        for c in campaigns:
            campaign = Campaign(**dict(c))
            db.merge(campaign)
        db.commit()
        print(f"✅ Migrated {len(campaigns)} campaigns")
        
        # Migrate Config
        cursor.execute("SELECT * FROM config")
        configs = cursor.fetchall()
        for cfg in configs:
            config = Config(**dict(cfg))
            db.merge(config)
        db.commit()
        print(f"✅ Migrated {len(configs)} configs")
        
        print("🎉 Migration complete!")
        print("Check supabase.com dashboard to verify")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Migration failed: {e}")
    finally:
        db.close()
        sqlite_conn.close()

if __name__ == "__main__":
    migrate()
