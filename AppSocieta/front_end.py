import streamlit as st
from app import prodotti_ws, vendite_ws
from data_utils import _clean_price, registra_vendita_multipla,inventario_aggregato, analisi_vendite, get_data, add_row, calcola_bilancio, aggiorna_inventario
import pandas as pd
import streamlit_authenticator as stauth

st.set_page_config(
    page_title="Gestione Società - Elia & Tommy",
    page_icon="💼",
    layout="wide"   
)


# --- CREDENZIALI ---
names = ["Elia Zanini", "Tommaso"]
usernames = ["Elia", "Tommy"]
passwords = [
    str(st.secrets.get("elia_password", "sonoilre")),
    str(st.secrets.get("tommy_password", "sonounservofedele"))
]

hashed_passwords = stauth.Hasher(passwords).generate()

credentials = {
    "usernames": {
        "Elia": {"name": names[0], "password": hashed_passwords[0]},
        "Tommy": {"name": names[1], "password": hashed_passwords[1]}
    }
}

authenticator = stauth.Authenticate(
    credentials,
    "cookie_societa",
    "firma_cookie123",
    cookie_expiry_days=30
)

# --- LOGIN ---
name, authentication_status, username = authenticator.login("Login", "sidebar")
if authentication_status:
    # ✅ SOLO GLI UTENTI AUTENTICATI POSSONO VEDERE DA QUI IN POI
    st.sidebar.success(f"✅ Benvenuto {name}!")
    authenticator.logout("Logout", "main")

    # Tutta la tua app va qui ↓↓↓


    # -------------------------------
    # 📦 TAB 1: INVENTARIO
    # -------------------------------
       
    # --- SIDEBAR NAVIGAZIONE ---
    st.sidebar.markdown("## 💼 Gestione Società")

    # Menu statico in verticale
    menu = st.sidebar.radio(
        "Navigazione",
        ["📈 Dashboard Venditore","💰 Bilancio", "📦 Inventario", "🧾 Vendite"],
        index=0,   # pagina predefinita (Inventario)
        key="menu_choice"
    )



    if menu== "📦 Inventario":
        st.subheader("📦 Inventario reale aggregato")

        prodotti_df = get_data(prodotti_ws)
        vendite_df = get_data(vendite_ws)
        inventario_df = inventario_aggregato(prodotti_df, vendite_df)

        st.dataframe(inventario_df, use_container_width=True)
        st.caption("⚙️ Costo medio e prezzo medio calcolati automaticamente in base alle vendite e agli acquisti.")


        st.markdown("### ➕ Aggiungi nuovo prodotto")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            nome = st.text_input("Nome prodotto")
        with col2:
            prezzo_input = st.text_input("Prezzo unitario (€)", placeholder="es. 4,50")
        with col3:
            quantita = st.number_input("Quantità", min_value=1, step=1)
        with col4:
            comprato_da = st.selectbox("Comprato da", ["Elia", "Tommy"])

        if st.button("Aggiungi prodotto", type="primary", use_container_width=True):
            if nome and prezzo_input:
                try:
                    # 🔹 Normalizza il prezzo (converte "4,5" -> 4.5)
                    prezzo_norm = prezzo_input.replace(",", ".").strip()
                    prezzo_float = float(prezzo_norm)
                    prezzo_format = f"€ {prezzo_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    # 👆 converte in formato europeo (4.5 -> "€ 4,50")

                    # Aggiungi la riga a Google Sheets
                    from datetime import datetime

                    # Aggiungi la data/ora locale formattata
                    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")
                    add_row(vendite_ws, [vendita_nome, vendita_qta, prezzo_vendita, venditore, timestamp])


                    st.success(f"✅ Prodotto **{nome}** aggiunto correttamente con prezzo {prezzo_format}!")
                    st.rerun()
                except ValueError:
                    st.warning("⚠️ Inserisci un numero valido per il prezzo (es. 4,50 o 10,00).")
       

    # -------------------------------
    # 🧾 TAB 2: VENDITE
    # -------------------------------
    
    elif menu == "🧾 Vendite":
        st.subheader("🧾 Registra nuovo ordine")

        prodotti_df = get_data(prodotti_ws)
        nomi_prodotti = sorted(prodotti_df["Nome"].unique().tolist())

        # Selezione multipla
        prodotti_scelti = st.multiselect("Prodotti venduti", nomi_prodotti)
        venditore = st.selectbox("Venditore", ["Elia", "Tommy"])
        prezzo_totale = st.number_input("Prezzo totale vendita (€)", min_value=0.0, step=0.5)

        quantita_vendute = {}
        for p in prodotti_scelti:
            quantita_vendute[p] = st.number_input(f"Quantità per {p}", min_value=1, step=1, key=p)

        if st.button("Registra", type="primary"):
            if prodotti_scelti and prezzo_totale > 0:
                vendite_generate, inventario_aggiornato = registra_vendita_multipla(
                    prodotti_df, quantita_vendute, prezzo_totale, venditore
                )
                
            
                for v in vendite_generate:
                    add_row(vendite_ws, v)

                # 🔔 Invia notifica Telegram
                from data_utils import registra_vendita_multipla, send_telegram_message
                prodotti_str = ", ".join(prodotti_scelti)
                msg = (
                    f"💸 <b>Nuova vendita registrata!</b>\n"
                    f"👤 Venditore: {venditore}\n"
                    f"🛍️ Prodotti: {prodotti_str}\n"
                    f"💶 Totale: € {prezzo_totale:.2f}"
                )
                send_telegram_message(msg)


                
                st.success(f"✅ Vendita registrata ({len(vendite_generate)} prodotti)")
                st.rerun()
            else:
                st.warning("⚠️ Seleziona almeno un prodotto e inserisci un prezzo totale.")
        
        # -------------------------------
        # 📜 Storico ordini (raggruppati)
        # -------------------------------
        st.markdown("---")
        st.markdown("### 📜 Ordini precedenti")

        vendite_storico = get_data(vendite_ws)

        if vendite_storico.empty:
            st.info("Nessun ordine registrato.")
        else:
            # Pulizia base
            vendite_storico = vendite_storico.copy()
            vendite_storico["Venditore"] = (
                vendite_storico["Venditore"].astype(str).str.strip().str.capitalize()
            )
            vendite_storico["Timestamp"] = vendite_storico.get("Timestamp", "").astype(str).str.strip()
            vendite_storico["Prezzo_totale_vendita"] = vendite_storico["Prezzo_totale_vendita"].apply(_clean_price)
            vendite_storico["Quantita"] = pd.to_numeric(vendite_storico["Quantita"], errors="coerce").fillna(0).astype(int)

            # Raggruppa per ordine: (Venditore, Timestamp)
            ordini = (
                vendite_storico
                .groupby(["Venditore", "Timestamp"], as_index=False)
                .agg(
                    Articoli=("Prodotto", "count"),             # quante righe/prodotti ha l'ordine
                    Pezzi=("Quantita", "sum"),                  # somma quantità
                    Totale=("Prezzo_totale_vendita", "sum")     # somma quote ricavo = totale ordine
                )
            )

            # Ordina per data (più recente in alto) e numerazione Ordine #1, #2, ...
            ordini["_ts"] = pd.to_datetime(ordini["Timestamp"], format="%d/%m/%Y %H:%M", errors="coerce")
            ordini = ordini.sort_values("_ts", ascending=False).reset_index(drop=True)
            ordini.insert(0, "Ordine #", ordini.index + 1)
            ordini["Ordine #"] = ordini["Ordine #"].apply(lambda i: f"Ordine #{i}")
            ordini["Totale (€)"] = ordini["Totale"].round(2)

            # Se vuoi mostrare solo le info principali richieste:
            cols = ["Ordine #", "Venditore", "Timestamp", "Totale (€)"]
            st.dataframe(ordini[cols], use_container_width=True)

            # (Opzionale) Expanders con il dettaglio dei prodotti per ogni ordine
            with st.expander("Mostra dettaglio prodotti per ogni ordine"):
                for _, row in ordini.iterrows():
                    mask = (vendite_storico["Venditore"] == row["Venditore"]) & (vendite_storico["Timestamp"] == row["Timestamp"])
                    dettaglio = vendite_storico.loc[mask, ["Prodotto", "Quantita", "Prezzo_totale_vendita"]].copy()
                    dettaglio["Prezzo_totale_vendita"] = dettaglio["Prezzo_totale_vendita"].round(2)
                    st.write(f"**{row['Ordine #']}** – {row['Venditore']} – {row['Timestamp']} – Totale: € {row['Totale (€)']:.2f}")
                    st.dataframe(dettaglio.rename(columns={"Prezzo_totale_vendita": "Quota ricavo (€)"}), use_container_width=True)


    # -------------------------------
    # 💰 TAB 3: BILANCIO
    # -------------------------------
    elif menu=="💰 Bilancio":
        st.subheader("💰 Bilancio")

        prodotti_df = get_data(prodotti_ws)
        vendite_df = get_data(vendite_ws)
        b = calcola_bilancio(prodotti_df, vendite_df)

                # Countdown al pareggio
        st.divider()

        # --- BILANCIO GLOBALE E AVANZAMENTO ---
        totale_spese = b["totale_spese"]
        totale_entrate = b["totale_entrate"]
        pareggio = b["pareggio"]
        guadagno_netto = totale_entrate - totale_spese

        if totale_spese > 0:
            progresso = min(totale_entrate / totale_spese, 1.0)
        else:
            progresso = 0

        # inizializza flag per palloncini
        if "pareggio_festeggiato" not in st.session_state:
            st.session_state.pareggio_festeggiato = False

        # --- Sezione dinamica ---
        if totale_entrate < totale_spese:
            st.markdown("### 🎯 Mancano al pareggio")
            st.metric("Importo mancante", f"€ {pareggio:.2f}")
            st.progress(progresso)
            st.markdown(f"**Avanzamento:** {progresso*100:.1f}% delle spese coperte")

            # resetta il flag se torni sotto il pareggio
            st.session_state.pareggio_festeggiato = False

        elif abs(totale_entrate - totale_spese) < 1:
            st.markdown("### ✅ Pareggio raggiunto!")
            st.progress(1.0)
            st.session_state.pareggio_festeggiato = False

        else:
            # PROFITTO 🤑
            st.markdown("""
                <div style="
                    background-color: #E8F5E9;
                    padding: 1rem;
                    border-radius: 10px;
                    border: 1px solid #C8E6C9;
                    text-align: center;">
                    <h3 style="color:#1B5E20;">💰 Guadagno netto</h3>
                </div>
            """, unsafe_allow_html=True)
            
            st.metric("Profitto totale", f"€ {guadagno_netto:.2f}")
            st.progress(1.0)
            st.markdown("Hai superato il pareggio e stai generando **profitto netto!** 🥳")

            # 🎈 Mostra i palloncini solo la prima volta che superi il pareggio
            if not st.session_state.pareggio_festeggiato:
                st.balloons()
                st.session_state.pareggio_festeggiato = True

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Spese Elia", f"€ {b['spesa_elia']:.2f}")
            st.metric("Entrate Elia", f"€ {b['entrate_elia']:.2f}")
        with col2:
            st.metric("Spese Tommy", f"€ {b['spesa_tommy']:.2f}")
            st.metric("Entrate Tommy", f"€ {b['entrate_tommy']:.2f}")

        st.divider()
        col3, col4 = st.columns(2)
        with col3:
            st.metric("Totale Spese", f"€ {b['totale_spese']:.2f}")
        with col4:
            st.metric("Totale Entrate", f"€ {b['totale_entrate']:.2f}")

        st.divider()

        # Mostra chi deve a chi
        saldo_elia = b["saldo_elia"]
        saldo_tommy = b["saldo_tommy"]

        if saldo_elia > 0:
            st.success(f"💸 Tommy deve a Elia: **€ {saldo_elia:.2f}**")
        elif saldo_elia < 0:
            st.error(f"💸 Elia deve a Tommy: **€ {abs(saldo_elia):.2f}**")
        else:
            st.info("✅ I conti sono perfettamente in pari!")

        st.caption(f"Saldo Elia: € {saldo_elia:.2f}  |  Saldo Tommy: € {saldo_tommy:.2f}")



    # -------------------------------
    # 📈 TAB 4: KING DELLA VENDITA
    # -------------------------------
    elif menu == "📈 Dashboard Venditore":
        import plotly.graph_objects as go
        from datetime import datetime, timedelta
        import pytz

        prodotti_df = get_data(prodotti_ws)
        vendite_df_all = get_data(vendite_ws)

        # Filtra le vendite dell' utente loggato

        current_user = username.lower().strip()
        vendite_df_all["Venditore"] = vendite_df_all["Venditore"].astype(str).str.strip().str.lower()
        vendite_df = vendite_df_all[vendite_df_all["Venditore"] == current_user]

        st.markdown("## 📊 Dashboard venditore")
        st.caption("🎯 Obiettivi personali di vendita – monitoraggio giornaliero e settimanale")



        if "Timestamp" in vendite_df.columns:
            # Rimuove spazi e converte tutto in datetime (senza crash)
            vendite_df["Timestamp"] = (
                pd.to_datetime(vendite_df["Timestamp"].astype(str).str.strip(), 
                            format="%d/%m/%Y %H:%M", 
                            errors="coerce")
            )

            # Applica .dt solo se la conversione ha funzionato
            if pd.api.types.is_datetime64_any_dtype(vendite_df["Timestamp"]):
                vendite_df["Timestamp"] = vendite_df["Timestamp"].dt.tz_localize(None)
            else:
                st.warning("⚠️ I timestamp non sono stati riconosciuti come datetime.")
                st.write(vendite_df["Timestamp"].head())
        else:
            vendite_df["Timestamp"] = pd.NaT

        italy_tz = pytz.timezone("Europe/Rome")
        oggi = datetime.now(italy_tz).date()
        settimana_inizio = oggi - timedelta(days=6)
        oggi_dt = pd.to_datetime(oggi)
        settimana_inizio_dt = pd.to_datetime(settimana_inizio)



        vendite_df["Prezzo_totale_vendita"] = vendite_df["Prezzo_totale_vendita"].apply(_clean_price)
        
        vendite_giornaliere = vendite_df[vendite_df["Timestamp"].dt.normalize() == oggi_dt]
        vendite_settimanali = vendite_df[
            (vendite_df["Timestamp"].dt.normalize() >= settimana_inizio_dt)
            & (vendite_df["Timestamp"].dt.normalize() <= oggi_dt)
        ]

        totale_giorno = vendite_giornaliere["Prezzo_totale_vendita"].sum()
        totale_settimana = vendite_settimanali["Prezzo_totale_vendita"].sum()

        # --- Obiettivi ---
        obiettivo_giorno = 35.0
        obiettivo_settimana = obiettivo_giorno * 7
        progresso_giorno = min(totale_giorno / obiettivo_giorno, 1)
        progresso_settimana = min(totale_settimana / obiettivo_settimana, 1)

        # --- GRAFICI ---
        col1, col2 = st.columns(2)
        with col1:
            fig_giorno = go.Figure(go.Pie(
                values=[progresso_giorno, 1 - progresso_giorno],
                hole=0.6, marker_colors=["#00B894", "#E0E0E0"], textinfo="none"))
            fig_giorno.update_layout(title=f"🕒 Oggi ({oggi.strftime('%d/%m/%Y')})",
                                    annotations=[dict(text=f"{progresso_giorno*100:.0f}%", x=0.5, y=0.5, font_size=22, showarrow=False)],
                                    showlegend=False, height=400)
            st.plotly_chart(fig_giorno, use_container_width=True)
        with col2:
            fig_settimana = go.Figure(go.Pie(
                values=[progresso_settimana, 1 - progresso_settimana],
                hole=0.6, marker_colors=["#007A87", "#E0E0E0"], textinfo="none"))
            fig_settimana.update_layout(title="📅 Ultimi 7 giorni",
                                        annotations=[dict(text=f"{progresso_settimana*100:.0f}%", x=0.5, y=0.5, font_size=22, showarrow=False)],
                                        showlegend=False, height=400)
            st.plotly_chart(fig_settimana, use_container_width=True)

        # --- INFO ---
        st.markdown("---")
        st.markdown(f"**Totale vendite oggi:** € {totale_giorno:.2f} / € {obiettivo_giorno:.2f}")
        st.markdown(f"**Totale vendite settimana:** € {totale_settimana:.2f} / € {obiettivo_settimana:.2f}")

        if progresso_giorno >= 1 and progresso_settimana < 1:
            st.success("🔥 Hai raggiunto l'obiettivo giornaliero, continua così per la settimana!")
        elif progresso_settimana >= 1:
            st.balloons()
            st.success("🏆 Complimenti! Hai raggiunto l'obiettivo settimanale!")

        # --- SEZIONE ANALISI COMPLETA ---
        st.markdown("---")
        st.markdown("### 🧮 Confronto vendite tra Elia e Tommy")

        # Normalizza la colonna "Venditore" in minuscolo per coerenza
        vendite_df_all["Venditore"] = vendite_df_all["Venditore"].astype(str).str.strip().str.lower()

        analisi = analisi_vendite(prodotti_df, vendite_df_all)
        
        if analisi.empty:
            st.info("📊 Nessuna vendita registrata al momento.")
        else:
            # Mostra tabella formattata
            st.dataframe(
                analisi.style.format({
                    "Ricavo totale (€)": "€ {:.2f}",
                    "Costo totale (€)": "€ {:.2f}",
                    "Guadagno totale (€)": "€ {:.2f}",
                    "Plusvalenza media (%)": "{:.1f}%"
                }),
                use_container_width=True
            )
        

            # Identifica il "King della vendita"
            king_row = analisi.loc[analisi["Plusvalenza media (%)"].idxmax()]
            king = str(king_row["Venditore"]).capitalize()  # ✅ rende la prima lettera maiuscola
            gain = king_row["Plusvalenza media (%)"]

            st.success(f"👑 King della vendita: **{king}** con una plusvalenza media del **{gain:.2f}%**")
