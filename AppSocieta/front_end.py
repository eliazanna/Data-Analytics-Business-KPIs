import streamlit as st
from app import prodotti_ws, vendite_ws, spese_ws
from data_utils import _clean_price, registra_vendita_multipla, inventario_aggregato, analisi_vendite, get_data, add_row, calcola_bilancio, aggiorna_inventario, ensure_headers
import pandas as pd
import plotly.graph_objects as go
import streamlit_authenticator as stauth
from datetime import datetime, timedelta, date as date_type
from zoneinfo import ZoneInfo

st.set_page_config(
    page_title="Gestione Società — Elia & Tommy",
    page_icon="💼",
    layout="wide"
)

st.markdown("""
<style>
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    }
    [data-testid="stSidebar"] * { color: #e0e0e0 !important; }

    .kpi-card {
        background: linear-gradient(135deg, #1e3a5f 0%, #0d2137 100%);
        border: 1px solid #2e5090;
        border-radius: 10px;
        padding: 1.1rem 1.4rem;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .kpi-label { font-size: 0.78rem; color: #8aa8c8; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.06em; }
    .kpi-value { font-size: 1.8rem; font-weight: 700; color: #fff; }
    .kpi-delta-pos  { font-size: 0.82rem; color: #52c97a; }
    .kpi-delta-neg  { font-size: 0.82rem; color: #e05c5c; }
    .kpi-delta-neutral { font-size: 0.82rem; color: #8aa8c8; }

    .section-title {
        font-size: 1rem;
        font-weight: 600;
        color: #6ab0f5;
        margin: 1.4rem 0 0.7rem 0;
        padding-bottom: 5px;
        border-bottom: 1px solid #1e3a5f;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .alert-low-stock {
        background: #2e1a1a;
        border-left: 3px solid #e05c5c;
        padding: 0.5rem 1rem;
        border-radius: 0 6px 6px 0;
        margin: 3px 0;
        color: #f5c6c6;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)

# --- AUTH ---
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
authenticator = stauth.Authenticate(credentials, "cookie_societa", "firma_cookie123", cookie_expiry_days=30)
name, authentication_status, username = authenticator.login("Login", "sidebar")

if authentication_status:
    st.sidebar.success(f"Benvenuto, {name}")
    authenticator.logout("Esci", "main")

    st.sidebar.markdown("## Gestione Società")
    menu = st.sidebar.radio(
        "Navigazione",
        ["Dashboard", "Bilancio", "Vendite", "Inventario"],
        index=0,
        key="menu_choice"
    )

    italy_tz = ZoneInfo("Europe/Rome")
    oggi = datetime.now(italy_tz).date()

    CHART_LAYOUT = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#ccc"),
    )

    # ──────────────────────────────────────────────────────────────────────────
    # DASHBOARD
    # ──────────────────────────────────────────────────────────────────────────
    if menu == "Dashboard":
        prodotti_df   = get_data(prodotti_ws)
        vendite_df_all = get_data(vendite_ws)
        spese_df_all  = get_data(spese_ws)

        st.markdown("## Dashboard")
        st.caption("Riepilogo della stagione Halloween 2025 — dati da Google Sheets")

        if not vendite_df_all.empty:
            vendite_df_all["Venditore"] = vendite_df_all["Venditore"].astype(str).str.strip().str.capitalize()
            vendite_df_all["Prezzo_totale_vendita"] = vendite_df_all["Prezzo_totale_vendita"].apply(_clean_price)
            vendite_df_all["Quantita"] = pd.to_numeric(vendite_df_all["Quantita"], errors="coerce").fillna(0)
            vendite_df_all["_ts"] = pd.to_datetime(
                vendite_df_all["Timestamp"].astype(str).str.strip(),
                format="%d/%m/%Y %H:%M", errors="coerce"
            )
            vendite_df_all["_date"] = vendite_df_all["_ts"].dt.date

        ieri              = oggi - timedelta(days=1)
        settimana_start   = oggi - timedelta(days=6)
        settimana_prec_s  = oggi - timedelta(days=13)
        settimana_prec_e  = oggi - timedelta(days=7)

        def ricavo_periodo(df, start, end):
            if df.empty or "_date" not in df.columns:
                return 0.0
            mask = (df["_date"] >= start) & (df["_date"] <= end)
            return float(df.loc[mask, "Prezzo_totale_vendita"].sum())

        def ordini_periodo(df, start, end):
            if df.empty or "_date" not in df.columns:
                return 0
            mask = (df["_date"] >= start) & (df["_date"] <= end)
            return df.loc[mask, ["Venditore", "Timestamp"]].drop_duplicates().shape[0]

        vdf = vendite_df_all if not vendite_df_all.empty else pd.DataFrame()
        tot_oggi      = ricavo_periodo(vdf, oggi, oggi)
        tot_ieri      = ricavo_periodo(vdf, ieri, ieri)
        tot_sett      = ricavo_periodo(vdf, settimana_start, oggi)
        tot_sett_prec = ricavo_periodo(vdf, settimana_prec_s, settimana_prec_e)
        ordini_oggi   = ordini_periodo(vdf, oggi, oggi)
        tot_stagione  = float(vendite_df_all["Prezzo_totale_vendita"].sum()) if not vendite_df_all.empty else 0.0

        analisi = analisi_vendite(prodotti_df, vendite_df_all, spese_df_all)
        margine_medio = float(analisi["Plusvalenza media (%)"].mean()) if not analisi.empty else 0.0

        def delta_html(curr, prev):
            if prev == 0:
                return '<span class="kpi-delta-neutral">— n/d</span>'
            diff = curr - prev
            pct  = (diff / abs(prev)) * 100
            icon = "▲" if diff >= 0 else "▼"
            cls  = "kpi-delta-pos" if diff >= 0 else "kpi-delta-neg"
            return f'<span class="{cls}">{icon} {abs(pct):.1f}%</span>'

        # KPI row
        c1, c2, c3, c4 = st.columns(4)
        for col, label, value, delta in [
            (c1, "Ricavi oggi",      f"€ {tot_oggi:.2f}",     delta_html(tot_oggi, tot_ieri)),
            (c2, "Ricavi settimana", f"€ {tot_sett:.2f}",     delta_html(tot_sett, tot_sett_prec)),
            (c3, "Ordini oggi",      str(ordini_oggi),         '<span class="kpi-delta-neutral">ordini</span>'),
            (c4, "Margine medio",    f"{margine_medio:.1f}%",  '<span class="kpi-delta-neutral">plusvalenza</span>'),
        ]:
            with col:
                st.markdown(f"""
                <div class="kpi-card">
                    <div class="kpi-label">{label}</div>
                    <div class="kpi-value">{value}</div>
                    {delta}
                </div>""", unsafe_allow_html=True)

        # Grafico stagione
        st.markdown('<div class="section-title">Vendite stagione Halloween 2025 — Elia vs Tommy</div>', unsafe_allow_html=True)

        if not vendite_df_all.empty and "_date" in vendite_df_all.columns:
            fine_stagione = date_type(2025, 10, 31)
            stagione_df = vendite_df_all[vendite_df_all["_date"] <= fine_stagione].copy()

            if stagione_df.empty:
                st.info("Nessuna vendita nella stagione 2025.")
            else:
                inizio_stagione = stagione_df["_date"].min()
                date_range = pd.date_range(start=pd.Timestamp(inizio_stagione), end=pd.Timestamp(fine_stagione), freq="D")

                # Raggruppa per data e venditore, poi pivot
                pivot = (
                    stagione_df
                    .groupby(["_date", "Venditore"])["Prezzo_totale_vendita"]
                    .sum()
                    .unstack(fill_value=0)
                    .reindex(date_range, fill_value=0)
                )
                pivot.index.name = "_date"

                fig_stagione = go.Figure()
                color_map = {"Elia": "#e63946", "Tommy": "#4895ef"}
                fill_map  = {"Elia": "rgba(230,57,70,0.1)", "Tommy": "rgba(72,149,239,0.1)"}

                for venditore in ["Elia", "Tommy"]:
                    y_vals = pivot[venditore].values if venditore in pivot.columns else [0] * len(date_range)
                    fig_stagione.add_trace(go.Scatter(
                        x=date_range,
                        y=y_vals,
                        mode="lines+markers",
                        name=venditore,
                        line=dict(color=color_map[venditore], width=2.5),
                        marker=dict(size=5, color=color_map[venditore]),
                        fill="tozeroy",
                        fillcolor=fill_map[venditore],
                        hovertemplate=f"<b>{venditore}</b><br>%{{x|%d %b}}<br>€ %{{y:.2f}}<extra></extra>"
                    ))

                fig_stagione.update_layout(
                    **CHART_LAYOUT,
                    height=310,
                    legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1, font=dict(color="#ccc")),
                    xaxis=dict(gridcolor="#243550", tickformat="%d %b", tickfont=dict(color="#aaa")),
                    yaxis=dict(gridcolor="#243550", tickprefix="€ ", tickfont=dict(color="#aaa")),
                    hovermode="x unified",
                )
                st.plotly_chart(fig_stagione, use_container_width=True)
        else:
            st.info("Nessun dato disponibile.")

        col_left, col_right = st.columns(2)

        # Top prodotti
        with col_left:
            st.markdown('<div class="section-title">Top prodotti per ricavo</div>', unsafe_allow_html=True)
            if not vendite_df_all.empty:
                top_prod = (
                    vendite_df_all.groupby("Prodotto", as_index=False)["Prezzo_totale_vendita"].sum()
                    .sort_values("Prezzo_totale_vendita", ascending=True)
                    .tail(8)
                )
                fig_top = go.Figure(go.Bar(
                    x=top_prod["Prezzo_totale_vendita"],
                    y=top_prod["Prodotto"],
                    orientation="h",
                    marker=dict(color=top_prod["Prezzo_totale_vendita"],
                                colorscale=[[0, "#2a4a70"], [1, "#6ab0f5"]], showscale=False),
                    text=[f"€ {v:.2f}" for v in top_prod["Prezzo_totale_vendita"]],
                    textposition="outside",
                    textfont=dict(color="#bbb", size=11)
                ))
                fig_top.update_layout(
                    **CHART_LAYOUT, height=300,
                    margin=dict(l=0, r=65, t=20, b=0),
                    xaxis=dict(showgrid=False, showticklabels=False),
                    yaxis=dict(gridcolor="#243550", tickfont=dict(color="#aaa")),
                )
                st.plotly_chart(fig_top, use_container_width=True)

        # Elia vs Tommy
        with col_right:
            st.markdown('<div class="section-title">Elia vs Tommy — confronto</div>', unsafe_allow_html=True)
            if not analisi.empty:
                metriche = ["Ricavo totale (€)", "Costo totale (€)", "Guadagno totale (€)"]
                fig_vs = go.Figure()
                palette = ["#e63946", "#4895ef"]
                for i, row in analisi.iterrows():
                    fig_vs.add_trace(go.Bar(
                        name=str(row["Venditore"]),
                        x=metriche,
                        y=[row[m] for m in metriche],
                        marker_color=palette[i % len(palette)],
                        text=[f"€ {row[m]:.0f}" for m in metriche],
                        textposition="outside",
                        textfont=dict(color="#bbb", size=10)
                    ))
                fig_vs.update_layout(
                    **CHART_LAYOUT,
                    barmode="group", height=300,
                    legend=dict(orientation="h", yanchor="bottom", y=1.01, font=dict(color="#ccc")),
                    yaxis=dict(gridcolor="#243550", tickprefix="€ ", tickfont=dict(color="#aaa")),
                )
                st.plotly_chart(fig_vs, use_container_width=True)

                king_row = analisi.loc[analisi["Plusvalenza media (%)"].idxmax()]
                king = str(king_row["Venditore"]).capitalize()
                gain = king_row["Plusvalenza media (%)"]
                st.success(f"**{king}** — plusvalenza media stagione: **{gain:.2f}%**")

        # Obiettivi personali (stagionali)
        st.markdown('<div class="section-title">Obiettivi personali — stagione</div>', unsafe_allow_html=True)
        current_user = username.lower().strip()
        fine_stagione = date_type(2025, 10, 31)

        if not vendite_df_all.empty:
            mie_vendite  = vendite_df_all[vendite_df_all["Venditore"].str.lower() == current_user].copy()
            mie_stagione = mie_vendite[mie_vendite["_date"] <= fine_stagione]
            tot_mio_sett = ricavo_periodo(mie_vendite, oggi - timedelta(days=6), oggi)
            tot_mio_stag = float(mie_stagione["Prezzo_totale_vendita"].sum())
        else:
            tot_mio_sett = tot_mio_stag = 0.0

        obiettivo_s    = 420   # 60/giorno x 7
        obiettivo_stag = 1800  # stagionale
        prog_s    = min(tot_mio_sett  / obiettivo_s,    1.0)
        prog_stag = min(tot_mio_stag  / obiettivo_stag, 1.0)

        og1, og2 = st.columns(2)
        for col, title, valore, obiettivo, prog in [
            (og1, "Ricavi settimana",  tot_mio_sett,  obiettivo_s,    prog_s),
            (og2, "Ricavi stagione",   tot_mio_stag,  obiettivo_stag, prog_stag),
        ]:
            with col:
                color_arc = "#52c97a" if prog >= 1 else "#4895ef"
                fig = go.Figure(go.Pie(
                    values=[prog, 1 - prog], hole=0.65,
                    marker_colors=[color_arc, "#1a2a3a"], textinfo="none"
                ))
                fig.update_layout(
                    title=dict(text=title, font=dict(color="#bbb", size=13)),
                    annotations=[dict(
                        text=f"€{valore:.0f}<br><span style='font-size:11px;color:#888'>/ €{obiettivo}</span>",
                        x=0.5, y=0.5, font_size=17, showarrow=False, font_color="#fff"
                    )],
                    showlegend=False, height=260,
                    paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=50, b=0, l=0, r=0)
                )
                st.plotly_chart(fig, use_container_width=True)

        if prog_stag >= 1:
            st.success("Obiettivo stagionale raggiunto!")
        elif prog_s >= 1:
            st.success("Obiettivo settimanale raggiunto!")

    # ──────────────────────────────────────────────────────────────────────────
    # BILANCIO
    # ──────────────────────────────────────────────────────────────────────────
    elif menu == "Bilancio":
        st.markdown("## Bilancio")

        ensure_headers(spese_ws, ["Descrizione", "Costo", "Chi", "Timestamp"])
        prodotti_df = get_data(prodotti_ws)
        vendite_df  = get_data(vendite_ws)
        spese_df    = get_data(spese_ws)
        b = calcola_bilancio(prodotti_df, vendite_df, spese_df)

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Spese prodotti — Elia",  f"€ {b['spesa_elia']:.2f}")
            st.metric("Spese extra — Elia",     f"€ {b['spese_extra_elia']:.2f}")
            st.metric("Entrate Elia",           f"€ {b['entrate_elia']:.2f}")
        with col2:
            st.metric("Spese prodotti — Tommy", f"€ {b['spesa_tommy']:.2f}")
            st.metric("Spese extra — Tommy",    f"€ {b['spese_extra_tommy']:.2f}")
            st.metric("Entrate Tommy",          f"€ {b['entrate_tommy']:.2f}")

        # Grouped bar: spese / entrate / risultato per socio
        st.markdown('<div class="section-title">Riepilogo economico per socio</div>', unsafe_allow_html=True)
        metriche_bil = ["Spese totali (€)", "Entrate (€)", "Guadagno (€)"]
        dati_bil = {
            "Elia":  [
                round(b["spesa_elia"]  + b["spese_extra_elia"],  2),
                round(b["entrate_elia"],  2),
                round(b["entrate_elia"]  - b["spesa_elia"]  - b["spese_extra_elia"],  2),
            ],
            "Tommy": [
                round(b["spesa_tommy"] + b["spese_extra_tommy"], 2),
                round(b["entrate_tommy"], 2),
                round(b["entrate_tommy"] - b["spesa_tommy"] - b["spese_extra_tommy"], 2),
            ],
        }
        fig_bil = go.Figure()
        for persona, vals in dati_bil.items():
            color = "#e63946" if persona == "Elia" else "#4895ef"
            fig_bil.add_trace(go.Bar(
                name=persona, x=metriche_bil, y=vals,
                marker_color=color,
                text=[f"€ {v:.0f}" for v in vals],
                textposition="outside",
                textfont=dict(color="#bbb", size=11)
            ))
        fig_bil.update_layout(
            **CHART_LAYOUT, barmode="group", height=320,
            legend=dict(orientation="h", yanchor="bottom", y=1.01, font=dict(color="#ccc")),
            yaxis=dict(gridcolor="#243550", tickprefix="€ ", tickfont=dict(color="#aaa")),
        )
        st.plotly_chart(fig_bil, use_container_width=True)

        st.divider()
        col3, col4 = st.columns(2)
        with col3:
            st.metric("Totale spese", f"€ {b['totale_spese']:.2f}")
        with col4:
            st.metric("Totale entrate", f"€ {b['totale_entrate']:.2f}")

        saldo_elia = b["saldo_elia"]
        st.divider()
        if saldo_elia > 0:
            st.success(f"Tommy deve a Elia: **€ {saldo_elia:.2f}**")
        elif saldo_elia < 0:
            st.error(f"Elia deve a Tommy: **€ {abs(saldo_elia):.2f}**")
        else:
            st.info("I conti sono in pari.")
        st.caption(f"Saldo Elia: € {saldo_elia:.2f}  |  Saldo Tommy: € {b['saldo_tommy']:.2f}")

        totale_spese   = b["totale_spese"]
        totale_entrate = b["totale_entrate"]
        pareggio       = b["pareggio"]
        guadagno_netto = totale_entrate - totale_spese
        progresso      = min((totale_entrate / totale_spese) if totale_spese > 0 else 0, 1.0)

        st.divider()
        if not "pareggio_festeggiato" in st.session_state:
            st.session_state.pareggio_festeggiato = False

        if totale_entrate < totale_spese:
            st.markdown("### Mancano al pareggio")
            st.metric("Importo mancante", f"€ {pareggio:.2f}")
            st.progress(progresso)
            st.caption(f"Avanzamento: {progresso*100:.1f}% delle spese coperte")
            st.session_state.pareggio_festeggiato = False
        elif abs(totale_entrate - totale_spese) < 1:
            st.markdown("### Pareggio raggiunto")
            st.progress(1.0)
        else:
            st.markdown("### Guadagno netto")
            st.metric("Profitto totale", f"€ {guadagno_netto:.2f}")
            st.progress(1.0)
            if not st.session_state.pareggio_festeggiato:
                st.session_state.pareggio_festeggiato = True

        st.markdown("---")
        st.markdown("### Inserisci spesa extra")
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            descr = st.text_input("Descrizione", placeholder="Es. Sponsorizzata Instagram")
        with c2:
            costo_input = st.text_input("Costo (€)", placeholder="es. 5,00")
        with c3:
            chi = st.selectbox("Chi paga", ["Elia", "Tommy"])

        if st.button("Inserisci spesa", type="primary", use_container_width=True):
            if descr and costo_input:
                try:
                    costo_float  = float(costo_input.replace(",", ".").strip())
                    costo_format = f"€ {costo_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    add_row(spese_ws, [descr, costo_format, chi, datetime.now().strftime("%d/%m/%Y %H:%M")])
                    st.success("Spesa inserita.")
                    st.rerun()
                except ValueError:
                    st.warning("Inserisci un numero valido.")
            else:
                st.warning("Inserisci descrizione e costo.")

        st.markdown("### Storico spese")
        spese_df = get_data(spese_ws)
        if spese_df.empty:
            st.info("Nessuna spesa registrata.")
        else:
            spese_df["Costo"] = spese_df["Costo"].apply(_clean_price).round(2)
            _ts = pd.to_datetime(spese_df["Timestamp"].astype(str).str.strip(), format="%d/%m/%Y %H:%M", errors="coerce")
            spese_df = spese_df.assign(_ts=_ts).sort_values("_ts", ascending=False).drop(columns=["_ts"])
            spese_df = spese_df.rename(columns={"Chi": "Pagata da"})
            spese_df["Costo (€)"] = spese_df["Costo"].map(lambda x: f"€ {x:.2f}")
            st.dataframe(spese_df[["Timestamp", "Descrizione", "Pagata da", "Costo (€)"]], use_container_width=True, hide_index=True)

    # ──────────────────────────────────────────────────────────────────────────
    # VENDITE
    # ──────────────────────────────────────────────────────────────────────────
    elif menu == "Vendite":
        st.markdown("## Vendite")
        st.markdown("### Registra nuovo ordine")

        prodotti_df  = get_data(prodotti_ws)
        nomi_prodotti = sorted(prodotti_df["Nome"].unique().tolist())

        prodotti_scelti = st.multiselect("Prodotti venduti", nomi_prodotti)
        venditore       = st.selectbox("Venditore", ["Elia", "Tommy"])
        prezzo_totale   = st.number_input("Prezzo totale vendita (€)", min_value=0.0, step=0.5)

        quantita_vendute = {}
        for p in prodotti_scelti:
            quantita_vendute[p] = st.number_input(f"Quantità — {p}", min_value=1, step=1, key=p)

        if st.button("Registra vendita", type="primary"):
            if prodotti_scelti and prezzo_totale > 0:
                vendite_generate, _ = registra_vendita_multipla(prodotti_df, quantita_vendute, prezzo_totale, venditore)
                for v in vendite_generate:
                    add_row(vendite_ws, v)
                from data_utils import send_telegram_message
                send_telegram_message(
                    f"<b>Nuova vendita</b>\nVenditore: {venditore}\n"
                    f"Prodotti: {', '.join(prodotti_scelti)}\nTotale: € {prezzo_totale:.2f}"
                )
                st.success(f"Vendita registrata — {len(vendite_generate)} articoli")
                st.rerun()
            else:
                st.warning("Seleziona almeno un prodotto e inserisci il prezzo.")

        st.markdown("---")
        st.markdown("### Ordini precedenti")
        vendite_storico = get_data(vendite_ws)

        if vendite_storico.empty:
            st.info("Nessun ordine registrato.")
        else:
            vendite_storico = vendite_storico.copy()
            vendite_storico["Venditore"] = vendite_storico["Venditore"].astype(str).str.strip().str.capitalize()
            vendite_storico["Timestamp"] = vendite_storico.get("Timestamp", "").astype(str).str.strip()
            vendite_storico["Prezzo_totale_vendita"] = vendite_storico["Prezzo_totale_vendita"].apply(_clean_price)
            vendite_storico["Quantita"] = pd.to_numeric(vendite_storico["Quantita"], errors="coerce").fillna(0).astype(int)

            ordini = (
                vendite_storico
                .groupby(["Venditore", "Timestamp"], as_index=False)
                .agg(Articoli=("Prodotto", "count"), Pezzi=("Quantita", "sum"), Totale=("Prezzo_totale_vendita", "sum"))
            )
            ordini["_ts"] = pd.to_datetime(ordini["Timestamp"], format="%d/%m/%Y %H:%M", errors="coerce")
            idx_valid = ordini.dropna(subset=["_ts"]).sort_values("_ts", ascending=True).index
            ordini.loc[idx_valid, "Ordine #"] = range(1, len(idx_valid) + 1)
            ordini = ordini.sort_values("_ts", ascending=False).reset_index(drop=True)
            ordini["Ordine #"] = ordini["Ordine #"].astype(int)
            ordini["Totale (€)"] = ordini["Totale"].round(2)

            st.dataframe(ordini[["Ordine #", "Venditore", "Timestamp", "Totale (€)"]], use_container_width=True, hide_index=True)

            with st.expander("Dettaglio prodotti per ordine"):
                for _, row in ordini.iterrows():
                    mask = (vendite_storico["Venditore"] == row["Venditore"]) & (vendite_storico["Timestamp"] == row["Timestamp"])
                    dettaglio = vendite_storico.loc[mask, ["Prodotto", "Quantita", "Prezzo_totale_vendita"]].copy()
                    dettaglio["Prezzo_totale_vendita"] = dettaglio["Prezzo_totale_vendita"].round(2)
                    st.write(f"**Ordine #{row['Ordine #']}** — {row['Venditore']} — {row['Timestamp']} — € {row['Totale (€)']:.2f}")
                    st.dataframe(dettaglio.rename(columns={"Prezzo_totale_vendita": "Quota ricavo (€)"}), use_container_width=True, hide_index=True)

    # ──────────────────────────────────────────────────────────────────────────
    # INVENTARIO
    # ──────────────────────────────────────────────────────────────────────────
    elif menu == "Inventario":
        st.markdown("## Inventario")

        prodotti_df  = get_data(prodotti_ws)
        vendite_df   = get_data(vendite_ws)
        inventario_df = inventario_aggregato(prodotti_df, vendite_df)
        inventario_df = inventario_df[inventario_df["Quantità residua"].fillna(0) > 0].copy()

        soglia_bassa = 2
        low_stock = inventario_df[inventario_df["Quantità residua"] <= soglia_bassa]
        if not low_stock.empty:
            st.markdown(f"**{len(low_stock)} prodott{'o' if len(low_stock)==1 else 'i'} con scorte basse (≤ {soglia_bassa} pz)**")
            for _, r in low_stock.iterrows():
                st.markdown(f'<div class="alert-low-stock"><b>{r["Prodotto"]}</b> — {int(r["Quantità residua"])} pezzi rimasti</div>', unsafe_allow_html=True)
            st.markdown("")

        if not inventario_df.empty and not prodotti_df.empty:
            prodotti_df_c = prodotti_df.copy()
            prodotti_df_c["Prezzo_unitario"] = prodotti_df_c["Prezzo_unitario"].apply(_clean_price)
            prodotti_df_c["Quantita"] = pd.to_numeric(prodotti_df_c["Quantita"], errors="coerce").fillna(0)
            valore_acquisto = float((prodotti_df_c["Prezzo_unitario"] * prodotti_df_c["Quantita"]).sum())
            valore_residuo  = float((inventario_df["Costo medio unitario(€)"] * inventario_df["Quantità residua"]).sum())
            pz_totali       = int(inventario_df["Quantità residua"].sum())

            k1, k2, k3 = st.columns(3)
            k1.metric("Valore acquistato",          f"€ {valore_acquisto:.2f}")
            k2.metric("Valore residuo in magazzino", f"€ {valore_residuo:.2f}")
            k3.metric("Pezzi in magazzino",          pz_totali)

        st.dataframe(inventario_df, use_container_width=True, hide_index=True)
        st.caption("Costo medio e prezzo medio calcolati automaticamente.")

        if not inventario_df.empty:
            st.markdown('<div class="section-title">Valore residuo per prodotto</div>', unsafe_allow_html=True)
            inv_plot = inventario_df.copy()
            inv_plot["Valore residuo (€)"] = (inv_plot["Costo medio unitario(€)"] * inv_plot["Quantità residua"]).round(2)
            inv_plot = inv_plot.sort_values("Valore residuo (€)", ascending=True)

            fig_inv = go.Figure(go.Bar(
                x=inv_plot["Valore residuo (€)"],
                y=inv_plot["Prodotto"],
                orientation="h",
                marker=dict(color=inv_plot["Valore residuo (€)"],
                            colorscale=[[0, "#2a4a70"], [1, "#6ab0f5"]], showscale=False),
                text=[f"€ {v:.2f}" for v in inv_plot["Valore residuo (€)"]],
                textposition="outside",
                textfont=dict(color="#bbb", size=11)
            ))
            fig_inv.update_layout(
                **CHART_LAYOUT,
                height=max(250, len(inv_plot) * 35),
                margin=dict(l=0, r=65, t=20, b=0),
                xaxis=dict(showgrid=False, showticklabels=False),
                yaxis=dict(gridcolor="#243550", tickfont=dict(color="#aaa")),
            )
            st.plotly_chart(fig_inv, use_container_width=True)

        st.markdown("### Aggiungi prodotto")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            nome = st.text_input("Nome prodotto")
        with col2:
            prezzo_input = st.text_input("Prezzo unitario (€)", placeholder="es. 4,50")
        with col3:
            quantita = st.number_input("Quantità", min_value=1, step=1)
        with col4:
            comprato_da = st.selectbox("Comprato da", ["Elia", "Tommy"])

        if st.button("Aggiungi", type="primary", use_container_width=True):
            if nome and prezzo_input:
                try:
                    prezzo_float  = float(prezzo_input.replace(",", ".").strip())
                    prezzo_format = f"€ {prezzo_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    add_row(prodotti_ws, [nome, prezzo_format, int(quantita), comprato_da, datetime.now().strftime("%d/%m/%Y %H:%M")])
                    st.success(f"Prodotto '{nome}' aggiunto.")
                    st.rerun()
                except ValueError:
                    st.warning("Inserisci un numero valido per il prezzo.")
