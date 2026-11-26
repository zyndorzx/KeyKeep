import json
import os
import secrets
import string
import questionary

# setup
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def select_menu(message, choices):
    return questionary.select(
        message, choices=choices, qmark="", erase_when_done=True
    ).unsafe_ask()


with open("data.json", "r", encoding="utf-8") as f:
    data = json.load(f)
def save_data():
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
def master_password_matches(password):
    return password.strip().lower() == data["MasterPassword"].lower()




# startup usefull when we want to add some sort of backend users can host on their own servers and have everything sync across devices
def startup():
    clear_screen()

    while True:
        password = questionary.password("Master Password (or type EXIT)", qmark="").unsafe_ask()
        if master_password_matches(password):
            return True
        if password.strip().lower() == "exit":
            return False
        print("Incorrect master password. Please try again.")



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


def unlock_with_master_password():
    password = questionary.password("Master Password", qmark="").unsafe_ask()
    if master_password_matches(password):
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





# main loop
def main():
    if not startup():
        return

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
            print("Settings is not available yet.")
            questionary.press_any_key_to_continue().unsafe_ask()
        elif choice == "Exit":
            return






# dw about this stuff, just a way to make sure the program exits gracefully when the user presses Ctrl+C or Ctrl+D
if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nExiting Key Keep.")
