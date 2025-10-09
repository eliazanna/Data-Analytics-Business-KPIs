import streamlit as st
from app import prodotti_ws, vendite_ws
from data_utils import get_data, add_row, calcola_bilancio, aggiorna_inventario
import pandas as pd

# -------------------------------
# 🎨 CONFIGURAZIONE BASE
# -------------------------------
st.set_page_config(
    page_title="Gestione Società - Elia & Tommy",
    page_icon="💼",
    layout="wide"
)

st.title("💼 Gestione Società - Elia & Tommy")
st.caption("Dashboard condivisa per gestire spese, vendite e saldi in tempo reale")

tab1, tab2, tab3, tab4 = st.tabs(["📦 Inventario", "🧾 Vendite", "💰 Bilancio", "📈 King della Vendita"])

# -------------------------------
# 📦 TAB 1: INVENTARIO
# -------------------------------
from data_utils import inventario_aggregato

with tab1:
    st.write("Token trovato:", st.secrets["telegram"]["bot_token"][:10] + "...")
    st.write("Chat ID:", st.secrets["telegram"]["chat_id"])
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
        prezzo = st.text_input("Prezzo unitario (€)", placeholder="es. 4,50")
    with col3:
        quantita = st.number_input("Quantità", min_value=1, step=1)
    with col4:
        comprato_da = st.selectbox("Comprato da", ["Elia", "Tommy"])

    if st.button("Aggiungi prodotto", type="primary", use_container_width=True):
        if nome and prezzo:
            add_row(prodotti_ws, [nome, prezzo, quantita, comprato_da])
            st.success(f"✅ Prodotto **{nome}** aggiunto correttamente!")
            st.rerun()
        else:
            st.warning("⚠️ Inserisci almeno nome e prezzo.")

# -------------------------------
# 🧾 TAB 2: VENDITE
# -------------------------------
from data_utils import registra_vendita_multipla

with tab2:
    st.subheader("🧾 Registra vendita multipla")

    prodotti_df = get_data(prodotti_ws)
    nomi_prodotti = sorted(prodotti_df["Nome"].unique().tolist())

    # Selezione multipla
    prodotti_scelti = st.multiselect("Prodotti venduti", nomi_prodotti)
    venditore = st.selectbox("Venditore", ["Elia", "Tommy"])
    prezzo_totale = st.number_input("Prezzo totale vendita (€)", min_value=0.0, step=0.5)

    quantita_vendute = {}
    for p in prodotti_scelti:
        quantita_vendute[p] = st.number_input(f"Quantità per {p}", min_value=1, step=1, key=p)

    if st.button("Registra vendita multipla", type="primary"):
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
with tab3:
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
    st.metric("🎯 Mancano al pareggio", f"€ {b['pareggio']:.2f}")

# -------------------------------
# 📈 TAB 4: KING DELLA VENDITA
# -------------------------------
from data_utils import analisi_vendite

with tab4:
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

        # Mostra grafico comparativo
        st.markdown("### 📊 Grafico confronto plusvalenza")
        st.bar_chart(
            data=analisi.set_index("Venditore")[["Plusvalenza media (%)"]],
            use_container_width=True
        )
