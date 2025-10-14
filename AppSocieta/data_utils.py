import pandas as pd
import re
import requests
import streamlit as st  
from datetime import datetime 
# ---------------------------------------------------
# 🧹 Pulizia prezzi
# ---------------------------------------------------
def _clean_price(val):
    """Pulisce il valore di prezzo rimuovendo simboli, spazi e separatori migliaia/decimali in stile IT."""
    if pd.isna(val):
        return 0.0
    val = str(val).strip()

    # Rimuove simboli non numerici, tranne . , - 
    val = re.sub(r"[^\d,.\-]", "", val)

    # Caso comune: "1.500,00" → rimuove i punti come migliaia, poi sostituisce la virgola in punto
    if "," in val and "." in val:
        # Se c'è sia punto che virgola, il punto è separatore migliaia
        val = val.replace(".", "").replace(",", ".")
    elif "," in val and "." not in val:
        # Solo virgola → formato europeo (es. 10,5)
        val = val.replace(",", ".")
    elif "." in val and "," not in val:
        # Solo punto → formato inglese
        pass

    try:
        return float(val)
    except ValueError:
        return 0.0

def ensure_headers(ws, headers):
    """Se il worksheet è vuoto, scrive le intestazioni una volta sola."""
    try:
        vals = ws.get_all_values()
        if not vals:
            ws.append_row(headers)
    except Exception as e:
        print("Errore ensure_headers:", e)


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
def calcola_bilancio(df_prodotti, df_vendite, df_spese=None):
    """
    Bilancio 50/50 includendo spese extra (foglio 'Spese'):
    - Le spese extra si sommano alle spese prodotto del socio che le ha sostenute.
    - Il pareggio = (spese prodotti + spese extra) - entrate.
    """
    if df_prodotti.empty and (df_spese is None or df_spese.empty):
        return {
            "spesa_elia": 0.0, "spesa_tommy": 0.0,
            "spese_extra_elia": 0.0, "spese_extra_tommy": 0.0,
            "entrate_elia": 0.0, "entrate_tommy": 0.0,
            "totale_spese": 0.0, "totale_entrate": 0.0,
            "saldo_elia": 0.0, "saldo_tommy": 0.0, "pareggio": 0.0,
        }

    # --- Spese prodotti ---
    dfp = df_prodotti.copy()
    dfp["Prezzo_unitario"] = dfp["Prezzo_unitario"].apply(_clean_price)
    dfp["Quantita"] = pd.to_numeric(dfp["Quantita"], errors="coerce").fillna(0)
    dfp["Spesa_totale"] = (dfp["Prezzo_unitario"] * dfp["Quantita"]).round(2)
    spese_per_socio = dfp.groupby("Comprato_da")["Spesa_totale"].sum().to_dict()
    spesa_elia = round(spese_per_socio.get("Elia", 0.0), 2)
    spesa_tommy = round(spese_per_socio.get("Tommy", 0.0), 2)

    # --- Spese extra ---
    extra_elia = extra_tommy = 0.0
    if df_spese is not None and not df_spese.empty:
        dfs = df_spese.copy()
        dfs["Chi"] = dfs["Chi"].astype(str).str.strip().str.capitalize()
        dfs["Costo"] = dfs["Costo"].apply(_clean_price)
        extra = dfs.groupby("Chi")["Costo"].sum().to_dict()
        extra_elia = round(extra.get("Elia", 0.0), 2)
        extra_tommy = round(extra.get("Tommy", 0.0), 2)

    # --- Entrate ---
    entrate_elia = entrate_tommy = 0.0
    if df_vendite is not None and not df_vendite.empty:
        dfv = df_vendite.copy()
        if "Prezzo_totale_vendita" in dfv.columns:
            dfv["Prezzo_totale_vendita"] = dfv["Prezzo_totale_vendita"].apply(_clean_price)
        if "Venditore" not in dfv.columns:
            dfv["Venditore"] = "Elia"
        dfv["Venditore"] = dfv["Venditore"].astype(str).str.strip().str.capitalize()
        entrate_elia = round(dfv.loc[dfv["Venditore"] == "Elia", "Prezzo_totale_vendita"].sum(), 2)
        entrate_tommy = round(dfv.loc[dfv["Venditore"] == "Tommy", "Prezzo_totale_vendita"].sum(), 2)

    # --- Totali e saldi ---
    totale_spese = round(spesa_elia + spesa_tommy + extra_elia + extra_tommy, 2)
    totale_entrate = round(entrate_elia + entrate_tommy, 2)

    # differenze tra soci (spese - entrate, 50/50)
    diff_spese = (spesa_elia + extra_elia) - (spesa_tommy + extra_tommy)
    diff_entrate = entrate_elia - entrate_tommy
    saldo_elia = round((diff_spese / 2) - (diff_entrate / 2), 2)
    saldo_tommy = round(-saldo_elia, 2)
    pareggio = round(totale_spese - totale_entrate, 2)

    return {
        "spesa_elia": round(spesa_elia, 2),
        "spesa_tommy": round(spesa_tommy, 2),
        "spese_extra_elia": round(extra_elia, 2),
        "spese_extra_tommy": round(extra_tommy, 2),
        "entrate_elia": round(entrate_elia, 2),
        "entrate_tommy": round(entrate_tommy, 2),
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

        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")
        vendite_generate.append([
            nome,
            qta,
            round(quota_ricavo, 2),
            venditore,
            timestamp
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
def analisi_vendite(df_prodotti, df_vendite, df_spese=None):
    """
    Per venditore calcola:
    - Ordini registrati (multi-ordine = 1, via (Venditore, Timestamp) unici)
    - Ricavo totale
    - Costo totale (costo medio prodotti + spese extra del venditore)
    - Guadagno totale
    - Plusvalenza media (%) = Guadagno / (Costo prodotti + Spese extra)
    """
    import pandas as pd

    if df_vendite.empty or df_prodotti.empty:
        return pd.DataFrame(columns=[
            "Venditore", "Ordini registrati", "Ricavo totale (€)",
            "Costo totale (€)", "Guadagno totale (€)", "Plusvalenza media (%)", "Spese extra (€)"
        ])

    # --- Pulizia base ---
    dfp = df_prodotti.copy()
    if "Nome" in dfp.columns:
        dfp = dfp.rename(columns={"Nome": "Prodotto"})
    dfp["Prodotto"] = dfp["Prodotto"].astype(str).str.strip().str.lower()
    dfp["Prezzo_unitario"] = dfp["Prezzo_unitario"].apply(_clean_price)
    dfp["Quantita"] = pd.to_numeric(dfp["Quantita"], errors="coerce").fillna(0)

    dfv = df_vendite.copy()
    dfv["Prodotto"] = dfv["Prodotto"].astype(str).str.strip().str.lower()
    dfv["Venditore"] = dfv["Venditore"].astype(str).str.strip().str.capitalize()
    dfv["Prezzo_totale_vendita"] = dfv["Prezzo_totale_vendita"].apply(_clean_price)
    dfv["Quantita"] = pd.to_numeric(dfv["Quantita"], errors="coerce").fillna(0)
    dfv["Timestamp"] = dfv.get("Timestamp", "").astype(str).str.strip()

    # --- Costo medio pesato per prodotto ---
    costi = (
        dfp.groupby("Prodotto").apply(
            lambda x: (x["Prezzo_unitario"] * x["Quantita"]).sum() / x["Quantita"].sum()
            if x["Quantita"].sum() > 0 else 0.0
        ).reset_index(name="Costo_medio_unitario")
    )

    m = dfv.merge(costi, on="Prodotto", how="left")
    m["Costo_totale_prodotti"] = m["Costo_medio_unitario"].fillna(0) * m["Quantita"]

    # --- Totali per venditore (ricavi, costo prodotti) ---
    totali = (
        m.groupby("Venditore", as_index=False)
         .agg(Ricavo_totale=("Prezzo_totale_vendita", "sum"),
              Costo_prodotti=("Costo_totale_prodotti", "sum"))
    )

    # --- Ordini registrati: (Venditore, Timestamp) unici ---
    ordini = (
        dfv[["Venditore", "Timestamp"]].drop_duplicates()
           .groupby("Venditore", as_index=False).size()
           .rename(columns={"size": "Ordini registrati"})
    )

    risultati = totali.merge(ordini, on="Venditore", how="left").fillna({"Ordini registrati": 0})

    # --- Spese extra per venditore ---
    extra_map = {}
    if df_spese is not None and not df_spese.empty:
        dfs = df_spese.copy()
        dfs["Chi"] = dfs["Chi"].astype(str).str.strip().str.capitalize()
        dfs["Costo"] = dfs["Costo"].apply(_clean_price)
        extra_map = dfs.groupby("Chi")["Costo"].sum().to_dict()

    risultati["Spese extra (€)"] = risultati["Venditore"].map(extra_map).fillna(0.0)

    # --- Costo totale (prodotti + extra) e guadagno ---
    risultati["Costo totale (€)"] = risultati["Costo_prodotti"] + risultati["Spese extra (€)"]
    risultati["Ricavo totale (€)"] = risultati["Ricavo_totale"]
    risultati["Guadagno totale (€)"] = risultati["Ricavo totale (€)"] - risultati["Costo totale (€)"]

    risultati["Plusvalenza media (%)"] = risultati.apply(
        lambda r: (r["Guadagno totale (€)"] / r["Costo totale (€)"] * 100) if r["Costo totale (€)"] > 0 else 0.0,
        axis=1
    )

    risultati = risultati[[
        "Venditore", "Ordini registrati", "Ricavo totale (€)",
        "Costo totale (€)", "Spese extra (€)", "Guadagno totale (€)", "Plusvalenza media (%)"
    ]].round(2)

    risultati = risultati.sort_values("Guadagno totale (€)", ascending=False).reset_index(drop=True)

    # garantisci sempre Elia e Tommy
    for nome in ["Elia", "Tommy"]:
        if nome not in risultati["Venditore"].values:
            risultati.loc[len(risultati)] = {
                "Venditore": nome,
                "Ordini registrati": 0,
                "Ricavo totale (€)": 0.0,
                "Costo totale (€)": 0.0,
                "Spese extra (€)": 0.0,
                "Guadagno totale (€)": 0.0,
                "Plusvalenza media (%)": 0.0
            }

    return risultati




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
            "Costo medio unitario(€)", "Prezzo medio vendita (€)", "Quantità venduta"
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
            "Costo medio unitario(€)": (x["Prezzo_unitario"] * x["Quantita"]).sum() / x["Quantita"].sum()
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
    grouped["Costo medio unitario(€)"] = grouped["Costo medio unitario(€)"].round(2)
    grouped["Prezzo medio vendita (€)"] = grouped["Prezzo medio vendita (€)"].round(2)

    # --- Riordina colonne (Quantità residua prima) ---
    grouped = grouped[[
        "Nome",
        "Quantità residua",
        "Quantità iniziale",
        "Costo medio unitario(€)",
        "Prezzo medio vendita (€)",
        "Quantità venduta"
    ]]

    grouped = grouped.rename(columns={"Nome": "Prodotto"})
    return grouped



def send_telegram_message(text):
    """Invia una notifica Telegram a tutti gli utenti configurati"""
    try:
        bot_token = st.secrets["telegram"]["bot_token"]
        chat_ids = st.secrets["telegram"]["chat_ids"]
        print("🔍 Secrets letti:", bot_token[:10], chat_ids)

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload_base = {"text": text, "parse_mode": "HTML"}

        for chat_id in chat_ids:
            payload = payload_base | {"chat_id": chat_id}
            response = requests.post(url, data=payload, timeout=10)
            print(f"📤 Invio a {chat_id}: {response.status_code} - {response.text}")
            if response.status_code != 200:
                st.warning(f"⚠️ Telegram error ({chat_id}): {response.text}")
    except Exception as e:
        print("❌ Errore Telegram:", e)
        st.warning(f"Errore Telegram: {e}")
        

