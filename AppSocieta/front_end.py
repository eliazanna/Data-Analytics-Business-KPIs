import streamlit as st
from app import prodotti_ws, vendite_ws
from data_utils import registra_vendita_multipla, analisi_vendite, get_data, add_row, calcola_bilancio, aggiorna_inventario
import pandas as pd
import streamlit_authenticator as stauth

st.set_page_config(
    page_title="Gestione Società - Elia & Tommy",
    page_icon="💼",
    layout="wide"   # <--- importantissimo
)

# --- CREDENZIALI ---
names = ["Elia Zanini", "Tommaso"]
usernames = ["elia", "tommy"]
passwords = [
    str(st.secrets.get("elia_password", "sonoilre")),
    str(st.secrets.get("tommy_password", "sonounservofedele"))
]

hashed_passwords = stauth.Hasher(passwords).generate()

credentials = {
    "usernames": {
        "elia": {"name": names[0], "password": hashed_passwords[0]},
        "tommy": {"name": names[1], "password": hashed_passwords[1]}
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
    st.title("💼 Gestione Società - Elia & Tommy")
    st.caption("Dashboard condivisa per gestire spese, vendite e saldi in tempo reale")


    # --- MENU LATERALE ---
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/2550/2550266.png", width=80)
    st.sidebar.markdown("## 💼 Gestione Società")

    menu = st.sidebar.selectbox(
        "Navigazione:",
        ["📦 Inventario", "🧾 Vendite", "💰 Bilancio", "📈 King della Vendita"]
    )


    # -------------------------------
    # 📦 TAB 1: INVENTARIO
    # -------------------------------
    from data_utils import inventario_aggregato

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
    # 💰 TAB 3: BILANCIO
    # -------------------------------
    elif menu=="💰 Bilancio":
        st.subheader("💰 Bilancio 50/50")

        prodotti_df = get_data(prodotti_ws)
        vendite_df = get_data(vendite_ws)
        b = calcola_bilancio(prodotti_df, vendite_df)

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

    # -------------------------------
    # 📈 TAB 4: KING DELLA VENDITA
    # -------------------------------


    elif menu == "📈 King della Vendita":
        st.subheader("📈 King della Vendita")

        prodotti_df = get_data(prodotti_ws)
        vendite_df = get_data(vendite_ws)

        if vendite_df.empty:
            st.info("Nessuna vendita registrata ancora.")
        else:
            analisi = analisi_vendite(prodotti_df, vendite_df)
            st.markdown("### 🧮 Confronto vendite tra Elia e Tommy")
            st.dataframe(analisi, use_container_width=True)

            # Evidenzia il vincitore
            king = analisi.loc[analisi["Plusvalenza media (%)"].idxmax(), "Venditore"]
            gain = analisi["Plusvalenza media (%)"].max()
            st.success(f"👑 King della vendita: **{king}** con una plusvalenza media del **{gain:.2f}%**")

