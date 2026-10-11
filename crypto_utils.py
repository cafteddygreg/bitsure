"""
crypto_utils.py
---------------
Chiffrement authentifié des clés API Binance au repos avec préfixe "enc:v1:".
Utilise Fernet (AES-128-CBC + PKCS7 + HMAC-SHA256) via `cryptography` ou `libcrypto` (OpenSSL).
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.util
import hashlib
import hmac
import logging
import os
import struct
import time
from typing import Optional

import config

logger = logging.getLogger("crypto_utils")

ENCRYPTION_PREFIX = "enc:v1:"

try:
    from cryptography.fernet import Fernet as _CryptographyFernet, InvalidToken as _CryptographyInvalidToken  # type: ignore
except ImportError:
    _CryptographyFernet = None

    class _CryptographyInvalidToken(Exception):
        pass


InvalidToken = _CryptographyInvalidToken


class _OpenSSLFernet:
    """Implémentation conforme à la spécification Fernet (AES-128-CBC + PKCS7 + HMAC-SHA256) via OpenSSL libcrypto."""

    def __init__(self, key: bytes | str):
        if isinstance(key, str):
            key = key.encode("utf-8")
        raw = base64.urlsafe_b64decode(key)
        if len(raw) != 32:
            raise ValueError("Une clé Fernet doit représenter exactement 32 octets décodés en base64 urlsafe.")
        self._signing_key = raw[:16]
        self._encryption_key = raw[16:]
        lib_name = ctypes.util.find_library("crypto") or "libcrypto.so.3"
        self._lib = ctypes.CDLL(lib_name)
        self._lib.EVP_CIPHER_CTX_new.restype = ctypes.c_void_p
        self._lib.EVP_CIPHER_CTX_free.argtypes = [ctypes.c_void_p]
        self._lib.EVP_aes_128_cbc.restype = ctypes.c_void_p
        self._lib.EVP_EncryptInit_ex.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
        ]
        self._lib.EVP_EncryptUpdate.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.EVP_EncryptFinal_ex.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_int),
        ]
        self._lib.EVP_DecryptInit_ex.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
        ]
        self._lib.EVP_DecryptUpdate.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.EVP_DecryptFinal_ex.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_int),
        ]

    def _aes128_cbc(self, data: bytes, iv: bytes, encrypt_mode: bool) -> bytes:
        ctx = self._lib.EVP_CIPHER_CTX_new()
        if not ctx:
            raise RuntimeError("OpenSSL EVP_CIPHER_CTX_new failed")
        try:
            cipher = self._lib.EVP_aes_128_cbc()
            init_fn = self._lib.EVP_EncryptInit_ex if encrypt_mode else self._lib.EVP_DecryptInit_ex
            update_fn = self._lib.EVP_EncryptUpdate if encrypt_mode else self._lib.EVP_DecryptUpdate
            final_fn = self._lib.EVP_EncryptFinal_ex if encrypt_mode else self._lib.EVP_DecryptFinal_ex

            if init_fn(ctx, cipher, None, self._encryption_key, iv) != 1:
                raise InvalidToken("AES-128-CBC init failed")

            out_buf = ctypes.create_string_buffer(len(data) + 32)
            out_len = ctypes.c_int(0)
            if update_fn(ctx, out_buf, ctypes.byref(out_len), data, len(data)) != 1:
                raise InvalidToken("AES-128-CBC update failed")

            total_len = out_len.value
            final_buf = ctypes.create_string_buffer(32)
            final_len = ctypes.c_int(0)
            if final_fn(ctx, final_buf, ctypes.byref(final_len)) != 1:
                raise InvalidToken("AES-128-CBC padding/final failed")

            return out_buf.raw[:total_len] + final_buf.raw[: final_len.value]
        finally:
            self._lib.EVP_CIPHER_CTX_free(ctx)

    def encrypt(self, data: bytes | str) -> bytes:
        if isinstance(data, str):
            data = data.encode("utf-8")
        iv = os.urandom(16)
        ciphertext = self._aes128_cbc(data, iv, encrypt_mode=True)
        basic_parts = b"\x80" + struct.pack(">Q", int(time.time())) + iv + ciphertext
        mac = hmac.new(self._signing_key, basic_parts, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(basic_parts + mac)

    def decrypt(self, token: bytes | str) -> bytes:
        if isinstance(token, str):
            token = token.encode("utf-8")
        try:
            decoded = base64.urlsafe_b64decode(token)
        except Exception as exc:
            raise InvalidToken("Invalid base64 Fernet token") from exc
        if len(decoded) < 1 + 8 + 16 + 16 + 32:
            raise InvalidToken("Fernet token too short")
        if decoded[0] != 0x80:
            raise InvalidToken("Unsupported Fernet version")
        basic_parts = decoded[:-32]
        mac = decoded[-32:]
        expected_mac = hmac.new(self._signing_key, basic_parts, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected_mac):
            raise InvalidToken("Fernet HMAC verification failed")
        iv = decoded[9:25]
        ciphertext = decoded[25:-32]
        if len(ciphertext) % 16 != 0:
            raise InvalidToken("Invalid AES block length")
        return self._aes128_cbc(ciphertext, iv, encrypt_mode=False)


def _is_production_or_postgres(env: Optional[str] = None, database_url: Optional[str] = None) -> bool:
    eff_env = (env if env is not None else os.environ.get("ENV", "")).strip().lower()
    eff_db = (database_url if database_url is not None else os.environ.get("DATABASE_URL", "")).strip().lower()
    if eff_env == "production":
        return True
    if eff_db.startswith("postgres://") or eff_db.startswith("postgresql://"):
        return True
    return False


def _normalize_fernet_key(raw_key: str) -> bytes:
    cleaned = raw_key.strip()
    try:
        decoded = base64.urlsafe_b64decode(cleaned.encode("utf-8"))
        if len(decoded) == 32:
            return cleaned.encode("utf-8")
    except Exception:
        pass
    digest = hashlib.sha256(cleaned.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def resolve_encryption_key(
    encryption_key: Optional[str] = None,
    *,
    env: Optional[str] = None,
    database_url: Optional[str] = None,
) -> bytes:
    """
    Résout la clé de chiffrement à partir de ENCRYPTION_KEY.
    Si ENCRYPTION_KEY est absente :
      - en production (ENV=production) ou avec PostgreSQL (DATABASE_URL postgres*) : lève RuntimeError ;
      - en local / SQLite : émet un warning et utilise une clé locale dérivée.
    """
    raw = encryption_key if encryption_key is not None else (getattr(config, "ENCRYPTION_KEY", "") or os.environ.get("ENCRYPTION_KEY", ""))
    raw = (raw or "").strip()
    if not raw:
        if _is_production_or_postgres(env=env, database_url=database_url):
            raise RuntimeError(
                "CRITICAL: ENCRYPTION_KEY est absente alors que l'environnement est en production ou utilise PostgreSQL."
            )
        logger.warning(
            "ENCRYPTION_KEY absente en environnement local/SQLite : utilisation d'une clé de développement locale."
        )
        fallback_seed = getattr(config, "SESSION_SECRET", "") or "bitsure-local-sqlite-dev-encryption-key"
        return _normalize_fernet_key(fallback_seed)
    return _normalize_fernet_key(raw)


def _get_cipher(encryption_key: Optional[str] = None):
    key_bytes = resolve_encryption_key(encryption_key)
    if _CryptographyFernet is not None:
        return _CryptographyFernet(key_bytes)
    return _OpenSSLFernet(key_bytes)


def encrypt(value: str, *, encryption_key: Optional[str] = None) -> str:
    """Chiffre une chaîne et préfixe le résultat par 'enc:v1:'."""
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    if text.startswith(ENCRYPTION_PREFIX):
        return text
    cipher = _get_cipher(encryption_key)
    token = cipher.encrypt(text.encode("utf-8")).decode("utf-8")
    return f"{ENCRYPTION_PREFIX}{token}"


def decrypt(value: str, *, encryption_key: Optional[str] = None) -> str:
    """
    Déchiffre une chaîne préfixée par 'enc:v1:'.
    Si la valeur ne possède pas le préfixe 'enc:v1:', la renvoie telle quelle (compatibilité migration).
    """
    if value is None:
        return ""
    text = str(value)
    if not text or not text.startswith(ENCRYPTION_PREFIX):
        return text
    token = text[len(ENCRYPTION_PREFIX) :]
    cipher = _get_cipher(encryption_key)
    plaintext = cipher.decrypt(token.encode("utf-8"))
    return plaintext.decode("utf-8")


# Validation dès l'import du module au démarrage
resolve_encryption_key()
