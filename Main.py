import os
import secrets
import string
import questionary
from cryptography.exceptions import UnsupportedAlgorithm

from DataFileSetup import (
    DATA_FILE,
    ask_new_master_password,
    save_vault_and_recovery_sheet,
    setup_vault,
)
from VaultCrypto import EncryptedVault, InvalidCredential, SUPPORTED_VAULT_FORMATS, VaultFileError, read_document

# setup
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def select_menu(message, choices):
    return questionary.select(
        message, choices=choices, qmark="", erase_when_done=True
    ).unsafe_ask()


def save_data():
    vault_session.save()

def delete_all_data():
    confirm = questionary.confirm(
        "Are you sure you want to delete all data? This action cannot be undone.",
        default=False,
        qmark=""
    ).unsafe_ask()
    if not confirm:
        return

    try:
        vault_session.delete()
    except (OSError, VaultFileError) as error:
        print(f"Could not delete data.json: {error}")
        questionary.press_any_key_to_continue().unsafe_ask()
        return

    print("data.json has been deleted. First-run setup will open when you restart Key Keep.")
    raise SystemExit(0)



def startup():
    clear_screen()
    document, original = read_document(DATA_FILE)
    if document is None or document.get("format") not in SUPPORTED_VAULT_FORMATS:
        return setup_vault(DATA_FILE, document, original)

    while True:
        choice = select_menu("Unlock Key Keep", [
            "Enter Master Password", "Recover With a Backup Code",
            questionary.Separator(" "), "Exit",
        ])
        if choice == "Exit":
            return None

        recovery = choice == "Recover With a Backup Code"
        label = "Backup code" if recovery else "Master password"
        credential = questionary.password(label, qmark="").unsafe_ask()
        try:
            session = EncryptedVault.unlock(DATA_FILE, document, original, credential, recovery=recovery)
        except InvalidCredential:
            print(f"{label} did not unlock this vault.")
            continue
        finally:
            del credential

        if recovery:
            if session.uses_single_use_codes:
                print("Backup code accepted. Set a new master password to finish recovery.")
                session = session.consume_recovery_code(ask_different_master_password(session))
                remaining = session.remaining_recovery_codes
                print(f"Password updated. Code used. Unused backup codes: {remaining}.")
                if not remaining:
                    print("Reset your master password in Settings to generate a new recovery sheet.")
                questionary.press_any_key_to_continue().unsafe_ask()
            else:
                print("Legacy code accepted. Save a new sheet with four single-use codes.")
                session = replace_master_password(session)
        return session



# vaults screen functions
def ask_name(message, existing_names, default=""):
    def validate(value):
        name = value.strip()
        if not name:
            return "Name cannot be empty."
        if name in existing_names and name != default:
            return "That name already exists."
        return True

    return questionary.text(message, default=default, validate=validate, qmark="").unsafe_ask().strip()


def add_login(vault):
    clear_screen()
    print("Add Login")

    name = ask_name("Login name (e.g. Gmail)", vault)
    login = {
        "email": questionary.text("Email", qmark="").unsafe_ask().strip(),
        "password": questionary.password("Password", qmark="").unsafe_ask(),
        "details": questionary.text("Details", qmark="").unsafe_ask().strip(),
        "MasterPasswordRequired": questionary.confirm(
            "Require master password to view?", default=False, qmark=""
        ).unsafe_ask(),
    }

    while True:
        required = "On" if login["MasterPasswordRequired"] else "Off"
        choice = select_menu("Review login", [
            questionary.Choice(f"Name: {name}", value="name"),
            questionary.Choice(f"Email: {login['email']}", value="email"),
            questionary.Choice("Change Password", value="password"),
            questionary.Choice(f"Details: {login['details']}", value="details"),
            questionary.Choice(f"Master Password Required: {required}", value="toggle"),
            "Save Login",
            "Cancel",
        ])

        if choice == "name":
            name = ask_name("Login name", vault, default=name)
        elif choice == "email":
            login["email"] = questionary.text("Email", default=login["email"], qmark="").unsafe_ask().strip()
        elif choice == "password":
            login["password"] = questionary.password("Password", qmark="").unsafe_ask()
        elif choice == "details":
            login["details"] = questionary.text("Details", default=login["details"], qmark="").unsafe_ask().strip()
        elif choice == "toggle":
            login["MasterPasswordRequired"] = not login["MasterPasswordRequired"]
        elif choice == "Save Login":
            vault[name] = login
            save_data()
            return
        elif choice == "Cancel":
            return


def unlock_with_master_password(message="Master Password"):
    password = questionary.password(message, qmark="").unsafe_ask()
    if vault_session.password_matches(password):
        return True
    print("Incorrect master password.")
    questionary.press_any_key_to_continue().unsafe_ask()
    return False


def view_login(name, login):
    clear_screen()
    required = login.get("MasterPasswordRequired", False)
    if required and not unlock_with_master_password():
        return

    print(name)
    for field, value in login.items():
        if field != "MasterPasswordRequired":
            print(f"{field.capitalize()}: {value}")
    print("Master password required:", "On" if required else "Off")
    questionary.press_any_key_to_continue().unsafe_ask()


def vault_contents_screen(vault_name, vault):
    while True:
        clear_screen()

        choices = [questionary.Choice(name) for name in vault]
        if choices:
            choices.append(questionary.Separator(" "))
        else:
            print("Nothing added yet...")

        choices.extend([
            questionary.Choice("Add Login", value=1),
            questionary.Choice("Back", value=2),
        ])
        choice = select_menu(f"Contents of {vault_name}", choices)

        if choice == 1:
            add_login(vault)
        elif choice == 2:
            return
        else:
            view_login(choice, vault[choice])


def vaults_screen():
    vaults = data.setdefault("Vaults", {})
    protected_vaults = data.setdefault("VaultMasterPasswordRequired", {})
    while True:
        clear_screen()
        choices = [
            questionary.Choice(name, value=index)
            for index, name in enumerate(vaults)
        ]
        if choices:
            choices.append(questionary.Separator(" "))
        choices.extend(["New Vault", "Back to Menu"])
        selected = select_menu("Pick a vault", choices)
        if selected == "Back to Menu":
            return
        if selected == "New Vault":
            name = ask_name("Vault name", vaults)
            required = questionary.confirm(
                "Require the master password to open this vault?", default=False, qmark=""
            ).unsafe_ask()
            vaults[name] = {}
            if required:
                protected_vaults[name] = True
            save_data()
            continue

        vault_name = list(vaults)[selected]
        if protected_vaults.get(vault_name) and not unlock_with_master_password():
            continue

        while True:
            clear_screen()
            required = "On" if protected_vaults.get(vault_name) else "Off"
            choice = select_menu(vault_name, [
                "View Contents", "Rename Vault",
                questionary.Choice(f"Master Password Required: {required}", value="toggle_password"),
                questionary.Separator(" "),
                "Back to Vaults", "Back to Menu",
            ])

            if choice == "View Contents":
                vault_contents_screen(vault_name, vaults[vault_name])
            elif choice == "Rename Vault":
                new_name = ask_name("New vault name", vaults, default=vault_name)
                if new_name != vault_name:
                    vaults[new_name] = vaults.pop(vault_name)
                    if vault_name in protected_vaults:
                        protected_vaults[new_name] = protected_vaults.pop(vault_name)
                    vault_name = new_name
                    save_data()
            elif choice == "toggle_password":
                if protected_vaults.get(vault_name):
                    del protected_vaults[vault_name]
                else:
                    protected_vaults[vault_name] = True
                save_data()
            elif choice == "Back to Vaults":
                break
            elif choice == "Back to Menu":
                return





# generate password screen

def generate_password(length, include_symbols):
    groups = [string.ascii_lowercase, string.ascii_uppercase, string.digits]
    if include_symbols:
        groups.append(string.punctuation)

    characters = "".join(groups)
    password = [secrets.choice(group) for group in groups]
    password.extend(secrets.choice(characters) for _ in range(length - len(groups)))
    secrets.SystemRandom().shuffle(password)
    return "".join(password)


def valid_password_length(value):
    return (
        value.isascii() and value.isdecimal() and len(value) <= 3 and 8 <= int(value) <= 128
    ) or "Enter a length from 8 to 128."


def Generators_and_tools_screen():
    while True:
        clear_screen()
        choice = select_menu("Generators and Tools", [
            "Generate Password", "Back to Menu",
        ])
        if choice == "Back to Menu":
            return

        length = questionary.text(
            "Password length", default="20", validate=valid_password_length, qmark=""
        ).unsafe_ask()
        include_symbols = questionary.confirm("Include symbols?", default=True, qmark="").unsafe_ask()
        print(f"\nGenerated password: {generate_password(int(length), include_symbols)}")
        questionary.press_any_key_to_continue().unsafe_ask()





def ask_different_master_password(session):
    password = ask_new_master_password()
    while session.password_matches(password):
        print("Choose a password different from your current password.")
        password = ask_new_master_password()
    return password


def replace_master_password(session):
    password = ask_different_master_password(session)
    replacement, codes = session.rotate_credentials(password)
    del password
    save_vault_and_recovery_sheet(replacement, codes)
    print("Master password updated. Use the new recovery sheet with the current vault.")
    return replacement


def reset_master_password():
    global vault_session
    clear_screen()
    if not unlock_with_master_password("Current Master Password"):
        return
    print("Changing the password also replaces all four backup codes.")
    vault_session = replace_master_password(vault_session)
    questionary.press_any_key_to_continue().unsafe_ask()


def settings_screen():
    while True:
        clear_screen()
        choice = select_menu("Settings", [
            "Reset Master Password",
            "Self Destruct Setup",
            "DELETE ALL DATA IMMEDIATELY",
            questionary.Separator(" "),
            "Back to Menu",
        ])
        if choice == "Back to Menu":
            return
        elif choice == "DELETE ALL DATA IMMEDIATELY":
            delete_all_data()
        elif choice == "Reset Master Password":
            reset_master_password()


# main loop
def main():
    global vault_session, data
    vault_session = startup()
    if vault_session is None:
        return
    data = vault_session.data

    while True:
        clear_screen()
        choice = select_menu("Key Keep 0.0.01", [
            "View Vaults", "Generators and Tools", "Settings",
            questionary.Separator(" "),
            "Exit",
        ])

        if choice == "View Vaults":
            vaults_screen()
        elif choice == "Generators and Tools":
            Generators_and_tools_screen()
        elif choice == "Settings":
            settings_screen()
        elif choice == "Exit":
            return






# dw about this stuff, just a way to make sure the program exits gracefully when the user presses Ctrl+C or Ctrl+D
if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nExiting Key Keep.")
    except UnsupportedAlgorithm:
        raise SystemExit("Key Keep needs a cryptography build that supports Argon2id.") from None
    except (OSError, VaultFileError) as error:
        raise SystemExit(f"Key Keep: {error}") from None
