"""First-run setup, plaintext migration, and recovery-sheet generation."""

import io
import os
import secrets
from pathlib import Path

import questionary
from cryptography.exceptions import UnsupportedAlgorithm
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from VaultCrypto import EncryptedVault, SUPPORTED_VAULT_FORMATS, VaultFileError, read_document


DATA_FILE = Path.cwd() / "data.json"


def ask_new_master_password():
    def validate(password):
        if len(password.strip()) < 16:
            return "Use at least 16 characters, ideally several randomly chosen words."
        return True

    while True:
        password = questionary.password(
            "New master password", validate=validate, qmark=""
        ).unsafe_ask()
        confirm = questionary.password("Confirm new master password", qmark="").unsafe_ask()
        if secrets.compare_digest(password.encode("utf-8"), confirm.encode("utf-8")):
            return password
        print("Passwords do not match. Try again.")


def _recovery_pdf(codes):
    stream = io.BytesIO()
    sheet = canvas.Canvas(stream, pagesize=letter)
    sheet.setTitle("Key Keep Recovery Codes")
    sheet.setAuthor("Key Keep")
    sheet.setFont("Helvetica-Bold", 22)
    sheet.drawString(48, 730, "Key Keep Recovery Codes")
    sheet.setFont("Helvetica", 11)
    sheet.drawString(
        48, 704, "Keep this sheet private and store it on another device that doesn't have access to the vault."
    )

    sheet.setFont("Helvetica", 12)
    for index, code in enumerate(codes):
        grouped = "-".join(code[i:i + 6] for i in range(0, len(code), 6))
        sheet.drawString(48, 673 - index * 24, grouped)
    sheet.showPage()
    sheet.save()
    return stream.getvalue()


def _write_new_pdf(path, contents):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, KeyboardInterrupt):
        path.unlink(missing_ok=True)
        raise


def save_vault_and_recovery_sheet(vault, codes):
    print("Save the recovery PDF somewhere private, separate from data.json.")
    print("Anyone with one code and the matching vault file can unlock it.")
    default = Path.home() / f"KeyKeep-Recovery-{vault.vault_id[:12]}.pdf"
    pdf = _recovery_pdf(codes)

    while True:
        filename = questionary.text("Recovery PDF path", default=str(default), qmark="").unsafe_ask()
        try:
            path = Path(filename.strip().strip('"')).expanduser()
            if path.suffix.lower() != ".pdf":
                print("Choose a filename ending in .pdf.")
                continue
            _write_new_pdf(path, pdf)
        except FileExistsError:
            print("That file already exists. Choose a different filename.")
        except (OSError, ValueError, RuntimeError) as error:
            print(f"Could not save the recovery PDF: {error}")
        else:
            break

    try:
        vault.save()
    except (OSError, VaultFileError):
        print(f"The sheet at {path} was written, but the vault was not saved. Check the vault before using it.")
        raise

    print(f"Recovery sheet saved to {path}")


def setup_vault(path, document, original):
    if document is None:
        print("Set up your encrypted Key Keep vault.")
        data = {"Vaults": {}}
    else:
        previous = document.get("MasterPassword")
        if "format" in document or not isinstance(previous, str) or not isinstance(document.get("Vaults"), dict):
            raise VaultFileError("data.json has an unrecognized format. It was left alone.")
        print("Upgrade the existing plaintext vault to encrypted storage.")
        print("Old copies, backups, and synced versions may still contain plaintext.")
        password = questionary.password("Current master password", qmark="").unsafe_ask()
        if not secrets.compare_digest(password.strip().lower().encode("utf-8"), previous.lower().encode("utf-8")):
            print("Incorrect current master password. The existing file was left alone.")
            return None
        data = {name: value for name, value in document.items() if name != "MasterPassword"}

    password = ask_new_master_password()
    while document is not None and password.strip().lower() == previous.lower():
        print("Choose a new password different from the previously stored password.")
        password = ask_new_master_password()

    vault, codes = EncryptedVault.create(path, original, data, password)
    save_vault_and_recovery_sheet(vault, codes)
    return vault


def main():
    document, original = read_document(DATA_FILE)
    if document is not None and document.get("format") in SUPPORTED_VAULT_FORMATS:
        print("An encrypted data.json already exists. Open it with Main.py.")
        return
    setup_vault(DATA_FILE, document, original)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled.")
    except UnsupportedAlgorithm:
        raise SystemExit("Key Keep needs a cryptography build that supports Argon2id.") from None
    except (OSError, VaultFileError) as error:
        raise SystemExit(f"Key Keep: {error}") from None
