import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(
    r"D:\DESKTOP\Desktop\AppSocieta\creds.json",
    scopes=SCOPES
)
client = gspread.authorize(creds)

SHEET_NAME = "GestioneSocieta"
prodotti_ws = client.open(SHEET_NAME).worksheet("prodotti")
vendite_ws = client.open(SHEET_NAME).worksheet("vendite")
