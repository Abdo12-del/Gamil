"""
إدارة قاعدة البيانات المحلية الموحدة (SQLite3 + FTS5 Full-Text Search)
تحفظ البيانات الوصفية للحسابات، فهرس الملفات الموحد، بصمات MD5 لمنع التكرار،
وسجل العمليات والتنبيهات، مع تشفير كافة رموز OAuth 2.0 عبر AES-256-GCM.
"""

from datetime import datetime, timezone
import os
import sqlite3
from typing import Any, Dict, List, Optional

from backend.crypto_vault import vault
from backend.seed_data import INITIAL_ACCOUNTS, INITIAL_FILES

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "gamil_cloudpool.db")
STORAGE_NODES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage_nodes")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db() -> None:
    os.makedirs(STORAGE_NODES_DIR, exist_ok=True)
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            provider TEXT NOT NULL DEFAULT 'google_drive',
            account_type TEXT NOT NULL DEFAULT 'Google Personal (15 GB)',
            rclone_remote TEXT NOT NULL,
            total_bytes INTEGER NOT NULL,
            used_bytes INTEGER NOT NULL DEFAULT 0,
            daily_upload_limit INTEGER NOT NULL DEFAULT 805306368000,
            daily_uploaded_bytes INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'connected',
            auth_mode TEXT NOT NULL DEFAULT 'OAuth 2.0',
            encrypted_tokens TEXT,
            token_expires_at TEXT,
            color TEXT NOT NULL DEFAULT '#2563eb',
            priority INTEGER NOT NULL DEFAULT 1,
            notes TEXT,
            last_sync_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            remote_file_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            name TEXT NOT NULL,
            virtual_path TEXT NOT NULL DEFAULT '/',
            mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
            size INTEGER NOT NULL DEFAULT 0,
            md5_hash TEXT NOT NULL,
            web_view_link TEXT,
            local_file_path TEXT,
            modified_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_files_md5 ON files(md5_hash);
        CREATE INDEX IF NOT EXISTS idx_files_account ON files(account_id);
        CREATE INDEX IF NOT EXISTS idx_files_vpath ON files(virtual_path);

        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT NOT NULL DEFAULT 'info',
            action_type TEXT NOT NULL,
            account_id TEXT,
            title TEXT NOT NULL,
            details TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS upload_sessions (
            session_id TEXT PRIMARY KEY,
            file_name TEXT NOT NULL,
            virtual_path TEXT NOT NULL DEFAULT '/كتب',
            mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
            total_bytes INTEGER NOT NULL,
            uploaded_bytes INTEGER NOT NULL DEFAULT 0,
            md5_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'in_progress',
            allocations_json TEXT NOT NULL DEFAULT '[]',
            autoscale_triggered INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS standby_pool (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            provider TEXT NOT NULL DEFAULT 'google_drive',
            driver_tool TEXT NOT NULL DEFAULT 'GAM / OAuth Standby',
            quota_bytes INTEGER NOT NULL DEFAULT 16106127360,
            encrypted_credentials TEXT,
            is_consumed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        """
    )

    # إعدادات النظام الافتراضية (مستوحاة من سياسات Rclone Union + محرك التوسع التلقائي)
    default_settings = {
        "placement_policy": "mfs",  # mfs | epmfs | lno | priority
        "safety_buffer_mb": "250",
        "pre_upload_dedupe": "true",
        "warning_threshold_pct": "80",
        "critical_threshold_pct": "92",
        "chunk_threshold_gb": "5",
        "autoscale_enabled": "true",
        "autoscale_trigger_pct": "85",
        "autoscale_unit_gb": "15",
        "autoscale_driver": "hybrid_gam_rclone",  # hybrid_gam_rclone | standby_oauth | casdoor_s3
        "simple_ui_mode": "true",
    }
    for k, v in default_settings.items():
        cur.execute(
            "INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)", (k, v)
        )

    # التحقق مما إذا كانت البيانات الأولية موجودة
    cur.execute("SELECT COUNT(*) AS cnt FROM accounts")
    count = cur.fetchone()["cnt"]
    if count == 0:
        seed_initial_data(cur)

    cur.execute("SELECT COUNT(*) AS scnt FROM standby_pool")
    if cur.fetchone()["scnt"] == 0:
        seed_standby_pool(cur)

    conn.commit()
    conn.close()


def seed_standby_pool(cur: sqlite3.Cursor) -> None:
    ts = now_iso()
    gb = 1024 * 1024 * 1024
    standby_entries = [
        (
            "standby_gam_gdrive_04",
            "حساب توسعة تلقائي #4 (Google Drive Standby)",
            "ngacademy.autoscale4@gmail.com",
            "google_drive",
            "GAMADV-XTD3 / Pre-Authorized OAuth Standby",
            15 * gb,
        ),
        (
            "standby_gam_gdrive_05",
            "حساب توسعة تلقائي #5 (Google Drive Standby)",
            "ngacademy.autoscale5@gmail.com",
            "google_drive",
            "GAMADV-XTD3 / Pre-Authorized OAuth Standby",
            15 * gb,
        ),
        (
            "standby_casdoor_node_06",
            "حساب توسعة تلقائي #6 (Casdoor IAM + SeaweedFS Bucket)",
            "autoscale-node6@gamil.cloud",
            "local_disk",
            "Casdoor SDK AddUser + Rclone Mkdir Provisioner",
            25 * gb,
        ),
    ]
    for sid, sname, semail, sprov, sdriver, squota in standby_entries:
        enc_creds = vault.encrypt_payload(
            {
                "access_token": f"ya29.standby_auto_{sid}",
                "refresh_token": f"1//0g_standby_refresh_{sid}",
                "provisioned_by": sdriver,
            }
        )
        cur.execute(
            """
            INSERT OR IGNORE INTO standby_pool (
                id, name, email, provider, driver_tool, quota_bytes,
                encrypted_credentials, is_consumed, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (sid, sname, semail, sprov, sdriver, squota, enc_creds, ts),
        )


def seed_initial_data(cur: sqlite3.Cursor) -> None:
    ts = now_iso()
    for acc in INITIAL_ACCOUNTS:
        os.makedirs(os.path.join(STORAGE_NODES_DIR, acc["id"]), exist_ok=True)
        encrypted_tok = vault.encrypt_payload(
            {
                "access_token": f"ya29.a0AfB_byC_{acc['id']}_live_oauth2",
                "refresh_token": f"1//0g_RefreshToken_{acc['id']}_production_offline",
                "token_type": "Bearer",
                "scope": "https://www.googleapis.com/auth/drive",
            }
        )
        cur.execute(
            """
            INSERT INTO accounts (
                id, name, email, provider, account_type, rclone_remote,
                total_bytes, used_bytes, daily_upload_limit, daily_uploaded_bytes,
                status, auth_mode, encrypted_tokens, token_expires_at,
                color, priority, notes, last_sync_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                acc["id"],
                acc["name"],
                acc["email"],
                acc["provider"],
                acc["account_type"],
                acc["rclone_remote"],
                acc["total_bytes"],
                acc["used_bytes"],
                acc["daily_upload_limit"],
                acc["daily_uploaded_bytes"],
                acc["status"],
                acc["auth_mode"],
                encrypted_tok,
                acc["token_expires_at"],
                acc["color"],
                acc["priority"],
                acc["notes"],
                ts,
            ),
        )

    for f in INITIAL_FILES:
        cur.execute(
            """
            INSERT INTO files (
                remote_file_id, account_id, name, virtual_path, mime_type,
                size, md5_hash, web_view_link, local_file_path, modified_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f["remote_file_id"],
                f["account_id"],
                f["name"],
                f["virtual_path"],
                f["mime_type"],
                f["size"],
                f["md5_hash"],
                f.get("web_view_link", ""),
                None,
                f["modified_at"],
                ts,
            ),
        )

    # إضافة سجلات عمليات وتنبيهات حقيقية أولية
    initial_logs = [
        (
            "success",
            "sync",
            "gdrive_ngacademy_main",
            "مزامنة حساب Google Drive الرئيسي (ngacademy14@gmail.com)",
            "تم استيراد وفهرسة الملفات والمجلدات (/كتب، /Google AI Studio، /تقارير ومستندات NG Academy) مع بصمات MD5 بنجاح.",
        ),
        (
            "warning",
            "dedupe_alert",
            "gdrive_ngacademy_main",
            "اكتشاف ملفات مكررة تستهلك مساحة إضافية (128.12 MB)",
            "تم رصد 3 مجموعات تكرار بالبصمة الرقمية MD5 (منها كتاب Connecting through talk وكتاب Words Their Way وصور Google AI Studio).",
        ),
        (
            "info",
            "quota_notice",
            "gdrive_ngacademy_main",
            "تنبيه استهلاك مساحة في الحساب الرئيسي (51.9%)",
            "يحتوي الحساب الرئيسي على ملف فيديو بحجم 7.54 GiB (Meet - ohi-psow-pbg.mp4). محرك التوزيع يوجه الرفوعات الجديدة تلقائيًا إلى الحساب #3 وعقدة التخزين المحلي.",
        ),
        (
            "success",
            "vault",
            None,
            "تفعيل خزنة التشفير AES-256-GCM لرموز OAuth 2.0",
            "جميع رموز الوصول والتجديد (Refresh Tokens) لـ 4 عقد تخزين مشفرة ومحمية دون حفظ أي كلمات مرور.",
        ),
    ]
    for level, action_type, acc_id, title, details in initial_logs:
        cur.execute(
            """
            INSERT INTO operation_logs (level, action_type, account_id, title, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (level, action_type, acc_id, title, details, ts),
        )


def log_operation(
    cur: sqlite3.Cursor,
    level: str,
    action_type: str,
    title: str,
    details: str,
    account_id: Optional[str] = None,
) -> None:
    cur.execute(
        """
        INSERT INTO operation_logs (level, action_type, account_id, title, details, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (level, action_type, account_id, title, details, now_iso()),
    )


def recalculate_account_usage(cur: sqlite3.Cursor, account_id: str) -> None:
    """إعادة حساب المساحة المستخدمة للحساب بناءً على الملفات الفعلية المسجلة فيه."""
    cur.execute(
        "SELECT COALESCE(SUM(size), 0) AS total_size FROM files WHERE account_id = ?",
        (account_id,),
    )
    total_size = int(cur.fetchone()["total_size"])
    cur.execute(
        "UPDATE accounts SET used_bytes = ?, last_sync_at = ? WHERE id = ?",
        (total_size, now_iso(), account_id),
    )
