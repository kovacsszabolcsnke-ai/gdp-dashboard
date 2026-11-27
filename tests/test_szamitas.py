from datetime import date

import pandas as pd
import pytest

from hitel_jutalek import szamitas as sz
from hitel_jutalek.export import excel, kozvetito_elszamolo


def hitel(szam, osszeg, folyositas, kozvetito, bank="Bank A", termek="Lakáshitel", megszunes=None):
    return {
        sz.SZERZODES: szam, sz.UGYFEL: "X", sz.BANK: bank, sz.TERMEK: termek, sz.OSSZEG: osszeg,
        sz.FOLYOSITAS: folyositas, sz.KOZVETITO: kozvetito, sz.MEGSZUNES: megszunes,
    }


def cfg_bonusz_nelkul():
    c = sz.Beallitasok()
    c.bonusz = c.bonusz.iloc[0:0]
    return c


def test_differencialis_feluliro():
    # Bank A lakáshitel 1,2% → 30M * 1,2% = 360 000
    df = pd.DataFrame([hitel("1", 30_000_000, "2026-11-05", "Kiss Anna")])
    e = sz.szamfejtes(df, cfg_bonusz_nelkul(), 2026, 11)
    osszeg = dict(zip(e.tetelek["Kedvezményezett"], e.tetelek["Összeg"]))
    assert osszeg == {"Kiss Anna": 180_000, "Nagy Péter": 36_000, "Szabó Éva": 18_000}
    assert e.ceg["Bank jutalék bevétel"] == 360_000
    assert e.ceg["Cégnél maradó"] == 126_000


def test_plafon():
    # 62M * 1,2% = 744 000, plafon 600 000
    assert sz.bank_jutalek(62_000_000, 1.2, 600_000) == 600_000
    assert sz.bank_jutalek(62_000_000, 1.2, 0) == 744_000


def test_csoportvezeto_sajat_ertekesitese():
    df = pd.DataFrame([hitel("1", 10_000_000, "2026-11-05", "Nagy Péter")])
    e = sz.szamfejtes(df, cfg_bonusz_nelkul(), 2026, 11)
    osszeg = dict(zip(e.tetelek["Kedvezményezett"], e.tetelek["Összeg"]))
    assert osszeg == {"Nagy Péter": 72_000, "Szabó Éva": 6_000}


def test_storno_idoablak():
    assert sz.eltelt_honapok(date(2026, 7, 8), date(2026, 11, 11)) == 4
    assert sz.eltelt_honapok(date(2026, 3, 20), date(2026, 9, 19)) == 5
    c = sz.Beallitasok()
    assert sz.storno_szazalek(4, c) == 100
    assert sz.storno_szazalek(8, c) == 50
    assert sz.storno_szazalek(14, c) == 0


def test_storno_tetelek_es_negativ_egyenleg():
    # Júliusi folyósítás, novemberi megszűnés → 100% visszaterhelés
    df = pd.DataFrame([hitel("1", 30_000_000, "2026-07-08", "Kiss Anna", megszunes="2026-11-11")])
    e = sz.szamfejtes(df, cfg_bonusz_nelkul(), 2026, 11)
    assert set(e.tetelek["Típus"]) == {sz.TIPUS_STORNO}
    assert e.tetelek["Összeg"].sum() == -234_000
    anna = e.osszesito.set_index("Közvetítő").loc["Kiss Anna"]
    assert anna["Kifizetendő"] == 0 and anna["Átvitt tartozás"] == -180_000
    assert e.ceg["Bank storno"] == -360_000


def test_megbizasi_levonasok():
    ado = sz.alap_ado()
    l = sz.levonasok(200_000, sz.KIFIZETES_MEGBIZASI, ado)
    # jövedelem 180 000; SZJA 27 000; TB 33 300; szocho 23 400
    assert (l["SZJA"], l["TB járulék"], l["Munkáltatói szocho"], l["Kifizetendő"]) == (27_000, 33_300, 23_400, 139_700)
    # Minimálbér 30%-a alatt nincs TB járulék
    kicsi = sz.levonasok(50_000, sz.KIFIZETES_MEGBIZASI, ado)
    assert kicsi["TB járulék"] == 0 and kicsi["SZJA"] == 6_750


def test_volumen_bonusz():
    df = pd.DataFrame([hitel(str(i), 40_000_000, "2026-11-05", "Tóth Gábor", bank="Bank C") for i in range(3)])
    e = sz.szamfejtes(df, sz.Beallitasok(), 2026, 11)
    bonusz = e.tetelek[e.tetelek["Típus"] == sz.TIPUS_BONUSZ]
    # 120M volumen → 2%, saját bank jutalék 3 * 440 000
    assert bonusz["Összeg"].tolist() == [26_400]


def test_hibak():
    c = cfg_bonusz_nelkul()
    c.kozvetitok.loc[c.kozvetitok["Közvetítő"] == "Szabó Éva", "Felettes"] = "Kiss Anna"
    df = pd.DataFrame([
        hitel("1", 10_000_000, "2026-11-05", "Ismeretlen"),
        hitel("2", 10_000_000, "2026-11-05", "Kiss Anna", bank="Bank D"),
        hitel("3", 10_000_000, "2026-11-05", "Kiss Anna"),
        hitel("3", 10_000_000, "2026-11-05", "Kiss Anna"),
    ])
    e = sz.szamfejtes(df, c, 2026, 11)
    uzenetek = " | ".join(e.hibak["Hiba"])
    assert "Ismeretlen közvetítő" in uzenetek
    assert "Nincs bank jutalék" in uzenetek
    assert "Körkörös" in uzenetek
    assert "Ismétlődő" in uzenetek
    assert e.tetelek.empty


def test_hianyzo_oszlop():
    with pytest.raises(ValueError, match="Hiányzó oszlop"):
        sz.szamfejtes(pd.DataFrame([{"Bank": "x"}]), sz.Beallitasok(), 2026, 11)


def test_json_oda_vissza():
    c = sz.Beallitasok()
    c2 = sz.Beallitasok.from_json(c.to_json())
    pd.testing.assert_frame_equal(c.szintek, c2.szintek)
    assert c2.ado == c.ado


def test_minta_es_export():
    df = pd.read_csv("data/minta_hitelek.csv", sep=";")
    e = sz.szamfejtes(df, sz.Beallitasok(), 2026, 11)
    assert len(e.hibak) == 1  # Bank D-re nincs beállítás
    assert e.ceg["Bank jutalék bevétel"] + e.ceg["Bank storno"] - e.ceg["Közvetítőknek bruttó"] == e.ceg["Cégnél maradó"]
    assert excel(e, "2026-11")[:2] == b"PK"
    assert kozvetito_elszamolo(e, "Kiss Anna", "2026-11")[:2] == b"PK"


def test_datum_formatumok():
    for x in ("2026-11-05", "2026.11.05.", "2026. 11. 05.", pd.Timestamp("2026-11-05"), date(2026, 11, 5)):
        assert sz.datum(x) == date(2026, 11, 5)
    assert sz.datum("") is None and sz.datum(None) is None and sz.datum(float("nan")) is None
