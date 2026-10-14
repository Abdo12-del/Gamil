"""
مدمج من مشروع GitHub مفتوح المصدر: Harshkhurdi/cloudVault
المستودع الأصلي: https://github.com/Harshkhurdi/cloudVault (backend/chunker.py & backend/engine.py)

يوفر:
- Chunker: تقسيم الملفات وتدفقات البايتات (Byte Streams) مع حساب بصمة SHA-256 لكل شريحة وللملف الكامل.
- CloudVaultStreamingEngine: توزيع شرائح الملف فعليًا على عقد التخزين المربوطة، وإعادة تجميع الملف (Reassembly)
  عند التنزيل مع التحقق الصارم من بصمة SHA-256 لكل جزء وللملف النهائي لضمان عدم ضياع أي بايت.
"""

import hashlib
import os
from typing import Any, Dict, Generator, List, Tuple

_IO_BLOCK = 4 * 1024 * 1024  # 4 MB streaming buffer (كما في Harshkhurdi/cloudVault/backend/engine.py)


class Chunker:
    """
    الكلاس الأصلي من Harshkhurdi/cloudVault/backend/chunker.py
    موسّع بدعم التقسيم غير المتساوي على حدود امتلاء الحسابات (Variable Slice Boundaries).
    """

    def __init__(self, chunk_size: int = 10 * 1024 * 1024) -> None:
        self.chunk_size = chunk_size

    @staticmethod
    def calculate_sha256(file_path: str) -> str:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(_IO_BLOCK), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    @staticmethod
    def calculate_bytes_sha256(data_bytes: bytes) -> str:
        return hashlib.sha256(data_bytes).hexdigest()

    def split_file(self, file_path: str) -> Generator[Tuple[int, bytes, str, int], None, None]:
        """
        Yields tuple: (chunk_index, chunk_data, chunk_hash, chunk_size)
        """
        chunk_index = 0
        with open(file_path, "rb") as f:
            while True:
                chunk_data = f.read(self.chunk_size)
                if not chunk_data:
                    break
                chunk_hash = hashlib.sha256(chunk_data).hexdigest()
                yield chunk_index, chunk_data, chunk_hash, len(chunk_data)
                chunk_index += 1

    def split_bytes(self, data_bytes: bytes) -> Generator[Tuple[int, bytes, str, int], None, None]:
        """
        Yields tuple: (chunk_index, chunk_data, chunk_hash, chunk_size)
        """
        total_len = len(data_bytes)
        offset = 0
        chunk_index = 0
        while offset < total_len:
            chunk_data = data_bytes[offset : offset + self.chunk_size]
            chunk_hash = hashlib.sha256(chunk_data).hexdigest()
            yield chunk_index, chunk_data, chunk_hash, len(chunk_data)
            offset += self.chunk_size
            chunk_index += 1

    @staticmethod
    def split_bytes_by_account_slices(
        data_bytes: bytes, slices: List[Dict[str, Any]], storage_root: str, session_id: str
    ) -> Dict[str, Any]:
        """
        تقسيم بايتات الملف الحقيقية وفق حدود السعة المتبقية لكل حساب (Overflow Slicing)
        وحفظ كل شريحة في مجلد الحساب الخاص بها مع حساب بصمة SHA-256 لكل شريحة وللملف الكامل.
        """
        os.makedirs(storage_root, exist_ok=True)
        full_sha256 = hashlib.sha256(data_bytes).hexdigest()
        total_len = len(data_bytes)
        total_planned = sum(max(1, int(s["bytes"])) for s in slices)

        offset = 0
        manifest_chunks: List[Dict[str, Any]] = []

        for idx, sl in enumerate(slices):
            if idx == len(slices) - 1:
                slice_bytes = data_bytes[offset:]
            else:
                ratio = int(sl["bytes"]) / total_planned if total_planned > 0 else 1.0
                cut_len = max(1, int(round(total_len * ratio)))
                slice_bytes = data_bytes[offset : offset + cut_len]
                offset += cut_len

            chunk_sha256 = hashlib.sha256(slice_bytes).hexdigest()
            acc_dir = os.path.join(storage_root, sl["account_id"])
            os.makedirs(acc_dir, exist_ok=True)

            chunk_filename = f"{session_id}_part{sl['part']}.chk"
            chunk_path = os.path.join(acc_dir, chunk_filename)
            with open(chunk_path, "wb") as cf:
                cf.write(slice_bytes)

            manifest_chunks.append(
                {
                    "part": sl["part"],
                    "account_id": sl["account_id"],
                    "account_name": sl["account_name"],
                    "chunk_path": chunk_path,
                    "actual_bytes": len(slice_bytes),
                    "planned_bytes": sl["bytes"],
                    "sha256": chunk_sha256,
                }
            )

        return {
            "full_sha256": full_sha256,
            "total_actual_bytes": total_len,
            "chunks": manifest_chunks,
        }

    @staticmethod
    def reassemble_file(chunk_bytes_list: List[bytes], output_path: str) -> str:
        """
        Takes an ordered list of chunk bytes and writes to output_path.
        """
        with open(output_path, "wb") as f:
            for chunk_data in chunk_bytes_list:
                f.write(chunk_data)
        return Chunker.calculate_sha256(output_path)

    @staticmethod
    def reassemble_and_verify_from_manifest(
        manifest_chunks: List[Dict[str, Any]], expected_full_sha256: str, output_path: str
    ) -> Dict[str, Any]:
        """
        يعيد تجميع الشرائح الموزعة عبر عدة حسابات ويتحقق من بصمة SHA-256 لكل شريحة وللملف المجمع بالكامل
        (كما في Harshkhurdi/cloudVault/backend/engine.py -> download_file).
        """
        full_hasher = hashlib.sha256()
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        ordered = sorted(manifest_chunks, key=lambda c: int(c["part"]))
        with open(output_path, "wb") as out:
            for ch in ordered:
                cpath = ch.get("chunk_path")
                if not cpath or not os.path.exists(cpath):
                    raise FileNotFoundError(f"مفقود جزء الملف #{ch['part']} في المسار {cpath}")
                actual_chunk_sha256 = Chunker.calculate_sha256(cpath)
                if ch.get("sha256") and actual_chunk_sha256 != ch["sha256"]:
                    raise ValueError(
                        f"فشل التحقق من سلامة الجزء #{ch['part']}: متوقع {ch['sha256']}، الفعلي {actual_chunk_sha256}"
                    )
                with open(cpath, "rb") as cf:
                    for block in iter(lambda: cf.read(_IO_BLOCK), b""):
                        out.write(block)
                        full_hasher.update(block)

        computed_full = full_hasher.hexdigest()
        if expected_full_sha256 and computed_full != expected_full_sha256:
            raise ValueError(
                f"فشل التحقق من بصمة الملف الكامل SHA-256 بعد التجميع: متوقع {expected_full_sha256}، الفعلي {computed_full}"
            )

        return {
            "verified": True,
            "sha256": computed_full,
            "output_path": output_path,
            "parts_reassembled": len(ordered),
        }
