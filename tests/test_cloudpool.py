"""
اختبارات شاملة لمنصة Gamil CloudPool v2.0
تتحقق من:
1. خزنة التشفير AES-256-GCM لرموز OAuth 2.0.
2. سياسات محرك التوزيع الذكي (mfs, epmfs, lno, priority).
3. تقسيم الملفات الضخمة عبر عدة حسابات (Multi-Account Chunker).
4. منع التكرار الاستباقي بالبصمة الرقمية (MD5 Pre-Upload Dedupe) وتنظيف التكرارات.
5. استيراد وتوليد ملفات rclone.conf وموازنة المساحة التلقائية.
"""

import unittest
from fastapi.testclient import TestClient

from backend.crypto_vault import vault
from backend.main import app


class TestGamilCloudPool(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.client.post("/api/reset-demo")

    def test_01_aes256_gcm_token_vault(self) -> None:
        secret_data = {
            "access_token": "ya29.super_secret_token_12345",
            "refresh_token": "1//0g_offline_refresh_99999",
        }
        encrypted = vault.encrypt_payload(secret_data)
        self.assertTrue(encrypted.startswith("enc:aes256gcm:"))
        self.assertNotIn("super_secret_token", encrypted)
        decrypted = vault.decrypt_payload(encrypted)
        self.assertEqual(decrypted["access_token"], secret_data["access_token"])
        self.assertEqual(decrypted["refresh_token"], secret_data["refresh_token"])

    def test_02_dashboard_and_synced_accounts(self) -> None:
        res = self.client.get("/api/dashboard")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["pool"]["accounts_count"], 4)
        self.assertGreaterEqual(data["pool"]["duplicate_groups_count"], 3)
        self.assertIn("api_quota_monitor", data)

    def test_03_smart_placement_policies_and_chunker_simulation(self) -> None:
        # 1. اختبار ملف عادي (500 MB) بسياسة mfs
        res = self.client.post(
            "/api/placement/simulate",
            json={
                "file_name": "course.mp4",
                "file_size_bytes": 500 * 1024 * 1024,
                "virtual_path": "/كتب",
                "policy": "mfs",
            },
        )
        self.assertEqual(res.status_code, 200)
        sim = res.json()
        self.assertTrue(sim["success"])
        self.assertIsNotNone(sim["selected"])

        # 2. اختبار ملف ضخم (30 GB) يتجاوز أي حساب منفرد فيفعل Chunker تلقائيًا
        res_large = self.client.post(
            "/api/placement/simulate",
            json={
                "file_name": "huge_backup.tar",
                "file_size_bytes": 30 * 1024 * 1024 * 1024,
                "virtual_path": "/تسجيلات وميديا",
                "policy": "mfs",
            },
        )
        self.assertEqual(res_large.status_code, 200)
        sim_large = res_large.json()
        self.assertFalse(sim_large["success"])
        self.assertTrue(sim_large["requires_chunking"])
        self.assertGreater(sim_large["chunk_plan"]["total_chunks"], 1)

    def test_04_pre_upload_deduplication_and_clean(self) -> None:
        # محاولة رفع ملف بنفس البصمة مرتين
        payload = {
            "name": "test_book.pdf",
            "size_mb": 10.0,
            "virtual_path": "/كتب",
            "content_seed": "same_hash_seed_123",
            "force_duplicate": False,
        }
        r1 = self.client.post("/api/files/create-synthetic", json=payload)
        self.assertTrue(r1.json()["success"])

        r2 = self.client.post("/api/files/create-synthetic", json=payload)
        self.assertFalse(r2.json()["success"])
        self.assertTrue(r2.json()["duplicate_blocked"])

        # تنظيف جميع التكرارات الموجودة
        clean_res = self.client.post("/api/duplicates/clean")
        self.assertEqual(clean_res.status_code, 200)
        self.assertGreaterEqual(clean_res.json()["removed_files_count"], 3)

    def test_05_multi_account_chunked_upload_and_rclone_import(self) -> None:
        r_chunk = self.client.post(
            "/api/files/upload-chunked",
            json={
                "name": "archive_16gb.tar",
                "size_gb": 16.0,
                "chunk_size_gb": 4.0,
                "virtual_path": "/تسجيلات وميديا",
            },
        )
        self.assertEqual(r_chunk.status_code, 200)
        self.assertEqual(r_chunk.json()["plan"]["total_chunks"], 4)

        r_imp = self.client.post(
            "/api/rclone/import",
            json={
                "conf_text": '[gdrive_extra]\ntype = drive\ntoken = {"access_token":"ya29.test","refresh_token":"1//0g.test"}\n'
            },
        )
        self.assertEqual(r_imp.status_code, 200)
        self.assertEqual(r_imp.json()["imported_count"], 1)

    def test_06_background_autoscale_and_midstream_overflow(self) -> None:
        # 1. التحقق من حالة مخزون الاحتياط وأدوات GitHub
        st_res = self.client.get("/api/autoscale/status")
        self.assertEqual(st_res.status_code, 200)
        st_data = st_res.json()
        self.assertGreaterEqual(len(st_data["standby_pool"]), 3)
        self.assertGreaterEqual(len(st_data["github_drivers"]), 4)

        # 2. رفع ملف 8.2 GB على الحساب الرئيسي (المتبقي فيه ~7.75 GB فقط)
        # يجب أن يملأ النظام الحساب الرئيسي حتى الحد الآمن ثم يوسع المساحة تلقائيًا ويكمل الرفع
        up_res = self.client.post(
            "/api/autoscale/upload-seamless",
            json={
                "file_name": "محاضرة_توسع_تلقائي_8GB.mp4",
                "size_mb": 8200.0,
                "virtual_path": "/تسجيلات وميديا",
                "target_account_id": "gdrive_ngacademy_main",
            },
        )
        self.assertEqual(up_res.status_code, 200)
        up_data = up_res.json()
        self.assertTrue(up_data["success"])
        self.assertGreaterEqual(len(up_data["allocations"]), 2)
        self.assertEqual(up_data["progress_pct"], 100.0)

        # 3. اختبار التوليد المباشر لحساب جديد عبر موصلات GitHub / Standby
        prov_res = self.client.post("/api/autoscale/provision-now")
        self.assertEqual(prov_res.status_code, 200)
        self.assertTrue(prov_res.json()["success"])
        self.assertIn("github_integrations_used", prov_res.json()["account"])

    def test_07_github_projects_code_integrations_and_reassembly(self) -> None:
        # 1. فحص التنفيذ المباشر لوحدات GitHub الأربعة المدمجة في backend/github_projects/
        v_res = self.client.get("/api/autoscale/verify-github-integrations")
        self.assertEqual(v_res.status_code, 200)
        v_data = v_res.json()
        self.assertTrue(v_data["verified"])
        self.assertGreater(v_data["cloudvault"]["test_chunks_created"], 1)
        self.assertTrue(v_data["autorclone"]["generated_sa"]["account_id"].startswith("mfc-"))
        self.assertEqual(v_data["gam_workspace"]["api_method"], "admin.directory_v1.users.insert")
        self.assertIn("CasdoorSDK", v_data["casdoor_sdk"]["sdk_class"])

        # 2. رفع ملف مقسم عبر حسابين ثم تنزيله والتأكد من إعادة التجميع وفحص SHA-256 (CloudVault Reassembler)
        up_res = self.client.post(
            "/api/autoscale/upload-seamless",
            json={
                "file_name": "ملف_اختبار_تجميع_CloudVault.bin",
                "size_mb": 8200.0,
                "virtual_path": "/كتب",
                "target_account_id": "gdrive_ngacademy_main",
            },
        )
        self.assertEqual(up_res.status_code, 200)
        files_res = self.client.get("/api/files?q=ملف_اختبار_تجميع_CloudVault")
        split_files = files_res.json()["files"]
        self.assertGreaterEqual(len(split_files), 2)

        dl_res = self.client.get(f"/api/files/{split_files[0]['id']}/download")
        self.assertEqual(dl_res.status_code, 200)
        self.assertIn(b"GamilCloudPool-CloudVault-Stream", dl_res.content)


if __name__ == "__main__":
    unittest.main()
