# 📊 S&P 500 Radar & Portfolio Guard

Automatizovaný ranní analytický dashboard, akciový radar a hlídač portfolia postavený na strategii **Core & Satellite** s přísnou investiční disciplínou.

---

## 🎯 Hlavní investiční teze
* **Žádné nucené obchody:** Cílem není generovat nákupní tipy každý den. Je zcela v pořádku a žádoucí, pokud několik dní či týdnů systém neoznačí žádnou akcii k nákupu a oznámí, že trh je férově oceněn či překoupen.
* **Koš 1: CORE („Klidný přístav“, 85 %):**
  - Dlouhodobé držení stabilních gigantů (S&P 500).
  - Nízké zadlužení (`D/E <= 100 %`, banky posuzovány specificky), kladné a stabilní FCF, rozumná valuace (`P/E <= 28`).
  - Nákupní spouštěč: Zdravá sleva 5–20 % od maxima s ochranou proti padajícímu noži a podmínkou, že cena drží nad SMA 200.
* **Koš 2: SATELLITE („Akcelerátor“, 15 %):**
  - Růst a momentum (S&P 500 + S&P MidCap 400).
  - Růst tržeb (`YoY >= 15 %`), potvrzený uptrend (`Cena > SMA 50` i `SMA 200`), zdravé momentum (`Wilder's RSI 14` v pásmu 45–70).
* **3úrovňový audit portfolia:**
  - 🔴 **Červená vlajka (Core):** Záporné Free Cash Flow -> narušení fundamentu.
  - 🔴 **Červená vlajka (Satellite):** Pokles pod `SMA 200` -> okamžitý technický stop-loss.
  - 🟡 **Žlutá vlajka:** Extrémní valuace (`P/E > 45`) nebo propad > 25 % od maxima -> návrh na revizi či vybrání zisku.

---

## 🏗️ Architektura a optimalizace rychlosti
* **Dvoustupňový trychtýř (Funnel):** Celý trh (900+ akcií z S&P 500 a MidCap 400) se stáhne v dávkách za cca 15–25 sekund. Následně se fundamenty dotahují pouze pro relevantní kandidáty s lokální mezipamětí (TTL 24h).
* **Headless ranní skener (`scanner.py`):** Běží na pozadí před otevřením trhu (GitHub Actions nebo lokální plánovač), uloží výsledky do `data/radar_cache.json`.
* **Bleskový Streamlit dashboard (`app.py`):** Načte hotová data z mezipaměti za **0.05 sekundy** bez točícího se kolečka.
* **Datově podložená AI analýza:** Gemini 2.5 Flash s přísnou strukturou (3 katalyzátory, 3 rizika, výhled) a robustním kvantitativním fallbackem při chybě klíče či sítě.

---

## 🚀 Rychlý start lokálně

### 1. Klonování repozitáře a příprava prostředí
```bash
# Spuštění na Windows
run_windows.bat

# Nebo ručně v terminálu:
python -m venv venv
venv\Scripts\activate       # Na Linuxu/Macu: source venv/bin/activate
pip install -r requirements.txt
```

### 2. Nastavení API klíče
Vytvoř soubor `.env` (zkopíruj z `.env.example`):
```env
GEMINI_API_KEY=tvuj_api_klic_zde
```

### 3. Spuštění
```bash
# 1. Ranní sken na pozadí (celý S&P 500 + MidCap 400)
python scanner.py --mode full

# 2. Spuštění webového dashboardu
streamlit run app.py
```

---

## 🤖 Automatizace na GitHub Actions
V repozitáři je připraven workflow `.github/workflows/morning_radar.yml`:
1. V GitHub repozitáři přejdi do **Settings -> Secrets and variables -> Actions**.
2. Přidej Repository secret: `GEMINI_API_KEY`.
3. Sken běží automaticky každé pondělí až pátek v 6:00 SEČ a aktualizuje `data/radar_cache.json`.
