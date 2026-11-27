"""Hitel jutalék számfejtés – számítási logika.

A modul Streamlit-független, így tesztelhető és parancssorból is használható.

Fogalmak
--------
* Bank jutalék: amit a bank fizet a közvetítő cégnek egy folyósított hitel után
  (a folyósított összeg adott %-a, opcionális Ft-os plafonnal).
* Részesedés: a közvetítői szinthez tartozó %, a bank jutalékból számolva.
* Differenciális felülíró (override): a felettes a saját szint-%-a és a
  láncban alatta már kifizetett legmagasabb % különbségét kapja.
* Storno: ha a hitel a folyósítástól számított X hónapon belül megszűnik
  (előtörlesztés, felmondás), a bank visszaterheli a jutalék egy részét;
  ezt arányosan minden érintett közvetítőnél levonjuk.
* Volumen bónusz: a közvetítő havi saját folyósított volumene alapján járó
  plusz %, a saját értékesítésű bank jutalékra vetítve.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

# --- Bemeneti oszlopnevek ----------------------------------------------------
SZERZODES = "Szerződésszám"
UGYFEL = "Ügyfél"
BANK = "Bank"
TERMEK = "Termék"
OSSZEG = "Folyósított összeg"
FOLYOSITAS = "Folyósítás dátuma"
KOZVETITO = "Közvetítő"
MEGSZUNES = "Megszűnés dátuma"

HITEL_OSZLOPOK = [SZERZODES, UGYFEL, BANK, TERMEK, OSSZEG, FOLYOSITAS, KOZVETITO, MEGSZUNES]
KOTELEZO_OSZLOPOK = [SZERZODES, BANK, TERMEK, OSSZEG, FOLYOSITAS, KOZVETITO]

KIFIZETES_SZAMLAS = "Számlás"
KIFIZETES_MEGBIZASI = "Megbízási"
KIFIZETESI_MODOK = [KIFIZETES_SZAMLAS, KIFIZETES_MEGBIZASI]

TIPUS_JUTALEK = "Jutalék"
TIPUS_STORNO = "Storno"
TIPUS_BONUSZ = "Volumen bónusz"
SZEREP_SAJAT = "Saját"
SZEREP_FELULIRO = "Felülíró"


def _df(rows: list[dict], columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=columns)


def alap_bank_jutalekok() -> pd.DataFrame:
    return _df(
        [
            {"Bank": "Bank A", "Termék": "Lakáshitel", "Jutalék %": 1.2, "Max jutalék (Ft)": 600_000},
            {"Bank": "Bank A", "Termék": "Szabad felhasználású jelzálog", "Jutalék %": 1.5, "Max jutalék (Ft)": 450_000},
            {"Bank": "Bank A", "Termék": "Személyi kölcsön", "Jutalék %": 2.5, "Max jutalék (Ft)": 0},
            {"Bank": "Bank B", "Termék": "Lakáshitel", "Jutalék %": 1.0, "Max jutalék (Ft)": 500_000},
            {"Bank": "Bank B", "Termék": "Személyi kölcsön", "Jutalék %": 3.0, "Max jutalék (Ft)": 300_000},
            {"Bank": "Bank C", "Termék": "Lakáshitel", "Jutalék %": 1.1, "Max jutalék (Ft)": 0},
            {"Bank": "Bank C", "Termék": "Babaváró / támogatott", "Jutalék %": 0.8, "Max jutalék (Ft)": 100_000},
        ],
        ["Bank", "Termék", "Jutalék %", "Max jutalék (Ft)"],
    )


def alap_szintek() -> pd.DataFrame:
    return _df(
        [
            {"Szint": "Üzletkötő", "Részesedés %": 50.0},
            {"Szint": "Csoportvezető", "Részesedés %": 60.0},
            {"Szint": "Regionális igazgató", "Részesedés %": 65.0},
        ],
        ["Szint", "Részesedés %"],
    )


def alap_kozvetitok() -> pd.DataFrame:
    return _df(
        [
            {"Közvetítő": "Szabó Éva", "Szint": "Regionális igazgató", "Felettes": "", "Kifizetés módja": KIFIZETES_SZAMLAS},
            {"Közvetítő": "Nagy Péter", "Szint": "Csoportvezető", "Felettes": "Szabó Éva", "Kifizetés módja": KIFIZETES_SZAMLAS},
            {"Közvetítő": "Horváth László", "Szint": "Csoportvezető", "Felettes": "Szabó Éva", "Kifizetés módja": KIFIZETES_SZAMLAS},
            {"Közvetítő": "Kiss Anna", "Szint": "Üzletkötő", "Felettes": "Nagy Péter", "Kifizetés módja": KIFIZETES_MEGBIZASI},
            {"Közvetítő": "Tóth Gábor", "Szint": "Üzletkötő", "Felettes": "Nagy Péter", "Kifizetés módja": KIFIZETES_SZAMLAS},
            {"Közvetítő": "Varga Dóra", "Szint": "Üzletkötő", "Felettes": "Horváth László", "Kifizetés módja": KIFIZETES_MEGBIZASI},
        ],
        ["Közvetítő", "Szint", "Felettes", "Kifizetés módja"],
    )


def alap_storno() -> pd.DataFrame:
    # "Hónapon belül": a folyósítástól a megszűnésig eltelt teljes hónapok száma < érték
    return _df(
        [
            {"Hónapon belül": 6, "Visszaterhelés %": 100.0},
            {"Hónapon belül": 12, "Visszaterhelés %": 50.0},
        ],
        ["Hónapon belül", "Visszaterhelés %"],
    )


def alap_bonusz() -> pd.DataFrame:
    return _df(
        [
            {"Min. havi volumen (Ft)": 100_000_000, "Plusz %": 2.0},
            {"Min. havi volumen (Ft)": 200_000_000, "Plusz %": 4.0},
        ],
        ["Min. havi volumen (Ft)", "Plusz %"],
    )


def alap_ado() -> dict:
    return {
        "szja_szazalek": 15.0,
        "tb_jarulek_szazalek": 18.5,
        "szocho_szazalek": 13.0,
        "koltseghanyad_szazalek": 10.0,
        # 2026-os minimálbér – ellenőrizendő! Megbízásinál a biztosítási
        # kötelezettség határa a minimálbér 30%-a.
        "minimalber_ft": 322_800,
        # A hitelközvetítés jellemzően tárgyi adómentes (Áfa tv. 86. §),
        # ezért alapértelmezetten 0%.
        "afa_szazalek": 0.0,
    }


@dataclass
class Beallitasok:
    bank_jutalekok: pd.DataFrame = field(default_factory=alap_bank_jutalekok)
    szintek: pd.DataFrame = field(default_factory=alap_szintek)
    kozvetitok: pd.DataFrame = field(default_factory=alap_kozvetitok)
    storno: pd.DataFrame = field(default_factory=alap_storno)
    bonusz: pd.DataFrame = field(default_factory=alap_bonusz)
    ado: dict = field(default_factory=alap_ado)

    _TABLAK = ("bank_jutalekok", "szintek", "kozvetitok", "storno", "bonusz")

    def to_json(self) -> str:
        adat = {t: getattr(self, t).fillna("").to_dict(orient="records") for t in self._TABLAK}
        adat["ado"] = self.ado
        return json.dumps(adat, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, szoveg: str) -> "Beallitasok":
        adat = json.loads(szoveg)
        alap = cls()
        kwargs = {}
        for t in cls._TABLAK:
            oszlopok = list(getattr(alap, t).columns)
            kwargs[t] = pd.DataFrame(adat.get(t, []), columns=oszlopok)
        kwargs["ado"] = {**alap.ado, **adat.get("ado", {})}
        return cls(**kwargs)


@dataclass
class Eredmeny:
    tetelek: pd.DataFrame
    osszesito: pd.DataFrame
    hibak: pd.DataFrame
    ceg: dict


# --- Segédfüggvények ----------------------------------------------------------

def kerekit(x: float) -> int:
    """Forintra kerekítés, fél felfelé (nem banker's rounding)."""
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def eltelt_honapok(tol: date, ig: date) -> int:
    """Két dátum között eltelt teljes hónapok száma."""
    h = (ig.year - tol.year) * 12 + (ig.month - tol.month)
    if ig.day < tol.day:
        h -= 1
    return h


def _szoveg(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    return str(x).strip()


def _szam(x, alap: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return alap
    return alap if pd.isna(v) else v


def datum(x) -> date | None:
    """Dátum értelmezése: Excel dátum, 2026-11-05, 2026.11.05., 2026. 11. 05."""
    if x is None or (not isinstance(x, str) and pd.isna(x)):
        return None
    if isinstance(x, str):
        x = x.strip().rstrip(".").replace(". ", "-").replace(".", "-").replace("/", "-")
        if not x:
            return None
    d = pd.to_datetime(x, errors="coerce", yearfirst=True)
    return None if pd.isna(d) else d.date()


def hitelek_elokeszitese(df: pd.DataFrame) -> pd.DataFrame:
    """Oszlopok ellenőrzése, típuskonverzió."""
    hianyzo = [o for o in KOTELEZO_OSZLOPOK if o not in df.columns]
    if hianyzo:
        raise ValueError("Hiányzó oszlop(ok) a hitel listában: " + ", ".join(hianyzo))
    df = df.copy()
    for o in HITEL_OSZLOPOK:
        if o not in df.columns:
            df[o] = None
    df = df[HITEL_OSZLOPOK]
    for o in (SZERZODES, UGYFEL, BANK, TERMEK, KOZVETITO):
        df[o] = df[o].map(_szoveg)
    df[OSSZEG] = pd.to_numeric(df[OSSZEG], errors="coerce")
    for o in (FOLYOSITAS, MEGSZUNES):
        df[o] = df[o].map(datum)
    df = df[df[SZERZODES] != ""]
    return df.reset_index(drop=True)


def _honap_kezdet_veg(ev: int, honap: int) -> tuple[date, date]:
    kezdet = date(ev, honap, 1)
    veg = date(ev + (honap == 12), honap % 12 + 1, 1)
    return kezdet, veg


def _bank_tabla(cfg: Beallitasok) -> dict[tuple[str, str], tuple[float, float]]:
    t = {}
    for _, r in cfg.bank_jutalekok.iterrows():
        bank, termek = _szoveg(r["Bank"]), _szoveg(r["Termék"])
        if bank:
            t[(bank.lower(), termek.lower())] = (_szam(r["Jutalék %"]), _szam(r["Max jutalék (Ft)"]))
    return t


def bank_jutalek(osszeg: float, szazalek: float, plafon: float) -> int:
    j = osszeg * szazalek / 100
    if plafon and plafon > 0:
        j = min(j, plafon)
    return kerekit(j)


def _kozvetito_tabla(cfg: Beallitasok) -> dict[str, dict]:
    return {
        _szoveg(r["Közvetítő"]): {
            "szint": _szoveg(r["Szint"]),
            "felettes": _szoveg(r["Felettes"]),
            "mod": _szoveg(r["Kifizetés módja"]) or KIFIZETES_SZAMLAS,
        }
        for _, r in cfg.kozvetitok.iterrows()
        if _szoveg(r["Közvetítő"])
    }


def lanc(kozvetito: str, kozv: dict[str, dict]) -> list[str]:
    """A közvetítő és felettesei alulról felfelé. Hibát dob ismeretlen névre / körre."""
    eredmeny: list[str] = []
    akt = kozvetito
    while akt:
        if akt not in kozv:
            if akt == kozvetito:
                raise ValueError(f"Ismeretlen közvetítő: {akt}")
            raise ValueError(f"Ismeretlen felettes ({akt}) – {eredmeny[-1]} felettese")
        if akt in eredmeny:
            raise ValueError("Körkörös felettesi lánc: " + " → ".join(eredmeny + [akt]))
        eredmeny.append(akt)
        akt = kozv[akt]["felettes"]
    return eredmeny


def felosztas(bank_j: int, kozvetito: str, kozv: dict, szint_szazalek: dict[str, float]) -> list[dict]:
    """Bank jutalék felosztása a lánc mentén differenciális felülíróval."""
    sorok = []
    kifizetett = 0.0
    for i, nev in enumerate(lanc(kozvetito, kozv)):
        szint = kozv[nev]["szint"]
        if szint not in szint_szazalek:
            raise ValueError(f"Ismeretlen szint ({szint}) – {nev}")
        szazalek = szint_szazalek[szint]
        kulonbseg = max(0.0, szazalek - kifizetett)
        if kulonbseg > 0:
            sorok.append(
                {
                    "Kedvezményezett": nev,
                    "Szerep": SZEREP_SAJAT if i == 0 else SZEREP_FELULIRO,
                    "Részesedés %": round(kulonbseg, 4),
                    "Összeg": kerekit(bank_j * kulonbseg / 100),
                }
            )
        kifizetett = max(kifizetett, szazalek)
    return sorok


def storno_szazalek(honapok: int, cfg: Beallitasok) -> float:
    szabalyok = sorted(
        (int(_szam(r["Hónapon belül"])), _szam(r["Visszaterhelés %"]))
        for _, r in cfg.storno.iterrows()
        if _szam(r["Hónapon belül"]) > 0
    )
    for hatar, sz in szabalyok:
        if honapok < hatar:
            return sz
    return 0.0


def bonusz_szazalek(volumen: float, cfg: Beallitasok) -> float:
    sz = 0.0
    for _, r in cfg.bonusz.iterrows():
        if volumen >= _szam(r["Min. havi volumen (Ft)"], float("inf")):
            sz = max(sz, _szam(r["Plusz %"]))
    return sz


def levonasok(brutto: int, mod: str, ado: dict) -> dict:
    """Közvetítőnkénti járulék/adó és kifizetendő összeg."""
    nulla = {"SZJA": 0, "TB járulék": 0, "ÁFA": 0, "Kifizetendő": 0, "Munkáltatói szocho": 0, "Átvitt tartozás": 0}
    if brutto <= 0:
        return {**nulla, "Átvitt tartozás": brutto}
    if mod == KIFIZETES_MEGBIZASI:
        jov = brutto * (1 - _szam(ado.get("koltseghanyad_szazalek")) / 100)
        szja = kerekit(jov * _szam(ado.get("szja_szazalek")) / 100)
        biztositott = jov >= 0.3 * _szam(ado.get("minimalber_ft"))
        tb = kerekit(jov * _szam(ado.get("tb_jarulek_szazalek")) / 100) if biztositott else 0
        szocho = kerekit(jov * _szam(ado.get("szocho_szazalek")) / 100)
        return {**nulla, "SZJA": szja, "TB járulék": tb, "Kifizetendő": brutto - szja - tb, "Munkáltatói szocho": szocho}
    afa = kerekit(brutto * _szam(ado.get("afa_szazalek")) / 100)
    return {**nulla, "ÁFA": afa, "Kifizetendő": brutto + afa}


# --- Fő számítás --------------------------------------------------------------

TETEL_OSZLOPOK = [
    "Típus", SZERZODES, UGYFEL, BANK, TERMEK, OSSZEG, FOLYOSITAS, MEGSZUNES, "Értékesítő",
    "Bank jutalék %", "Bank jutalék", "Kedvezményezett", "Szerep", "Részesedés %", "Szorzó %", "Összeg",
]


def szamfejtes(hitelek: pd.DataFrame, cfg: Beallitasok, ev: int, honap: int) -> Eredmeny:
    """Egy elszámolási hónap számfejtése.

    * Jutalék: a hónapban folyósított hitelek.
    * Storno: a hónapban megszűnt hitelek, ha a storno időablakon belül vannak.
    * Volumen bónusz: a hónapban folyósított saját volumen alapján.
    """
    hitelek = hitelek_elokeszitese(hitelek)
    kezdet, veg = _honap_kezdet_veg(ev, honap)
    bank_t = _bank_tabla(cfg)
    kozv = _kozvetito_tabla(cfg)
    szint_sz = {_szoveg(r["Szint"]): _szam(r["Részesedés %"]) for _, r in cfg.szintek.iterrows() if _szoveg(r["Szint"])}

    tetelek: list[dict] = []
    hibak: list[dict] = []
    ceg = {"Bank jutalék bevétel": 0, "Bank storno": 0}
    sajat_volumen: dict[str, float] = {}
    sajat_bank_j: dict[str, int] = {}

    if hitelek[SZERZODES].duplicated().any():
        for sz in hitelek.loc[hitelek[SZERZODES].duplicated(), SZERZODES].unique():
            hibak.append({SZERZODES: sz, "Hiba": "Ismétlődő szerződésszám – csak az első sor kerül elszámolásra"})
        hitelek = hitelek.drop_duplicates(SZERZODES)

    for _, h in hitelek.iterrows():
        alap = {o: h[o] for o in (SZERZODES, UGYFEL, BANK, TERMEK, OSSZEG, FOLYOSITAS, MEGSZUNES)}
        alap["Értékesítő"] = h[KOZVETITO]
        f, m = h[FOLYOSITAS], h[MEGSZUNES]
        if pd.isna(h[OSSZEG]) or h[OSSZEG] <= 0:
            hibak.append({SZERZODES: h[SZERZODES], "Hiba": "Hiányzó vagy hibás folyósított összeg"})
            continue
        if not isinstance(f, date):
            hibak.append({SZERZODES: h[SZERZODES], "Hiba": "Hiányzó vagy hibás folyósítási dátum"})
            continue
        jutalek_honap = kezdet <= f < veg
        storno_honap = isinstance(m, date) and kezdet <= m < veg
        if not (jutalek_honap or storno_honap):
            continue
        if isinstance(m, date) and m < f:
            hibak.append({SZERZODES: h[SZERZODES], "Hiba": "A megszűnés dátuma korábbi, mint a folyósításé"})
            continue

        kulcs = (h[BANK].lower(), h[TERMEK].lower())
        if kulcs not in bank_t:
            hibak.append({SZERZODES: h[SZERZODES], "Hiba": f"Nincs bank jutalék beállítva: {h[BANK]} / {h[TERMEK]}"})
            continue
        sz, plafon = bank_t[kulcs]
        bank_j = bank_jutalek(h[OSSZEG], sz, plafon)
        try:
            sorok = felosztas(bank_j, h[KOZVETITO], kozv, szint_sz)
        except ValueError as e:
            hibak.append({SZERZODES: h[SZERZODES], "Hiba": str(e)})
            continue

        if jutalek_honap:
            ceg["Bank jutalék bevétel"] += bank_j
            sajat_volumen[h[KOZVETITO]] = sajat_volumen.get(h[KOZVETITO], 0) + h[OSSZEG]
            sajat_bank_j[h[KOZVETITO]] = sajat_bank_j.get(h[KOZVETITO], 0) + bank_j
            for s in sorok:
                tetelek.append({**alap, "Típus": TIPUS_JUTALEK, "Bank jutalék %": sz, "Bank jutalék": bank_j, **s, "Szorzó %": 100.0})

        if storno_honap:
            vissza = storno_szazalek(eltelt_honapok(f, m), cfg)
            if vissza > 0:
                ceg["Bank storno"] -= kerekit(bank_j * vissza / 100)
                for s in sorok:
                    tetelek.append({
                        **alap, "Típus": TIPUS_STORNO, "Bank jutalék %": sz, "Bank jutalék": -kerekit(bank_j * vissza / 100),
                        **s, "Szorzó %": -vissza, "Összeg": -kerekit(s["Összeg"] * vissza / 100),
                    })

    for nev, vol in sajat_volumen.items():
        plusz = bonusz_szazalek(vol, cfg)
        if plusz > 0:
            tetelek.append({
                "Típus": TIPUS_BONUSZ, SZERZODES: "", UGYFEL: "", BANK: "", TERMEK: "", OSSZEG: vol,
                FOLYOSITAS: None, MEGSZUNES: None, "Értékesítő": nev, "Bank jutalék %": None,
                "Bank jutalék": sajat_bank_j[nev], "Kedvezményezett": nev, "Szerep": SZEREP_SAJAT,
                "Részesedés %": plusz, "Szorzó %": 100.0, "Összeg": kerekit(sajat_bank_j[nev] * plusz / 100),
            })

    tetelek_df = pd.DataFrame(tetelek, columns=TETEL_OSZLOPOK)
    osszesito = _osszesit(tetelek_df, kozv, cfg.ado)

    ceg["Közvetítőknek bruttó"] = int(tetelek_df["Összeg"].sum()) if len(tetelek_df) else 0
    ceg["Cégnél maradó"] = ceg["Bank jutalék bevétel"] + ceg["Bank storno"] - ceg["Közvetítőknek bruttó"]
    ceg["Munkáltatói szocho"] = int(osszesito["Munkáltatói szocho"].sum()) if len(osszesito) else 0
    ceg["Átvitt tartozások"] = int(osszesito["Átvitt tartozás"].sum()) if len(osszesito) else 0

    return Eredmeny(tetelek_df, osszesito, pd.DataFrame(hibak, columns=[SZERZODES, "Hiba"]), ceg)


OSSZESITO_OSZLOPOK = [
    "Közvetítő", "Szint", "Kifizetés módja", "Darab", "Saját volumen", "Saját jutalék", "Felülíró jutalék",
    "Volumen bónusz", "Storno", "Bruttó jutalék", "SZJA", "TB járulék", "ÁFA", "Kifizetendő",
    "Munkáltatói szocho", "Átvitt tartozás",
]


def _osszesit(t: pd.DataFrame, kozv: dict, ado: dict) -> pd.DataFrame:
    sorok = []
    for nev in sorted(t["Kedvezményezett"].dropna().unique()):
        s = t[t["Kedvezményezett"] == nev]
        jut = s[s["Típus"] == TIPUS_JUTALEK]
        sajat = jut[jut["Szerep"] == SZEREP_SAJAT]
        brutto = int(s["Összeg"].sum())
        mod = kozv.get(nev, {}).get("mod", KIFIZETES_SZAMLAS)
        sorok.append({
            "Közvetítő": nev,
            "Szint": kozv.get(nev, {}).get("szint", ""),
            "Kifizetés módja": mod,
            "Darab": len(sajat),
            "Saját volumen": float(sajat[OSSZEG].sum()),
            "Saját jutalék": int(sajat["Összeg"].sum()),
            "Felülíró jutalék": int(jut[jut["Szerep"] == SZEREP_FELULIRO]["Összeg"].sum()),
            "Volumen bónusz": int(s[s["Típus"] == TIPUS_BONUSZ]["Összeg"].sum()),
            "Storno": int(s[s["Típus"] == TIPUS_STORNO]["Összeg"].sum()),
            "Bruttó jutalék": brutto,
            **levonasok(brutto, mod, ado),
        })
    return pd.DataFrame(sorok, columns=OSSZESITO_OSZLOPOK)
