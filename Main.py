import json
import os
import secrets
import string

import questionary


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


with open("data.json", "r", encoding="utf-8") as f:
    data = json.load(f)


def save_data():
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def master_password_matches(password):
    return password.strip().lower() == data["MasterPassword"].lower()


def startup():
    clear_screen()

    while True:
        password = questionary.password("Master Password (or type EXIT)").unsafe_ask()
        if master_password_matches(password):
            return True
        if password.strip().lower() == "exit":
            return False
        print("Incorrect master password. Please try again.")


def ask_name(message, existing_names, default=""):
    def validate(value):
        name = value.strip()
        if not name:
            return "Name cannot be empty."
        if name in existing_names and name != default:
            return "That name already exists."
        return True

    return questionary.text(message, default=default, validate=validate).unsafe_ask().strip()


def add_login(vault):
    clear_screen()
    print("Add Login")

    name = ask_name("Login name (e.g. Gmail)", vault)
    login = {
        "email": questionary.text("Email").unsafe_ask().strip(),
        "password": questionary.password("Password").unsafe_ask(),
        "details": questionary.text("Details").unsafe_ask().strip(),
        "MasterPasswordRequired": questionary.confirm(
            "Require master password to view?", default=False
        ).unsafe_ask(),
    }

    while True:
        required = "On" if login["MasterPasswordRequired"] else "Off"
        choice = questionary.select("Review login", choices=[
            questionary.Choice(f"Name: {name}", value="name"),
            questionary.Choice(f"Email: {login['email']}", value="email"),
            questionary.Choice("Change Password", value="password"),
            questionary.Choice(f"Details: {login['details']}", value="details"),
            questionary.Choice(f"Master Password Required: {required}", value="toggle"),
            "Save Login",
            "Cancel",
        ]).unsafe_ask()

        if choice == "name":
            name = ask_name("Login name", vault, default=name)
        elif choice == "email":
            login["email"] = questionary.text("Email", default=login["email"]).unsafe_ask().strip()
        elif choice == "password":
            login["password"] = questionary.password("Password").unsafe_ask()
        elif choice == "details":
            login["details"] = questionary.text("Details", default=login["details"]).unsafe_ask().strip()
        elif choice == "toggle":
            login["MasterPasswordRequired"] = not login["MasterPasswordRequired"]
        elif choice == "Save Login":
            vault[name] = login
            save_data()
            return
        elif choice == "Cancel":
            return


def view_login(name, login):
    clear_screen()
    required = login.get("MasterPasswordRequired", False)
    if required:
        password = questionary.password("Master Password").unsafe_ask()
        if not master_password_matches(password):
            print("Incorrect master password.")
            questionary.press_any_key_to_continue().unsafe_ask()
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
        print(f"Contents of {vault_name}\n")

        logins = {str(number): name for number, name in enumerate(vault, start=3)}
        if not logins:
            print("Nothing added yet...")
        for login_id, name in logins.items():
            print(f"[{login_id}] {name}")

        print("\n[1] Add Login")
        print("[2] Back")
        choice = questionary.text(
            "Choose an option or enter a login ID",
            validate=lambda value: (
                value.strip() in ("1", "2") or value.strip() in logins
                or "Enter one of the numbers shown."
            ),
        ).unsafe_ask().strip()

        if choice == "1":
            add_login(vault)
        elif choice == "2":
            return
        else:
            name = logins[choice]
            view_login(name, vault[name])


def vaults_screen():
    vaults = data.get("Vaults", {})
    while True:
        clear_screen()
        choices = [
            questionary.Choice(name, value=index)
            for index, name in enumerate(vaults)
        ]
        choices.append("Back to Menu")
        selected = questionary.select("Pick a vault", choices=choices).unsafe_ask()
        if selected == "Back to Menu":
            return

        vault_name = list(vaults)[selected]
        while True:
            clear_screen()
            choice = questionary.select(vault_name, choices=[
                "View Contents", "Rename Vault", "Back to Vaults", "Back to Menu",
            ]).unsafe_ask()

            if choice == "View Contents":
                vault_contents_screen(vault_name, vaults[vault_name])
            elif choice == "Rename Vault":
                new_name = ask_name("New vault name", vaults, default=vault_name)
                if new_name != vault_name:
                    vaults[new_name] = vaults.pop(vault_name)
                    vault_name = new_name
                    save_data()
            elif choice == "Back to Vaults":
                break
            elif choice == "Back to Menu":
                return


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
        choice = questionary.select("Generators and Tools", choices=[
            "Generate Password", "Back to Menu",
        ]).unsafe_ask()
        if choice == "Back to Menu":
            return

        length = questionary.text(
            "Password length", default="20", validate=valid_password_length
        ).unsafe_ask()
        include_symbols = questionary.confirm("Include symbols?", default=True).unsafe_ask()
        print(f"\nGenerated password: {generate_password(int(length), include_symbols)}")
        questionary.press_any_key_to_continue().unsafe_ask()


def main():
    if not startup():
        return

    while True:
        clear_screen()
        choice = questionary.select("Key Keep 0.0.01", choices=[
            "View Vaults", "Generators and Tools", "Settings", "Exit",
        ]).unsafe_ask()

        if choice == "View Vaults":
            vaults_screen()
        elif choice == "Generators and Tools":
            Generators_and_tools_screen()
        elif choice == "Settings":
            print("Settings is not available yet.")
            questionary.press_any_key_to_continue().unsafe_ask()
        elif choice == "Exit":
            return


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nExiting Key Keep.")
