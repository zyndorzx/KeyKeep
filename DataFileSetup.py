import json
from pathlib import Path

data = {
    "MasterPassword": "my_secure_password",
    "Vaults": {
        "Vault1": {
            "Gmail":{
                "email": "example@gmail.com",
                "password": "password123",
                "details": "This is a sample Gmail account for testing purposes.",
                "MasterPasswordRequired": False,
            },
            "Netflex":{
                "email": "example@gmail.com",
                "password": "password123",
                "details": "This is a sample Netflex account for testing purposes.",
                "MasterPasswordRequired": True,
            },
        },
    }
}




Template = {
    "MasterPassword": "my_secure_password",
    "Vaults": {
        "Vault1": {
        },
    }
}



data_file = Path("data.json")
if not data_file.exists():
    print("Creating data.json file...")
    with data_file.open("w", encoding="utf-8") as f:
        json.dump(Template, f, ensure_ascii=False, indent=2)
else:
    print("data.json file already exists.")