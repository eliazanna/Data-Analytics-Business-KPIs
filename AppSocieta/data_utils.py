import pandas as pd
import re
import requests
import streamlit as st   
# ---------------------------------------------------
# 🧹 Pulizia prezzi
# ---------------------------------------------------
def _clean_price(val):
    """Rimuove simboli di valuta, spazi e converte virgole in punti."""
    if pd.isna(val):
        return 0.0
    val = str(val)
    val = re.sub(r"[^\d,.-]", "", val)
    val = val.replace(",", ".")
    try:
        return float(val)
    except ValueError:
        return 0.0


# ---------------------------------------------------
# 📥 Lettura e scrittura su Google Sheets
# ---------------------------------------------------
def get_data(ws):
    """Scarica i dati da un worksheet gspread e li trasforma in DataFrame."""
    try:
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        print("Errore durante la lettura dal foglio:", e)
        return pd.DataFrame()


def add_row(ws, row):
    """Aggiunge una riga al worksheet."""
    try:
        ws.append_row(row)
    except Exception as e:
        print("Errore durante l'aggiunta di una riga:", e)


# ---------------------------------------------------
# 📦 Aggiornamento inventario
# ---------------------------------------------------
def aggiorna_inventario(df_prodotti, df_vendite):
    """Aggiorna le quantità rimanenti nell'inventario dopo le vendite."""
    if df_vendite.empty or df_prodotti.empty:
        return df_prodotti

    df = df_prodotti.copy()
    df["Quantita"] = pd.to_numeric(df["Quantita"], errors="coerce").fillna(0)

    for _, v in df_vendite.iterrows():
        nome = str(v["Prodotto"]).strip()
        qta_venduta = pd.to_numeric(v["Quantita"], errors="coerce")
        if pd.isna(qta_venduta):
            continue
        idx = df[df["Nome"].astype(str).str.strip() == nome].index
        if not idx.empty:
            i = idx[0]
            df.loc[i, "Quantita"] = max(df.loc[i, "Quantita"] - qta_venduta, 0)
    return df


# ---------------------------------------------------
# 💰 Calcolo bilancio (Elia ↔ Tommy)
# ---------------------------------------------------
def calcola_bilancio(df_prodotti, df_vendite):
    """
    Calcola spese, entrate e saldo reale tra Elia e Tommy:
    - chi ha speso di più deve ricevere la metà della differenza
    - le vendite si dividono 50/50, quindi chi vende deve dare metà all'altro
    """

    if df_prodotti.empty:
        return {
            "spesa_elia": 0.0,
            "spesa_tommy": 0.0,
            "entrate_elia": 0.0,
            "entrate_tommy": 0.0,
            "totale_spese": 0.0,
            "totale_entrate": 0.0,
            "saldo_elia": 0.0,
            "saldo_tommy": 0.0,
            "pareggio": 0.0,
        }

    # --- Pulizia dati ---
    df_prodotti = df_prodotti.copy()
    df_prodotti["Prezzo_unitario"] = df_prodotti["Prezzo_unitario"].apply(_clean_price)
    df_prodotti["Quantita"] = pd.to_numeric(df_prodotti["Quantita"], errors="coerce").fillna(0)

    # --- Calcolo spese ---
    df_prodotti["Spesa_totale"] = (df_prodotti["Prezzo_unitario"] * df_prodotti["Quantita"]).round(2)
    spese_per_socio = df_prodotti.groupby("Comprato_da")["Spesa_totale"].sum().to_dict()

    spesa_elia = round(spese_per_socio.get("Elia", 0.0), 2)
    spesa_tommy = round(spese_per_socio.get("Tommy", 0.0), 2)
    totale_spese = round(spesa_elia + spesa_tommy, 2)

    # --- Calcolo entrate ---
    entrate_elia = entrate_tommy = 0.0
    if not df_vendite.empty:
        df_vendite = df_vendite.copy()
        if "Prezzo_totale_vendita" in df_vendite.columns:
            df_vendite["Prezzo_totale_vendita"] = df_vendite["Prezzo_totale_vendita"].apply(_clean_price)
        if "Venditore" not in df_vendite.columns:
            df_vendite["Venditore"] = "Elia"
        entrate_elia = round(df_vendite.loc[df_vendite["Venditore"] == "Elia", "Prezzo_totale_vendita"].sum(), 2)
        entrate_tommy = round(df_vendite.loc[df_vendite["Venditore"] == "Tommy", "Prezzo_totale_vendita"].sum(), 2)

    totale_entrate = round(entrate_elia + entrate_tommy, 2)

    # --- Calcolo saldo reale ---
    diff_spese = spesa_elia - spesa_tommy
    diff_entrate = entrate_elia - entrate_tommy
    saldo_elia = round((diff_spese / 2) - (diff_entrate / 2), 2)
    saldo_tommy = round(-saldo_elia, 2)

    pareggio = round(totale_spese - totale_entrate, 2)

    return {
        "spesa_elia": spesa_elia,
        "spesa_tommy": spesa_tommy,
        "entrate_elia": entrate_elia,
        "entrate_tommy": entrate_tommy,
        "totale_spese": totale_spese,
        "totale_entrate": totale_entrate,
        "saldo_elia": saldo_elia,
        "saldo_tommy": saldo_tommy,
        "pareggio": pareggio,
    }


# ---------------------------------------------------
# 🧾 Gestione vendite multiple
# ---------------------------------------------------
def registra_vendita_multipla(df_prodotti, vendita_dict, prezzo_totale, venditore):
    """
    Registra una vendita con più prodotti insieme.
    vendita_dict = {"ProdottoA": quantita, "ProdottoB": quantita}
    Divide il prezzo totale in proporzione ai costi dei prodotti venduti.
    Restituisce una lista di righe vendite (per scrivere su Google Sheets)
    e l'inventario aggiornato.
    """

    df = df_prodotti.copy()
    df["Prezzo_unitario"] = df["Prezzo_unitario"].apply(_clean_price)

    # Calcola costo totale dei prodotti coinvolti
    costo_totale = 0
    for nome, qta in vendita_dict.items():
        riga = df[df["Nome"].astype(str).str.strip() == nome]
        if not riga.empty:
            costo_totale += float(riga["Prezzo_unitario"].values[0]) * qta

    if costo_totale == 0:
        return [], df  # nessun prodotto valido

    vendite_generate = []
    for nome, qta in vendita_dict.items():
        riga = df[df["Nome"].astype(str).str.strip() == nome]
        if riga.empty:
            continue

        costo_unit = float(riga["Prezzo_unitario"].values[0])
        costo_tot = costo_unit * qta
        quota_ricavo = (costo_tot / costo_totale) * prezzo_totale
        prezzo_unit_vendita = round(quota_ricavo / qta, 2)

        vendite_generate.append([
            nome,
            qta,
            round(quota_ricavo, 2),
            venditore
        ])

        # Aggiorna inventario
        idx = df[df["Nome"].astype(str).str.strip() == nome].index
        if not idx.empty:
            i = idx[0]
            df.loc[i, "Quantita"] = max(df.loc[i, "Quantita"] - qta, 0)

    return vendite_generate, df


# ---------------------------------------------------
# 📊 Analisi vendite: "King della vendita"
# ---------------------------------------------------
def analisi_vendite(df_prodotti, df_vendite):
    """
    Crea una tabella comparativa tra Elia e Tommy con:
    - numero di ordini (non singoli prodotti)
    - ricavo totale
    - costo totale
    - guadagno totale
    - plusvalenza media ponderata
    """

    if df_vendite.empty or df_prodotti.empty:
        return pd.DataFrame(columns=[
            "Venditore", "Ordini registrati", "Ricavo totale (€)",
            "Costo totale (€)", "Guadagno totale (€)", "Plusvalenza media (%)"
        ])

    df_prodotti = df_prodotti.copy()
    df_vendite = df_vendite.copy()

    # pulizia
    df_prodotti["Prezzo_unitario"] = df_prodotti["Prezzo_unitario"].apply(_clean_price)
    df_vendite["Prezzo_totale_vendita"] = df_vendite["Prezzo_totale_vendita"].apply(_clean_price)
    df_vendite["Quantita"] = pd.to_numeric(df_vendite["Quantita"], errors="coerce").fillna(0)

    risultati = []

    for venditore in ["Elia", "Tommy"]:
        vendite_v = df_vendite[df_vendite["Venditore"] == venditore]
        if vendite_v.empty:
            risultati.append({
                "Venditore": venditore,
                "Ordini registrati": 0,
                "Ricavo totale (€)": 0.0,
                "Costo totale (€)": 0.0,
                "Guadagno totale (€)": 0.0,
                "Plusvalenza media (%)": 0.0,
            })
            continue

        # --- Ricavo totale e numero ordini (conteggio righe vendita)
        ricavo_totale = vendite_v["Prezzo_totale_vendita"].sum()
        ordini = len(vendite_v)

        # --- Calcolo costo totale
        costo_totale = 0
        plusvalenze = []
        for _, r in vendite_v.iterrows():
            nome = str(r["Prodotto"]).strip()
            qta = r["Quantita"]
            prezzo_vendita = float(r["Prezzo_totale_vendita"])
            prezzo_acquisto = df_prodotti.loc[df_prodotti["Nome"] == nome, "Prezzo_unitario"]

            if not prezzo_acquisto.empty:
                costo = float(prezzo_acquisto.values[0]) * qta
                costo_totale += costo
                if costo > 0:
                    plusvalenze.append((prezzo_vendita - costo) / costo * 100)

        guadagno = ricavo_totale - costo_totale
        plusvalenza_media = sum(plusvalenze) / len(plusvalenze) if plusvalenze else 0

        risultati.append({
            "Venditore": venditore,
            "Ordini registrati": ordini,
            "Ricavo totale (€)": round(ricavo_totale, 2),
            "Costo totale (€)": round(costo_totale, 2),
            "Guadagno totale (€)": round(guadagno, 2),
            "Plusvalenza media (%)": round(plusvalenza_media, 2)
        })

    df_risultati = pd.DataFrame(risultati)

    # ordina per guadagno totale decrescente
    df_risultati = df_risultati.sort_values("Guadagno totale (€)", ascending=False).reset_index(drop=True)

    return df_risultati



def inventario_aggregato(df_prodotti, df_vendite):
    """
    Crea l'inventario reale:
    - Raggruppa per nome prodotto
    - Calcola costo medio pesato
    - Calcola quantità iniziale (totale acquistata)
    - Calcola quantità residua dopo le vendite
    - Calcola prezzo medio di vendita
    """

    if df_prodotti.empty:
        return pd.DataFrame(columns=[
            "Prodotto", "Quantità residua", "Quantità iniziale",
            "Costo medio (€)", "Prezzo medio vendita (€)", "Quantità venduta"
        ])

    df_prodotti = df_prodotti.copy()
    df_prodotti["Prezzo_unitario"] = df_prodotti["Prezzo_unitario"].apply(_clean_price)
    df_prodotti["Quantita"] = pd.to_numeric(df_prodotti["Quantita"], errors="coerce").fillna(0)

    # --- Calcolo costo medio pesato e quantità iniziale ---
    grouped = (
        df_prodotti
        .groupby("Nome")
        .apply(lambda x: pd.Series({
            "Quantità iniziale": x["Quantita"].sum(),
            "Costo medio (€)": (x["Prezzo_unitario"] * x["Quantita"]).sum() / x["Quantita"].sum()
            if x["Quantita"].sum() > 0 else 0
        }))
        .reset_index()
    )

    # --- Aggiungi dati dalle vendite ---
    if not df_vendite.empty:
        df_vendite = df_vendite.copy()
        df_vendite["Prezzo_totale_vendita"] = df_vendite["Prezzo_totale_vendita"].apply(_clean_price)
        df_vendite["Quantita"] = pd.to_numeric(df_vendite["Quantita"], errors="coerce").fillna(0)

        vendite_group = (
            df_vendite
            .groupby("Prodotto")
            .apply(lambda x: pd.Series({
                "Quantità venduta": x["Quantita"].sum(),
                "Prezzo medio vendita (€)": (
                    x["Prezzo_totale_vendita"].sum() / x["Quantita"].sum()
                    if x["Quantita"].sum() > 0 else 0
                )
            }))
            .reset_index()
        )

        grouped = pd.merge(
            grouped, vendite_group,
            left_on="Nome", right_on="Prodotto", how="left"
        ).drop(columns=["Prodotto"])
    else:
        grouped["Quantità venduta"] = 0
        grouped["Prezzo medio vendita (€)"] = 0.0

    grouped["Quantità venduta"] = grouped["Quantità venduta"].fillna(0)
    grouped["Prezzo medio vendita (€)"] = grouped["Prezzo medio vendita (€)"].fillna(0)

    # --- Calcolo quantità residua ---
    grouped["Quantità residua"] = (grouped["Quantità iniziale"] - grouped["Quantità venduta"]).clip(lower=0)

    # --- Arrotondamenti ---
    grouped["Costo medio (€)"] = grouped["Costo medio (€)"].round(2)
    grouped["Prezzo medio vendita (€)"] = grouped["Prezzo medio vendita (€)"].round(2)

    # --- Riordina colonne (Quantità residua prima) ---
    grouped = grouped[[
        "Nome",
        "Quantità residua",
        "Quantità iniziale",
        "Costo medio (€)",
        "Prezzo medio vendita (€)",
        "Quantità venduta"
    ]]

    grouped = grouped.rename(columns={"Nome": "Prodotto"})
    return grouped



def send_telegram_message(text):
    """Invia una notifica Telegram usando i secrets di Streamlit"""
    try:
        bot_token = st.secrets["telegram"]["bot_token"]
        chat_id = st.secrets["telegram"]["chat_id"]

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload_base = {"text": text, "parse_mode": "HTML"}

        for chat_id in chat_ids:
            payload = payload_base | {"chat_id": chat_id}
            response = requests.post(url, data=payload, timeout=10)
            if response.status_code != 200:
                print(f"⚠️ Errore Telegram ({chat_id}):", response.text)
            else:
                print(f"✅ Messaggio Telegram inviato a {chat_id}")
    except Exception as e:
        print("❌ Errore Telegram:", e)
        

