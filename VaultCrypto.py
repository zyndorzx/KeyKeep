"""Versioned encryption and storage for Key Keep's local vault."""

import base64
import binascii
import json
import os
import secrets
import tempfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from filelock import FileLock


LEGACY_VAULT_FORMAT = "keykeep-v1"
VAULT_FORMAT = "keykeep-v2"
SUPPORTED_VAULT_FORMATS = (LEGACY_VAULT_FORMAT, VAULT_FORMAT)
RECOVERY_CODE_COUNT = 4


class VaultFileError(ValueError):
    """The file is invalid, damaged, or has changed on disk."""


class InvalidCredential(ValueError):
    """The supplied credential could not unlock a data key."""


def _json_bytes(value, *, sort_keys=True):
    return json.dumps(value, ensure_ascii=True, sort_keys=sort_keys, separators=(",", ":")).encode("utf-8")


def _encode(value):
    return base64.b64encode(value).decode("ascii")


def _decode(value, size=None):
    if not isinstance(value, str):
        raise VaultFileError("Invalid encrypted vault field.")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise VaultFileError("Invalid encoded vault field.") from error
    if size is not None and len(raw) != size:
        raise VaultFileError("Invalid encrypted vault field length.")
    return raw


def _credential_key(credential, salt):
    # The format fixes the cost in code. A file cannot request weaker or larger settings.
    return Argon2id(
        salt=salt, length=32, iterations=3, lanes=4, memory_cost=256 * 1024
    ).derive(credential)


def _seal(plaintext, key, context):
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, context)
    return {"nonce": _encode(nonce), "ciphertext": _encode(ciphertext)}


def _unseal(box, key, context):
    if not isinstance(box, dict):
        raise VaultFileError("Invalid encrypted vault field.")
    nonce = _decode(box.get("nonce"), 12)
    ciphertext = _decode(box.get("ciphertext"))
    if len(ciphertext) < 16:
        raise VaultFileError("The encrypted vault field is truncated.")
    return AESGCM(key).decrypt(nonce, ciphertext, context)


def _wrap_key(data_key, credential, context):
    salt = secrets.token_bytes(16)
    box = _seal(data_key, _credential_key(credential, salt), context)
    return {"salt": _encode(salt), **box}


def _unwrap_key(slot, credential, context):
    if not isinstance(slot, dict):
        raise VaultFileError("Invalid vault credential slot.")
    salt = _decode(slot.get("salt"), 16)
    key = _unseal(slot, _credential_key(credential, salt), context)
    if len(key) != 32:
        raise VaultFileError("Invalid vault data key.")
    return key


def _slot_context(format_name, vault_id, slot):
    return f"{format_name}:{vault_id}:{slot}".encode("ascii")


def _recovery_private_key(code, vault_id):
    seed = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=bytes.fromhex(vault_id),
        info=b"Key Keep v2 recovery private key",
    ).derive(code)
    return X25519PrivateKey.from_private_bytes(seed)


def _recovery_wrapping_key(private_key, peer_bytes, context, recipient, ephemeral):
    shared = private_key.exchange(X25519PublicKey.from_public_bytes(peer_bytes))
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None,
        info=b"Key Keep v2 recovery wrapping key\0" + context + recipient + ephemeral,
    ).derive(shared)


def _wrap_recovery_key(data_key, recipient, context):
    sender_key = X25519PrivateKey.generate()
    ephemeral = sender_key.public_key().public_bytes_raw()
    key = _recovery_wrapping_key(sender_key, recipient, context, recipient, ephemeral)
    return {"public": _encode(recipient), "ephemeral": _encode(ephemeral), **_seal(data_key, key, context)}


def _recover_key(header, code):
    format_name, vault_id = header["format"], header["id"]
    private = _recovery_private_key(code, vault_id) if format_name == VAULT_FORMAT else None
    public = private.public_key().public_bytes_raw() if private is not None else None
    for index, slot in enumerate(header["recovery"]):
        if slot is None and private is not None:
            continue
        context = _slot_context(format_name, vault_id, f"recovery-{index}")
        if private is None:
            try:
                return _unwrap_key(slot, code, context), index
            except InvalidTag:
                continue
        if not isinstance(slot, dict):
            raise VaultFileError("Invalid recovery slot.")
        recipient = _decode(slot.get("public"), 32)
        if recipient != public:
            continue
        try:
            ephemeral = _decode(slot.get("ephemeral"), 32)
            key = _recovery_wrapping_key(private, ephemeral, context, recipient, ephemeral)
            data_key = _unseal(slot, key, context)
        except (InvalidTag, ValueError) as error:
            raise VaultFileError("The recovery slot failed its integrity check.") from error
        if len(data_key) != 32:
            raise VaultFileError("Invalid vault data key.")
        return data_key, index
    raise InvalidCredential()


def _payload_context(header):
    # Authenticate the envelope and all credential slots with the vault contents.
    return b"Key Keep payload\0" + _json_bytes(header)


def read_document(path):
    """Read the on-disk format and retain the original bytes for checked saves."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, None
    try:
        document = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise VaultFileError("data.json is not valid JSON.") from error
    if not isinstance(document, dict):
        raise VaultFileError("data.json has an unrecognized format.")
    return document, raw


def _replace_document(path, expected, contents):
    # The temporary file is in the same directory and contains ciphertext only.
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".keykeep-", delete=False) as stream:
            temporary_path = Path(stream.name)
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())

        with _write_lock(path):
            try:
                actual = path.read_bytes()
            except FileNotFoundError:
                actual = None
            if actual != expected:
                raise VaultFileError("data.json changed on disk. Restart Key Keep before saving.")
            if expected is None:
                # Publish a complete new file without overwriting any file created meanwhile.
                if os.name == "nt":
                    temporary_path.rename(path)
                else:
                    os.link(temporary_path, path)
            else:
                os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _write_lock(path):
    return FileLock(path.with_name(".keykeep-data.lock"), timeout=5)


class EncryptedVault:
    """An unlocked session. Only the data key and vault contents stay in memory."""

    def __init__(self, path, original, header, data_key, data, recovered_slot=None):
        self.path = path
        self.vault_id = header["id"]
        self.data = data
        self._original = original
        self._header = header
        self._data_key = data_key
        self._recovered_slot = recovered_slot

    @property
    def uses_single_use_codes(self):
        return self._header["format"] == VAULT_FORMAT

    @property
    def remaining_recovery_codes(self):
        return sum(slot is not None for slot in self._header["recovery"])

    @classmethod
    def _create_with_recipients(cls, path, original, data, password, vault_id, recipients):
        data_key = AESGCM.generate_key(bit_length=256)
        header = {
            "format": VAULT_FORMAT,
            "id": vault_id,
            "password": _wrap_key(
                data_key, password.encode("utf-8"), _slot_context(VAULT_FORMAT, vault_id, "password")
            ),
            "recovery": [
                None if recipient is None else _wrap_recovery_key(
                    data_key, recipient, _slot_context(VAULT_FORMAT, vault_id, f"recovery-{index}")
                )
                for index, recipient in enumerate(recipients)
            ],
        }
        return cls(path, original, header, data_key, data)

    @classmethod
    def create(cls, path, original, data, password):
        vault_id = secrets.token_hex(16)
        codes = [secrets.token_hex(24).upper() for _ in range(RECOVERY_CODE_COUNT)]
        recipients = [
            _recovery_private_key(bytes.fromhex(code), vault_id).public_key().public_bytes_raw()
            for code in codes
        ]
        return cls._create_with_recipients(path, original, data, password, vault_id, recipients), codes

    @classmethod
    def unlock(cls, path, document, original, credential, *, recovery=False):
        format_name = document.get("format")
        if format_name not in SUPPORTED_VAULT_FORMATS:
            raise VaultFileError("This encrypted vault version is not supported.")
        vault_id = document.get("id")
        if not isinstance(vault_id, str) or len(vault_id) != 32 or any(c not in "0123456789abcdef" for c in vault_id):
            raise VaultFileError("Invalid vault ID.")
        slots = document.get("recovery")
        if not isinstance(slots, list) or len(slots) != RECOVERY_CODE_COUNT:
            raise VaultFileError("Invalid recovery slots.")
        header = {name: document.get(name) for name in ("format", "id", "password", "recovery")}
        recovered_slot = None
        if recovery:
            code = "".join(credential.split()).replace("-", "")
            if len(code) != 48 or any(c not in "0123456789abcdefABCDEF" for c in code):
                raise InvalidCredential()
            data_key, recovered_slot = _recover_key(header, bytes.fromhex(code))
        else:
            try:
                data_key = _unwrap_key(
                    header["password"], credential.encode("utf-8"), _slot_context(format_name, vault_id, "password")
                )
            except InvalidTag as error:
                raise InvalidCredential() from error

        try:
            plaintext = _unseal(document.get("vault"), data_key, _payload_context(header))
            data = json.loads(plaintext)
        except (InvalidTag, ValueError, UnicodeError) as error:
            raise VaultFileError("The encrypted vault failed its integrity check.") from error
        if not isinstance(data, dict) or not isinstance(data.get("Vaults"), dict) or "MasterPassword" in data:
            raise VaultFileError("The encrypted vault contents have an invalid format.")
        return cls(path, original, header, data_key, data, recovered_slot)

    def password_matches(self, password):
        try:
            key = _unwrap_key(
                self._header["password"], password.encode("utf-8"),
                _slot_context(self._header["format"], self.vault_id, "password"),
            )
        except InvalidTag:
            return False
        return secrets.compare_digest(key, self._data_key)

    def rotate_credentials(self, password):
        """Prepare a new data key, password slot, and four recovery slots."""
        return self.create(self.path, self._original, self.data, password)

    def consume_recovery_code(self, password):
        """Save a fresh data key that the used code cannot unwrap."""
        if not self.uses_single_use_codes or self._recovered_slot is None:
            raise VaultFileError("A single-use recovery code is required.")
        recipients = [
            None if slot is None or index == self._recovered_slot else _decode(slot.get("public"), 32)
            for index, slot in enumerate(self._header["recovery"])
        ]
        replacement = self._create_with_recipients(
            self.path, self._original, self.data, password, self.vault_id, recipients
        )
        replacement.save()
        return replacement

    def save(self):
        encrypted = _seal(_json_bytes(self.data, sort_keys=False), self._data_key, _payload_context(self._header))
        contents = _json_bytes({**self._header, "vault": encrypted}) + b"\n"
        _replace_document(self.path, self._original, contents)
        self._original = contents

    def delete(self):
        with _write_lock(self.path):
            if self.path.read_bytes() != self._original:
                raise VaultFileError("data.json changed on disk. Restart Key Keep before deleting.")
            self.path.unlink()
