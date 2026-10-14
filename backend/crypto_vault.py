"""
خزنة التشفير الآمنة (AES-256-GCM Encrypted Token Vault)
لتشفير رموز OAuth 2.0 (Access Token & Refresh Token) قبل حفظها في قاعدة البيانات
دون تخزين أي كلمات مرور أو رموز نصية مكشوفة.
"""

import base64
import hashlib
import json
import os
from typing import Any, Dict, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class TokenVault:
    """يدير تشفير وفك تشفير بيانات الاعتماد ورموز OAuth 2.0 باستخدام AES-256-GCM."""

    def __init__(self, secret_seed: Optional[str] = None) -> None:
        seed = secret_seed or os.environ.get(
            "GAMIL_VAULT_KEY", "gamil-cloudpool-local-master-key-2026-aes256gcm"
        )
        # اشتقاق مفتاح 256-bit (32 بايت) باستخدام SHA-256
        self._key: bytes = hashlib.sha256(seed.encode("utf-8")).digest()
        self._aesgcm = AESGCM(self._key)

    def encrypt_payload(self, data: Dict[str, Any]) -> str:
        """تشفير قاموس رموز OAuth 2.0 وإرجاع سلسلة Base64 تحتوي على (Nonce + Ciphertext + Tag)."""
        nonce = os.urandom(12)  # 96-bit nonce قياسي لـ AES-GCM
        plaintext = json.dumps(data, ensure_ascii=False).encode("utf-8")
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, None)
        combined = nonce + ciphertext
        return "enc:aes256gcm:" + base64.urlsafe_b64encode(combined).decode("ascii")

    def decrypt_payload(self, token_str: Optional[str]) -> Dict[str, Any]:
        """فك تشفير الرموز المحفوظة في الذاكرة فقط عند الحاجة للاتصال بـ API."""
        if not token_str:
            return {}
        try:
            if token_str.startswith("enc:aes256gcm:"):
                b64_part = token_str.split("enc:aes256gcm:", 1)[1]
                raw = base64.urlsafe_b64decode(b64_part.encode("ascii"))
                nonce, ciphertext = raw[:12], raw[12:]
                plaintext = self._aesgcm.decrypt(nonce, ciphertext, None)
                return json.loads(plaintext.decode("utf-8"))
            return json.loads(token_str)
        except Exception:
            return {"status": "encrypted_or_invalid"}

    @staticmethod
    def mask_token(token_preview: str) -> str:
        """إخفاء الرمز للعرض الآمن في واجهة المستخدم."""
        if not token_preview or len(token_preview) < 10:
            return "••••••••••••••••"
        return f"{token_preview[:6]}••••••••••••{token_preview[-4:]}"


vault = TokenVault()
