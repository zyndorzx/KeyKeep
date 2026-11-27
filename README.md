![Key Keeper logo](logo.png)

Key Keeper is a terminal password manager. It stores logins in an encrypted local vault and lets you recover access with a printed backup code. The startup screen allows you to pick between the data being stored localy or on a cloud server you setup.

## Getting started

Run these commands from the `KEYKEEP_Terminal` directory in a Python environment.

```powershell
python -m pip install -r requirements.txt
python Main.py
```

1. Choose **Locally on this device**.
2. Create a strong master password and keep it written down somewhere. Master password requires at least 16 characters. 
3. Save the recovery PDF in a private separate device from the vault, a printed copy stored securely is also a great option.

All your data is stored in `data.json`. This project aims to protect your data when the actual json file gets out.

