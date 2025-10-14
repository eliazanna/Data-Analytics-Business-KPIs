import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

#access to google sheets- scopes
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

#using streamlit "secret" - where apis password is hided
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],  # <-- legge dal pannello "Secrets"
    scopes=SCOPES
)
client = gspread.authorize(creds)

SHEET_NAME = "GestioneSocieta"

#sheets access
prodotti_ws = client.open(SHEET_NAME).worksheet("prodotti")
vendite_ws = client.open(SHEET_NAME).worksheet("vendite")
spese_ws = client.open(SHEET_NAME).worksheet("Spese")


