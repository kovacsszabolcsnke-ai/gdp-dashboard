# :earth_americas: GDP dashboard template

A simple Streamlit app showing the GDP of different countries in the world.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://gdp-dashboard-template.streamlit.app/)

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```

---

# 💰 Hitel jutalék számfejtés

Streamlit alkalmazás a folyósított hitelek utáni közvetítői jutalék havi számfejtéséhez.

```
pip install -r requirements.txt
streamlit run jutalek_app.py
```

## Mit számol

| Lépés | Szabály (a felületen állítható) |
|---|---|
| Bank jutalék | folyósított összeg × bank/termék szerinti %, opcionális Ft-os plafonnal |
| Felosztás | szintenkénti részesedés a bank jutalékból; a felettes **differenciális felülírót** kap (saját % − alatta kifizetett legmagasabb %) |
| Storno | a hónapban megszűnt (előtörlesztett, felmondott) hitel, ha a folyósítástól számított N hónapon belül szűnt meg → visszaterhelés %, arányosan minden érintettnél |
| Volumen bónusz | havi saját folyósított volumen sávjai szerint plusz %, a saját értékesítésű bank jutalékra |
| Levonások | *Megbízási*: költséghányad, SZJA, TB járulék (minimálbér 30%-a alatt nincs), munkáltatói szocho; *Számlás*: ÁFA (alapból 0%, tárgyi mentes) |
| Negatív egyenleg | ha a storno meghaladja a jutalékot, nincs kifizetés, az összeg *Átvitt tartozás*-ként jelenik meg |

## Bemenet

Excel vagy CSV (`;` vagy `,` elválasztó) az alábbi oszlopokkal – minta: `data/minta_hitelek.csv`:

`Szerződésszám; Ügyfél; Bank; Termék; Folyósított összeg; Folyósítás dátuma; Közvetítő; Megszűnés dátuma`

## Kimenet

* Teljes számfejtés Excelben (Összesítő, Cég, Tételek, Storno, Hibák lapok)
* Közvetítőnkénti elszámoló Excelben
* A beállítások JSON-ba menthetők és visszatölthetők

A számítási logika a `hitel_jutalek/szamitas.py` modulban van; tesztek: `python -m pytest tests`.

> Az alapértelmezett bankok, %-ok és közvetítők **példaadatok**. Az adó- és
> járulékkulcsokat (SZJA 15%, TB 18,5%, szocho 13%, 2026-os minimálbér) használat előtt ellenőrizze.
