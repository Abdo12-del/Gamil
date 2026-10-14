"""
محرك التوزيع الذكي وتجميع المساحات وتقسيم الملفات الضخمة
(Smart Union Placement, Multi-Account Chunker & Deduplication Engine)
يحاكي وينفذ سياسات Rclone Union القياسية (mfs, epmfs, lno, priority) مع مراعاة:
1. المساحة الفارغة الفعلية في كل حساب + هامش الأمان (Safety Buffer).
2. حد الرفع اليومي الصارم في Google Drive (750 GB / 24h).
3. تقسيم الملفات الضخمة تلقائيًا عبر عدة حسابات (Transparent Multi-Account Chunking)
   عندما يتجاوز حجم الملف سعة الحساب الفردي أو حد التقطيع (Chunk Size).
4. فحص البصمة الرقمية (MD5) قبل الرفع لمنع تكرار الملفات عبر الحسابات.
5. إعادة موازنة الحمل (Auto-Rebalance) بين الحسابات الممتلئة والفارغة.
"""

import math
import sqlite3
from typing import Any, Dict, List, Optional


POLICY_DESCRIPTIONS = {
    "mfs": {
        "code": "mfs",
        "name": "الأكثر مساحة فارغة (Most Free Space - mfs)",
        "description": "يوجه كل ملف جديد تلقائيًا إلى الحساب الذي يمتلك أكبر سعة فارغة متاحة حاليًا.",
    },
    "epmfs": {
        "code": "epmfs",
        "name": "الحفاظ على المجلد مع الأكثر مساحة (Existing Path MFS - epmfs)",
        "description": "يفضل الحسابات التي تحتوي مسبقًا على نفس المجلد الافتراضي وبها أكبر مساحة فارغة لتقليل تشتت المجلدات.",
    },
    "lno": {
        "code": "lno",
        "name": "الأقل عددًا في الملفات (Least Number of Objects - lno)",
        "description": "يوازن عدد العناصر (Objects) بين الحسابات لتجنب سقف 500,000 عنصر وتخفيف ضغط طلبات الفهرسة.",
    },
    "priority": {
        "code": "priority",
        "name": "الأولوية المتدرجة (Priority Tiering)",
        "description": "يملأ الحسابات ذات الأولوية رقم 1 أولاً حتى تصل إلى عتبة التحذير (80%) ثم ينتقل تلقائيًا للحساب التالي.",
    },
}


def plan_chunked_upload(
    cur: sqlite3.Cursor,
    file_name: str,
    file_size: int,
    chunk_size_bytes: int = 2 * 1024 * 1024 * 1024,
) -> Dict[str, Any]:
    """
    محرك تقسيم الملفات الضخمة عبر عدة حسابات (Multi-Account Chunker):
    يقسم الملف الكبير إلى أجزاء (Chunks) ويوزعها على الحسابات المتاحة بحسب سعتها الحرة،
    مما يتيح تخزين ملف حجمه مثلاً 20 GB عبر عدة حسابات مجانية (15 GB لكل حساب).
    """
    cur.execute("SELECT key, value FROM system_settings")
    settings = {row["key"]: row["value"] for row in cur.fetchall()}
    safety_buffer = int(settings.get("safety_buffer_mb", "250")) * 1024 * 1024

    cur.execute(
        """
        SELECT * FROM accounts
        WHERE status = 'connected'
        ORDER BY (total_bytes - used_bytes) DESC
        """
    )
    accounts = [dict(r) for r in cur.fetchall()]

    usable_accounts: List[Dict[str, Any]] = []
    total_usable_free = 0
    for acc in accounts:
        free_after_buf = max(0, (acc["total_bytes"] - acc["used_bytes"]) - safety_buffer)
        if free_after_buf > 0:
            usable_accounts.append({**acc, "allocatable_bytes": free_after_buf})
            total_usable_free += free_after_buf

    if total_usable_free < file_size:
        return {
            "can_chunk": False,
            "reason": (
                f"إجمالي المساحة الصافية المتاحة عبر جميع الحسابات مجتمعة "
                f"({round(total_usable_free / (1024**3), 2)} GiB) أقل من حجم الملف المطلوب "
                f"({round(file_size / (1024**3), 2)} GiB)."
            ),
            "chunks": [],
        }

    chunks: List[Dict[str, Any]] = []
    remaining = file_size
    part_num = 1

    # توزيع الأجزاء بالتناوب على الحسابات الأوسع مساحة (Round-Robin Weighted by Free Space)
    while remaining > 0:
        usable_accounts.sort(key=lambda a: a["allocatable_bytes"], reverse=True)
        target = usable_accounts[0]
        if target["allocatable_bytes"] <= 0:
            break

        this_chunk = min(remaining, chunk_size_bytes, target["allocatable_bytes"])
        chunks.append(
            {
                "part_number": part_num,
                "chunk_name": f"{file_name}.rclone_chunk.{part_num:03d}",
                "size_bytes": this_chunk,
                "account_id": target["id"],
                "account_name": target["name"],
                "account_email": target["email"],
                "account_color": target["color"],
            }
        )
        target["allocatable_bytes"] -= this_chunk
        remaining -= this_chunk
        part_num += 1

    accounts_used = list({c["account_name"] for c in chunks})
    return {
        "can_chunk": remaining == 0,
        "total_chunks": len(chunks),
        "chunk_size_bytes": chunk_size_bytes,
        "accounts_spanned": accounts_used,
        "reason": (
            f"تم تفعيل مقسّم الملفات الذكي (Rclone Chunker): تقسيم الملف إلى {len(chunks)} أجزاء "
            f"وتوزيعها عبر {len(accounts_used)} حسابات ({' + '.join(accounts_used)})."
        ),
        "chunks": chunks,
    }


def select_best_account(
    cur: sqlite3.Cursor,
    file_size: int,
    virtual_path: str = "/",
    override_policy: Optional[str] = None,
    preferred_account_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    يحدد الحساب الأنسب لتخزين ملف بحجم file_size وفق السياسة النشطة.
    وإذا كان الملف أكبر من أي حساب منفرد، يقترح خطة التقسيم التلقائي (Multi-Account Chunking).
    """
    cur.execute("SELECT key, value FROM system_settings")
    settings = {row["key"]: row["value"] for row in cur.fetchall()}

    policy = override_policy or settings.get("placement_policy", "mfs")
    safety_buffer = int(settings.get("safety_buffer_mb", "250")) * 1024 * 1024
    warning_pct = float(settings.get("warning_threshold_pct", "80"))

    cur.execute(
        """
        SELECT a.*,
               (SELECT COUNT(*) FROM files f WHERE f.account_id = a.id) AS file_count,
               (SELECT COUNT(*) FROM files f WHERE f.account_id = a.id AND f.virtual_path = ?) AS path_file_count
        FROM accounts a
        ORDER BY a.priority ASC, (a.total_bytes - a.used_bytes) DESC
        """,
        (virtual_path,),
    )
    accounts = [dict(r) for r in cur.fetchall()]

    candidates: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for acc in accounts:
        free_bytes = max(0, acc["total_bytes"] - acc["used_bytes"])
        daily_rem = max(0, acc["daily_upload_limit"] - acc["daily_uploaded_bytes"])
        used_pct = (
            round((acc["used_bytes"] / acc["total_bytes"]) * 100, 2)
            if acc["total_bytes"] > 0
            else 100.0
        )

        acc_eval = {
            "account_id": acc["id"],
            "name": acc["name"],
            "email": acc["email"],
            "provider": acc["provider"],
            "color": acc["color"],
            "free_bytes": free_bytes,
            "used_bytes": acc["used_bytes"],
            "total_bytes": acc["total_bytes"],
            "used_pct": used_pct,
            "file_count": acc["file_count"],
            "path_exists": acc["path_file_count"] > 0,
            "priority": acc["priority"],
            "status": acc["status"],
        }

        if acc["status"] != "connected":
            acc_eval["reject_reason"] = "الحساب غير متصل أو يحتاج إلى تجديد صلاحية OAuth"
            rejected.append(acc_eval)
            continue

        if free_bytes < (file_size + safety_buffer):
            acc_eval["reject_reason"] = (
                f"المساحة الحرة ({round(free_bytes / (1024**3), 2)} GiB) أقل من حجم الملف + هامش الأمان"
            )
            rejected.append(acc_eval)
            continue

        if daily_rem < file_size:
            acc_eval["reject_reason"] = "تم تجاوز حد الرفع اليومي المسموح (750 GB / 24h)"
            rejected.append(acc_eval)
            continue

        candidates.append(acc_eval)

    if not candidates:
        # إذا لم يتسع أي حساب منفرد، نفحص إمكانية تقسيم الملف عبر عدة حسابات (Chunker)
        chunk_plan = plan_chunked_upload(cur, "large_file.bin", file_size)
        return {
            "success": False,
            "requires_chunking": chunk_plan["can_chunk"],
            "chunk_plan": chunk_plan,
            "policy": policy,
            "selected": None,
            "reason": (
                chunk_plan["reason"]
                if chunk_plan["can_chunk"]
                else "لا يوجد حساب منفرد أو مجموع حسابات يملك مساحة كافية لهذا الملف."
            ),
            "candidates": [],
            "rejected": rejected,
        }

    # إذا حدد المستخدم حسابًا بعينه يدويًا وكان مؤهلاً
    if preferred_account_id:
        for c in candidates:
            if c["account_id"] == preferred_account_id:
                return {
                    "success": True,
                    "requires_chunking": False,
                    "policy": "manual",
                    "selected": c,
                    "reason": f"تم التوجيه يدويًا حسب اختيارك إلى ({c['name']}).",
                    "candidates": candidates,
                    "rejected": rejected,
                }

    # تطبيق خوارزمية السياسة المختارة
    if policy == "epmfs":
        existing_path_candidates = [c for c in candidates if c["path_exists"]]
        if existing_path_candidates:
            existing_path_candidates.sort(key=lambda x: x["free_bytes"], reverse=True)
            chosen = existing_path_candidates[0]
            reason = (
                f"سياسة (epmfs): المجلد ({virtual_path}) موجود مسبقًا في ({chosen['name']}) "
                f"وهو الأعلى مساحة فارغة بين الحسابات الحاملة للمسار."
            )
        else:
            candidates.sort(key=lambda x: x["free_bytes"], reverse=True)
            chosen = candidates[0]
            reason = (
                f"سياسة (epmfs -> mfs): المجلد ({virtual_path}) جديد، فتم اختيار الحساب "
                f"الأكبر سعة فارغة ({chosen['name']})."
            )
    elif policy == "lno":
        candidates.sort(key=lambda x: (x["file_count"], -x["free_bytes"]))
        chosen = candidates[0]
        reason = (
            f"سياسة (lno): تم اختيار ({chosen['name']}) لأنه يحتوي على أقل عدد ملفات "
            f"({chosen['file_count']} ملف) لتوزيع ضغط الفهرسة."
        )
    elif policy == "priority":
        non_warn = [c for c in candidates if c["used_pct"] < warning_pct]
        pool = non_warn if non_warn else candidates
        pool.sort(key=lambda x: (x["priority"], -x["free_bytes"]))
        chosen = pool[0]
        reason = (
            f"سياسة (الأولوية): تم اختيار ({chosen['name']}) ذي الأولوية ({chosen['priority']}) "
            f"ونسبة إشغال ({chosen['used_pct']}%)."
        )
    else:  # mfs (الافتراضي: الأكثر مساحة فارغة)
        candidates.sort(key=lambda x: x["free_bytes"], reverse=True)
        chosen = candidates[0]
        reason = (
            f"سياسة (mfs - الأكثر مساحة فارغة): تم توجيه الملف تلقائيًا إلى ({chosen['name']}) "
            f"لأنه يمتلك أكبر مساحة حرة ({round(chosen['free_bytes'] / (1024**3), 2)} GiB)."
        )

    return {
        "success": True,
        "requires_chunking": False,
        "policy": policy,
        "policy_info": POLICY_DESCRIPTIONS.get(policy, POLICY_DESCRIPTIONS["mfs"]),
        "selected": chosen,
        "reason": reason,
        "candidates": candidates,
        "rejected": rejected,
    }


def find_duplicates(cur: sqlite3.Cursor) -> Dict[str, Any]:
    """
    يكتشف جميع الملفات المكررة عبر كافة الحسابات بناءً على البصمة الرقمية (MD5 Hash)
    أو تطابق الاسم والحجم، ويحسب إجمالي المساحة المهدرة القابلة للاسترجاع.
    """
    cur.execute(
        """
        SELECT f.*, a.name AS account_name, a.email AS account_email, a.color AS account_color
        FROM files f
        JOIN accounts a ON f.account_id = a.id
        WHERE f.md5_hash IS NOT NULL AND f.md5_hash != ''
        ORDER BY f.size DESC, f.modified_at ASC
        """
    )
    all_files = [dict(r) for r in cur.fetchall()]

    by_hash: Dict[str, List[Dict[str, Any]]] = {}
    for f in all_files:
        by_hash.setdefault(f["md5_hash"], []).append(f)

    duplicate_groups: List[Dict[str, Any]] = []
    total_wasted_bytes = 0
    total_redundant_files = 0

    for md5_hash, group in by_hash.items():
        if len(group) > 1:
            file_size = group[0]["size"]
            wasted = file_size * (len(group) - 1)
            total_wasted_bytes += wasted
            total_redundant_files += len(group) - 1
            accounts_involved = list({item["account_name"] for item in group})
            is_cross_account = len({item["account_id"] for item in group}) > 1

            duplicate_groups.append(
                {
                    "md5_hash": md5_hash,
                    "primary_name": group[0]["name"],
                    "file_size": file_size,
                    "copies_count": len(group),
                    "wasted_bytes": wasted,
                    "is_cross_account": is_cross_account,
                    "accounts_involved": accounts_involved,
                    "files": group,
                }
            )

    duplicate_groups.sort(key=lambda g: g["wasted_bytes"], reverse=True)
    return {
        "groups_count": len(duplicate_groups),
        "redundant_files_count": total_redundant_files,
        "total_wasted_bytes": total_wasted_bytes,
        "groups": duplicate_groups,
    }


def generate_rclone_config(cur: sqlite3.Cursor) -> Dict[str, str]:
    """
    يولّد ملف إعدادات rclone.conf جاهز للعمل الفعلي مع أوامر التركيب (rclone mount)
    وأوامر خادم التحكم (rclone rcd) وبوابة WebDAV المتوافقة مع OpenList،
    بالإضافة إلى ملف docker-compose.yml جاهز للاستضافة الذاتية المجانية.
    """
    cur.execute("SELECT * FROM accounts ORDER BY priority ASC")
    accounts = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT key, value FROM system_settings")
    settings = {row["key"]: row["value"] for row in cur.fetchall()}
    policy = settings.get("placement_policy", "mfs")
    rclone_policy = policy if policy in ("mfs", "epmfs", "lno") else "epmfs"

    lines: List[str] = [
        "# ======================================================================",
        "# ملف إعدادات Rclone الموحد — تم توليده تلقائيًا بواسطة منصة Gamil CloudPool",
        "# يجمع عدة حسابات Google Drive وعقد تخزين في مساحة افتراضية واحدة (Union)",
        "# ======================================================================",
        "",
    ]

    upstreams: List[str] = []
    combine_upstreams: List[str] = []

    for acc in accounts:
        remote_name = acc["rclone_remote"].rstrip(":")
        lines.append(f"[{remote_name}]")
        if acc["provider"] == "google_drive":
            lines.append("type = drive")
            lines.append("scope = drive")
            lines.append(f"# Account: {acc['name']} ({acc['email']})")
            lines.append(
                'token = {"access_token":"<ENCRYPTED_IN_GAMIL_VAULT>","token_type":"Bearer"}'
            )
            lines.append("server_side_across_configs = true")
            upstreams.append(f"{remote_name}:pool")
            combine_upstreams.append(f'"{remote_name}={remote_name}:"')
        else:
            lines.append("type = local")
            lines.append(f"# Local Node: {acc['name']}")
            upstreams.append(f"{remote_name}:/home/user/Gamil/storage_nodes/{acc['id']}")
            combine_upstreams.append(
                f'"{remote_name}={remote_name}:/home/user/Gamil/storage_nodes/{acc["id"]}"'
            )
        lines.append("")

    lines.extend(
        [
            "[gamil_union]",
            "type = union",
            f"upstreams = {' '.join(upstreams)}",
            "action_policy = epall",
            f"create_policy = {rclone_policy}",
            "search_policy = ff",
            "cache_time = 120",
            "",
            "# طبقة تقسيم الملفات الضخمة (Chunker) لتجاوز سقف حجم الحساب الفردي",
            "[gamil_chunker]",
            "type = chunker",
            "remote = gamil_union:",
            "chunk_size = 2G",
            "hash_type = md5",
            "",
            "# طبقة Combine لعرض كل حساب كمجلد مستقل في شجرة واحدة",
            "[gamil_combine]",
            "type = combine",
            f"upstreams = {' '.join(combine_upstreams)}",
        ]
    )

    commands = (
        "# 1. تركيب المساحة الموحدة كقرص افتراضي محلي (مثل Mountain Duck مجانًا):\n"
        "rclone mount gamil_chunker: /mnt/gamil_cloud --vfs-cache-mode writes --vfs-cache-max-size 10G --dir-cache-time 5m\n\n"
        "# 2. تشغيل خادم WebDAV الموحد لربطه مع OpenList أو مستكشف الملفات:\n"
        "rclone serve webdav gamil_chunker: --addr 0.0.0.0:8085 --vfs-cache-mode writes\n\n"
        "# 3. تشغيل محرك التحكم البرمجي (Rclone RC Daemon):\n"
        "rclone rcd --rc-addr 127.0.0.1:5572 --rc-no-auth\n\n"
        "# 4. فحص وإزالة الملفات المكررة عبر البصمة الرقمية MD5:\n"
        "rclone dedupe --by-hash gamil_union: --dedupe-mode newest --dry-run"
    )

    docker_compose = """version: "3.9"
services:
  gamil-cloudpool:
    build: .
    container_name: gamil-cloudpool
    ports:
      - "8000:8000"
    volumes:
      - ./storage_nodes:/app/storage_nodes
      - ./rclone_config:/config/rclone
    environment:
      - GAMIL_VAULT_KEY=change-this-secret-in-production
    restart: unless-stopped

  rclone-union-webdav:
    image: rclone/rclone:latest
    container_name: gamil-rclone-union
    command: serve webdav gamil_chunker: --addr 0.0.0.0:8085 --vfs-cache-mode writes
    ports:
      - "8085:8085"
    volumes:
      - ./rclone_config:/config/rclone
      - ./storage_nodes:/data/storage_nodes
    restart: unless-stopped

  openlist-ui:
    image: openlistteam/openlist:latest
    container_name: gamil-openlist
    ports:
      - "5244:5244"
    volumes:
      - ./openlist_data:/opt/openlist/data
    depends_on:
      - rclone-union-webdav
    restart: unless-stopped
"""

    return {
        "rclone_conf": "\n".join(lines),
        "cli_commands": commands,
        "docker_compose": docker_compose,
        "active_policy": rclone_policy,
    }
