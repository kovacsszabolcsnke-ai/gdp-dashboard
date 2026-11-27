"""Hitel jutalék számfejtés – Streamlit felület.

Indítás:  streamlit run jutalek_app.py
"""

from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from hitel_jutalek import szamitas as sz
from hitel_jutalek.export import excel, kozvetito_elszamolo

st.set_page_config(page_title="Hitel jutalék számfejtés", page_icon="💰", layout="wide")

MINTA = Path(__file__).parent / "data" / "minta_hitelek.csv"
HONAPOK = ["január", "február", "március", "április", "május", "június", "július",
           "augusztus", "szeptember", "október", "november", "december"]


def ft(x) -> str:
    return f"{int(x):,} Ft".replace(",", " ")


def beolvas(fajl) -> pd.DataFrame:
    if fajl.name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(fajl)
    nyers = fajl.getvalue()
    for kod in ("utf-8-sig", "cp1250"):
        try:
            szoveg = nyers.decode(kod)
            break
        except UnicodeDecodeError:
            continue
    return pd.read_csv(BytesIO(szoveg.encode("utf-8")), sep=None, engine="python")


# --- Állapot -----------------------------------------------------------------
if "cfg" not in st.session_state:
    st.session_state.cfg = sz.Beallitasok()
    st.session_state.verzio = 0
if "hitelek" not in st.session_state:
    st.session_state.hitelek = pd.read_csv(MINTA, sep=";")
    st.session_state.hitel_forras = "minta adat"

cfg: sz.Beallitasok = st.session_state.cfg
v = st.session_state.verzio

# --- Oldalsáv ----------------------------------------------------------------
with st.sidebar:
    st.header("Elszámolási időszak")
    ma = date.today()
    ev = st.number_input("Év", 2000, 2100, ma.year, step=1)
    honap = st.selectbox("Hónap", range(1, 13), index=ma.month - 1, format_func=lambda m: HONAPOK[m - 1])
    idoszak = f"{ev}-{honap:02d}"

    st.divider()
    st.header("Beállítások mentése")
    feltoltott_cfg = st.file_uploader("Beállítások betöltése (JSON)", type="json", key=f"cfgfel_{v}")
    if feltoltott_cfg is not None:
        try:
            st.session_state.cfg = sz.Beallitasok.from_json(feltoltott_cfg.getvalue().decode("utf-8"))
            st.session_state.verzio += 1
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"Hibás beállítás fájl: {e}")
    if st.button("Alapértelmezett beállítások"):
        st.session_state.cfg = sz.Beallitasok()
        st.session_state.verzio += 1
        st.rerun()

st.title("💰 Hitel jutalék számfejtés")
st.caption(f"Elszámolási időszak: **{ev}. {HONAPOK[honap - 1]}** – "
           "a hónapban folyósított hitelek jutaléka, a hónapban megszűnt hitelek stornója.")

tab_hitel, tab_beall, tab_eredmeny, tab_elszamolo = st.tabs(
    ["1. Hitelek", "2. Beállítások", "3. Számfejtés", "4. Közvetítői elszámoló"]
)

# --- 1. Hitelek --------------------------------------------------------------
with tab_hitel:
    c1, c2 = st.columns([3, 1])
    with c1:
        fajl = st.file_uploader("Folyósítási lista feltöltése (Excel vagy CSV)", type=["xlsx", "xls", "csv"])
    with c2:
        sablon = pd.DataFrame(columns=sz.HITEL_OSZLOPOK).to_csv(index=False, sep=";").encode("utf-8-sig")
        st.download_button("Üres sablon (CSV)", sablon, "hitel_sablon.csv", "text/csv")
        if st.button("Minta adat betöltése"):
            st.session_state.hitelek = pd.read_csv(MINTA, sep=";")
            st.session_state.hitel_forras = "minta adat"
            st.session_state.pop("utolso_fajl", None)
    if fajl is not None and st.session_state.get("utolso_fajl") != (fajl.name, fajl.size):
        try:
            st.session_state.hitelek = beolvas(fajl)
            st.session_state.hitel_forras = fajl.name
            st.session_state.utolso_fajl = (fajl.name, fajl.size)
        except Exception as e:  # noqa: BLE001
            st.error(f"A fájl nem olvasható: {e}")

    st.write(f"Forrás: **{st.session_state.hitel_forras}** – a táblázat itt is szerkeszthető.")
    with st.expander("Elvárt oszlopok"):
        st.markdown(
            "- **Kötelező:** " + ", ".join(sz.KOTELEZO_OSZLOPOK) + "\n"
            f"- **Opcionális:** {sz.UGYFEL}, {sz.MEGSZUNES} (előtörlesztés / felmondás dátuma – storno alapja)\n"
            "- Dátum: `2026-11-05` vagy `2026.11.05.`; az összeg forintban, szóköz nélkül."
        )
    try:
        hitel_nezet = sz.hitelek_elokeszitese(st.session_state.hitelek)
    except ValueError as e:
        st.error(str(e))
        st.stop()
    hitelek = st.data_editor(
        hitel_nezet,
        num_rows="dynamic",
        width="stretch",
        key=f"hitel_{st.session_state.hitel_forras}",
        column_config={
            sz.OSSZEG: st.column_config.NumberColumn(format="%d Ft"),
            sz.FOLYOSITAS: st.column_config.DateColumn(format="YYYY.MM.DD"),
            sz.MEGSZUNES: st.column_config.DateColumn(format="YYYY.MM.DD"),
        },
    )

# --- 2. Beállítások ----------------------------------------------------------
with tab_beall:
    st.subheader("Bank jutalék")
    st.caption("A bank által a cégnek fizetett jutalék a folyósított összeg %-ában. "
               "Max jutalék = 0 esetén nincs plafon.")
    bank_j = st.data_editor(cfg.bank_jutalekok, num_rows="dynamic", width="stretch", key=f"bank_{v}")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Közvetítői szintek")
        st.caption("Részesedés a bank jutalékból. A felettes a saját és az alatta "
                   "kifizetett legmagasabb % különbségét kapja (differenciális felülíró).")
        szintek = st.data_editor(cfg.szintek, num_rows="dynamic", width="stretch", key=f"szint_{v}")
    with c2:
        st.subheader("Storno (visszaterhelés)")
        st.caption("Ha a hitel a folyósítástól számított N teljes hónapon belül megszűnik, "
                   "ennyi %-ot terhelünk vissza (a legkisebb illeszkedő sor érvényes).")
        storno = st.data_editor(cfg.storno, num_rows="dynamic", width="stretch", key=f"storno_{v}")

    st.subheader("Közvetítők")
    kozvetitok = st.data_editor(
        cfg.kozvetitok, num_rows="dynamic", width="stretch", key=f"kozv_{v}",
        column_config={
            "Szint": st.column_config.SelectboxColumn(options=[s for s in szintek["Szint"].dropna() if s]),
            "Kifizetés módja": st.column_config.SelectboxColumn(options=sz.KIFIZETESI_MODOK),
        },
    )

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Volumen bónusz")
        st.caption("Havi saját folyósított volumen alapján plusz %, a saját értékesítésű bank jutalékra.")
        bonusz = st.data_editor(cfg.bonusz, num_rows="dynamic", width="stretch", key=f"bonusz_{v}")
    with c2:
        st.subheader("Adók, járulékok")
        a = cfg.ado
        ado = {
            "szja_szazalek": st.number_input("SZJA %", value=float(a["szja_szazalek"]), key=f"szja_{v}"),
            "tb_jarulek_szazalek": st.number_input("TB járulék %", value=float(a["tb_jarulek_szazalek"]), key=f"tb_{v}"),
            "szocho_szazalek": st.number_input("Szocho % (cégnél)", value=float(a["szocho_szazalek"]), key=f"szocho_{v}"),
            "koltseghanyad_szazalek": st.number_input("Költséghányad % (megbízási)", value=float(a["koltseghanyad_szazalek"]), key=f"kh_{v}"),
            "minimalber_ft": st.number_input("Minimálbér (Ft)", value=int(a["minimalber_ft"]), step=1000, key=f"minber_{v}",
                                             help="Megbízásinál a minimálbér 30%-a alatti havi jövedelemnél nincs TB járulék."),
            "afa_szazalek": st.number_input("ÁFA % (számlás)", value=float(a["afa_szazalek"]), key=f"afa_{v}",
                                            help="A hitelközvetítés jellemzően tárgyi adómentes, ezért alapból 0%."),
        }

    aktualis = sz.Beallitasok(bank_j, szintek, kozvetitok, storno, bonusz, ado)
    st.download_button("Beállítások letöltése (JSON)", aktualis.to_json().encode("utf-8"),
                       "jutalek_beallitasok.json", "application/json")

# --- Számítás ----------------------------------------------------------------
try:
    e = sz.szamfejtes(hitelek, aktualis, int(ev), int(honap))
except ValueError as hiba:
    st.error(str(hiba))
    st.stop()

# --- 3. Számfejtés -----------------------------------------------------------
with tab_eredmeny:
    if not e.hibak.empty:
        st.warning(f"{len(e.hibak)} tétel nem számolható el – lásd lent a Hibák táblát.")
    k = st.columns(3)
    k[0].metric("Bank jutalék bevétel", ft(e.ceg["Bank jutalék bevétel"]))
    k[1].metric("Bank storno", ft(e.ceg["Bank storno"]))
    k[2].metric("Közvetítőknek bruttó", ft(e.ceg["Közvetítőknek bruttó"]))
    k = st.columns(3)
    k[0].metric("Cégnél maradó", ft(e.ceg["Cégnél maradó"]))
    k[1].metric("Munkáltatói szocho", ft(e.ceg["Munkáltatói szocho"]))
    k[2].metric("Átvitt tartozások", ft(e.ceg["Átvitt tartozások"]))

    st.subheader("Közvetítőnkénti összesítő")
    if e.osszesito.empty:
        st.info("Ebben az időszakban nincs elszámolható tétel.")
    else:
        osszeg_oszlopok = [c for c in e.osszesito.columns if c not in ("Közvetítő", "Szint", "Kifizetés módja", "Darab")]
        st.dataframe(
            e.osszesito, width="stretch", hide_index=True,
            column_config={c: st.column_config.NumberColumn(format="localized") for c in osszeg_oszlopok},
        )
        if e.ceg["Átvitt tartozások"] < 0:
            st.info("Negatív egyenleg (storno > jutalék) esetén nincs kifizetés; "
                    "az összeg az *Átvitt tartozás* oszlopban szerepel, a következő hónapban kell beszámítani.")

    st.subheader("Tételek")
    tipusok = st.multiselect("Típus", [sz.TIPUS_JUTALEK, sz.TIPUS_STORNO, sz.TIPUS_BONUSZ],
                             default=[sz.TIPUS_JUTALEK, sz.TIPUS_STORNO, sz.TIPUS_BONUSZ])
    st.dataframe(e.tetelek[e.tetelek["Típus"].isin(tipusok)], width="stretch", hide_index=True)

    if not e.hibak.empty:
        st.subheader("Hibák")
        st.dataframe(e.hibak, width="stretch", hide_index=True)

    st.download_button(
        "⬇️ Teljes számfejtés letöltése (Excel)", excel(e, idoszak), f"jutalek_szamfejtes_{idoszak}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary",
    )

# --- 4. Közvetítői elszámoló -------------------------------------------------
with tab_elszamolo:
    if e.osszesito.empty:
        st.info("Ebben az időszakban nincs elszámolható tétel.")
    else:
        nev = st.selectbox("Közvetítő", e.osszesito["Közvetítő"])
        sor = e.osszesito.set_index("Közvetítő").loc[nev]
        st.markdown(f"### {nev} – {ev}. {HONAPOK[honap - 1]}")
        st.caption(f"{sor['Szint']} · kifizetés módja: {sor['Kifizetés módja']}")
        k = st.columns(4)
        k[0].metric("Bruttó jutalék", ft(sor["Bruttó jutalék"]))
        k[1].metric("Levonások", ft(sor["SZJA"] + sor["TB járulék"]))
        k[2].metric("Kifizetendő", ft(sor["Kifizetendő"]))
        k[3].metric("Átvitt tartozás", ft(sor["Átvitt tartozás"]))
        bontas = pd.DataFrame({
            "Megnevezés": ["Saját jutalék", "Felülíró jutalék", "Volumen bónusz", "Storno", "Bruttó jutalék",
                           "SZJA", "TB járulék", "ÁFA", "Kifizetendő"],
            "Összeg (Ft)": [sor["Saját jutalék"], sor["Felülíró jutalék"], sor["Volumen bónusz"], sor["Storno"],
                            sor["Bruttó jutalék"], -sor["SZJA"], -sor["TB járulék"], sor["ÁFA"], sor["Kifizetendő"]],
        })
        st.dataframe(bontas, hide_index=True, column_config={"Összeg (Ft)": st.column_config.NumberColumn(format="localized")})
        st.dataframe(e.tetelek[e.tetelek["Kedvezményezett"] == nev], width="stretch", hide_index=True)
        st.download_button(
            "⬇️ Elszámoló letöltése (Excel)", kozvetito_elszamolo(e, nev, idoszak),
            f"elszamolo_{nev.replace(' ', '_')}_{idoszak}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
