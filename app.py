"""
Real Exchange Rate Explorer
---------------------------
A Streamlit app that pulls monthly CPI and exchange-rate data from the IMF
SDMX 3.0 API and computes the bilateral real exchange rate between two
countries (or the Euro area).

Definitions used throughout (matching the assignment):
    S(t)   = units of Country 2 currency per 1 unit of Country 1 currency
    P1, P2 = monthly CPI of Country 1 and Country 2
    RER(t) = S(t) * P1(t) / P2(t)
    RER*   = average of RER(t) over the valid months in the selected period
    Real index(t) = 100 * RER(t) / RER*

The IMF publishes exchange rates as local currency per US dollar (e_i), so
    S(t) = e2(t) / e1(t)
because (C2 per USD) / (C1 per USD) = C2 per C1.

Built for Python 3.12.
"""

from __future__ import annotations

import io
import math
import re
import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Real Exchange Rate Explorer",
    page_icon="💱",
    layout="wide",
    initial_sidebar_state="collapsed",
)

IMF_BASE = "https://api.imf.org/external/sdmx/3.0"
IMF_AGENCY = "IMF.STA"
FIRST_MONTH = pd.Period("1976-01", freq="M")

# Colors (also used in the CSS below)
INK = "#14213D"
MUTED = "#5C6B7A"
LINE = "#DDE3EA"
REAL = "#0E7C66"  # teal: real index
NOMINAL = "#B86E00"  # ochre: nominal rate

# ---------------------------------------------------------------------------
# Countries: ISO3 | ISO2 (for the flag) | name | currency code | currency name
# IMF member economies plus the Euro area (IMF code G163).
# Currency labels show today's currency and are only used for display.
# ---------------------------------------------------------------------------
_COUNTRY_TABLE = """
G163|EU|Euro area|EUR|euro
AFG|AF|Afghanistan|AFN|Afghan afghani
ALB|AL|Albania|ALL|Albanian lek
DZA|DZ|Algeria|DZD|Algerian dinar
AND|AD|Andorra|EUR|euro
AGO|AO|Angola|AOA|Angolan kwanza
ATG|AG|Antigua and Barbuda|XCD|East Caribbean dollar
ARG|AR|Argentina|ARS|Argentine peso
ARM|AM|Armenia|AMD|Armenian dram
ABW|AW|Aruba|AWG|Aruban florin
AUS|AU|Australia|AUD|Australian dollar
AUT|AT|Austria|EUR|euro
AZE|AZ|Azerbaijan|AZN|Azerbaijani manat
BHS|BS|Bahamas|BSD|Bahamian dollar
BHR|BH|Bahrain|BHD|Bahraini dinar
BGD|BD|Bangladesh|BDT|Bangladeshi taka
BRB|BB|Barbados|BBD|Barbados dollar
BLR|BY|Belarus|BYN|Belarusian ruble
BEL|BE|Belgium|EUR|euro
BLZ|BZ|Belize|BZD|Belize dollar
BEN|BJ|Benin|XOF|West African CFA franc
BTN|BT|Bhutan|BTN|Bhutanese ngultrum
BOL|BO|Bolivia|BOB|boliviano
BIH|BA|Bosnia and Herzegovina|BAM|convertible mark
BWA|BW|Botswana|BWP|Botswana pula
BRA|BR|Brazil|BRL|Brazilian real
BRN|BN|Brunei Darussalam|BND|Brunei dollar
BGR|BG|Bulgaria|BGN|Bulgarian lev
BFA|BF|Burkina Faso|XOF|West African CFA franc
BDI|BI|Burundi|BIF|Burundi franc
CPV|CV|Cabo Verde|CVE|Cabo Verde escudo
KHM|KH|Cambodia|KHR|Cambodian riel
CMR|CM|Cameroon|XAF|Central African CFA franc
CAN|CA|Canada|CAD|Canadian dollar
CAF|CF|Central African Republic|XAF|Central African CFA franc
TCD|TD|Chad|XAF|Central African CFA franc
CHL|CL|Chile|CLP|Chilean peso
CHN|CN|China|CNY|Chinese yuan
COL|CO|Colombia|COP|Colombian peso
COM|KM|Comoros|KMF|Comorian franc
COD|CD|Congo, Democratic Republic|CDF|Congolese franc
COG|CG|Congo, Republic|XAF|Central African CFA franc
CRI|CR|Costa Rica|CRC|Costa Rican colon
CIV|CI|Cote d'Ivoire|XOF|West African CFA franc
HRV|HR|Croatia|EUR|euro
CYP|CY|Cyprus|EUR|euro
CZE|CZ|Czech Republic|CZK|Czech koruna
DNK|DK|Denmark|DKK|Danish krone
DJI|DJ|Djibouti|DJF|Djiboutian franc
DMA|DM|Dominica|XCD|East Caribbean dollar
DOM|DO|Dominican Republic|DOP|Dominican peso
ECU|EC|Ecuador|USD|US dollar
EGY|EG|Egypt|EGP|Egyptian pound
SLV|SV|El Salvador|USD|US dollar
GNQ|GQ|Equatorial Guinea|XAF|Central African CFA franc
ERI|ER|Eritrea|ERN|Eritrean nakfa
EST|EE|Estonia|EUR|euro
SWZ|SZ|Eswatini|SZL|Swazi lilangeni
ETH|ET|Ethiopia|ETB|Ethiopian birr
FJI|FJ|Fiji|FJD|Fiji dollar
FIN|FI|Finland|EUR|euro
FRA|FR|France|EUR|euro
GAB|GA|Gabon|XAF|Central African CFA franc
GMB|GM|Gambia|GMD|Gambian dalasi
GEO|GE|Georgia|GEL|Georgian lari
DEU|DE|Germany|EUR|euro
GHA|GH|Ghana|GHS|Ghanaian cedi
GRC|GR|Greece|EUR|euro
GRD|GD|Grenada|XCD|East Caribbean dollar
GTM|GT|Guatemala|GTQ|Guatemalan quetzal
GIN|GN|Guinea|GNF|Guinean franc
GNB|GW|Guinea-Bissau|XOF|West African CFA franc
GUY|GY|Guyana|GYD|Guyanese dollar
HTI|HT|Haiti|HTG|Haitian gourde
HND|HN|Honduras|HNL|Honduran lempira
HKG|HK|Hong Kong SAR|HKD|Hong Kong dollar
HUN|HU|Hungary|HUF|Hungarian forint
ISL|IS|Iceland|ISK|Icelandic krona
IND|IN|India|INR|Indian rupee
IDN|ID|Indonesia|IDR|Indonesian rupiah
IRN|IR|Iran|IRR|Iranian rial
IRQ|IQ|Iraq|IQD|Iraqi dinar
IRL|IE|Ireland|EUR|euro
ISR|IL|Israel|ILS|Israeli shekel
ITA|IT|Italy|EUR|euro
JAM|JM|Jamaica|JMD|Jamaican dollar
JPN|JP|Japan|JPY|Japanese yen
JOR|JO|Jordan|JOD|Jordanian dinar
KAZ|KZ|Kazakhstan|KZT|Kazakhstani tenge
KEN|KE|Kenya|KES|Kenyan shilling
KIR|KI|Kiribati|AUD|Australian dollar
KOR|KR|South Korea (Korea, Rep.)|KRW|South Korean won
KWT|KW|Kuwait|KWD|Kuwaiti dinar
KGZ|KG|Kyrgyz Republic|KGS|Kyrgyzstani som
LAO|LA|Lao P.D.R.|LAK|Lao kip
LVA|LV|Latvia|EUR|euro
LBN|LB|Lebanon|LBP|Lebanese pound
LSO|LS|Lesotho|LSL|Lesotho loti
LBR|LR|Liberia|LRD|Liberian dollar
LBY|LY|Libya|LYD|Libyan dinar
LIE|LI|Liechtenstein|CHF|Swiss franc
LTU|LT|Lithuania|EUR|euro
LUX|LU|Luxembourg|EUR|euro
MAC|MO|Macao SAR|MOP|Macanese pataca
MDG|MG|Madagascar|MGA|Malagasy ariary
MWI|MW|Malawi|MWK|Malawian kwacha
MYS|MY|Malaysia|MYR|Malaysian ringgit
MDV|MV|Maldives|MVR|Maldivian rufiyaa
MLI|ML|Mali|XOF|West African CFA franc
MLT|MT|Malta|EUR|euro
MHL|MH|Marshall Islands|USD|US dollar
MRT|MR|Mauritania|MRU|Mauritanian ouguiya
MUS|MU|Mauritius|MUR|Mauritian rupee
MEX|MX|Mexico|MXN|Mexican peso
FSM|FM|Micronesia|USD|US dollar
MDA|MD|Moldova|MDL|Moldovan leu
MNG|MN|Mongolia|MNT|Mongolian togrog
MNE|ME|Montenegro|EUR|euro
MAR|MA|Morocco|MAD|Moroccan dirham
MOZ|MZ|Mozambique|MZN|Mozambican metical
MMR|MM|Myanmar|MMK|Myanmar kyat
NAM|NA|Namibia|NAD|Namibian dollar
NRU|NR|Nauru|AUD|Australian dollar
NPL|NP|Nepal|NPR|Nepalese rupee
NLD|NL|Netherlands|EUR|euro
NZL|NZ|New Zealand|NZD|New Zealand dollar
NIC|NI|Nicaragua|NIO|Nicaraguan cordoba
NER|NE|Niger|XOF|West African CFA franc
NGA|NG|Nigeria|NGN|Nigerian naira
MKD|MK|North Macedonia|MKD|Macedonian denar
NOR|NO|Norway|NOK|Norwegian krone
OMN|OM|Oman|OMR|Omani rial
PAK|PK|Pakistan|PKR|Pakistani rupee
PLW|PW|Palau|USD|US dollar
PAN|PA|Panama|PAB|Panamanian balboa
PNG|PG|Papua New Guinea|PGK|Papua New Guinean kina
PRY|PY|Paraguay|PYG|Paraguayan guarani
PER|PE|Peru|PEN|Peruvian sol
PHL|PH|Philippines|PHP|Philippine peso
POL|PL|Poland|PLN|Polish zloty
PRT|PT|Portugal|EUR|euro
QAT|QA|Qatar|QAR|Qatari riyal
ROU|RO|Romania|RON|Romanian leu
RUS|RU|Russia|RUB|Russian ruble
RWA|RW|Rwanda|RWF|Rwandan franc
KNA|KN|St. Kitts and Nevis|XCD|East Caribbean dollar
LCA|LC|St. Lucia|XCD|East Caribbean dollar
VCT|VC|St. Vincent and the Grenadines|XCD|East Caribbean dollar
WSM|WS|Samoa|WST|Samoan tala
SMR|SM|San Marino|EUR|euro
STP|ST|Sao Tome and Principe|STN|Sao Tome dobra
SAU|SA|Saudi Arabia|SAR|Saudi riyal
SEN|SN|Senegal|XOF|West African CFA franc
SRB|RS|Serbia|RSD|Serbian dinar
SYC|SC|Seychelles|SCR|Seychelles rupee
SLE|SL|Sierra Leone|SLE|Sierra Leonean leone
SGP|SG|Singapore|SGD|Singapore dollar
SVK|SK|Slovak Republic|EUR|euro
SVN|SI|Slovenia|EUR|euro
SLB|SB|Solomon Islands|SBD|Solomon Islands dollar
SOM|SO|Somalia|SOS|Somali shilling
ZAF|ZA|South Africa|ZAR|South African rand
SSD|SS|South Sudan|SSP|South Sudanese pound
ESP|ES|Spain|EUR|euro
LKA|LK|Sri Lanka|LKR|Sri Lankan rupee
SDN|SD|Sudan|SDG|Sudanese pound
SUR|SR|Suriname|SRD|Surinamese dollar
SWE|SE|Sweden|SEK|Swedish krona
CHE|CH|Switzerland|CHF|Swiss franc
SYR|SY|Syria|SYP|Syrian pound
TJK|TJ|Tajikistan|TJS|Tajikistani somoni
TZA|TZ|Tanzania|TZS|Tanzanian shilling
THA|TH|Thailand|THB|Thai baht
TLS|TL|Timor-Leste|USD|US dollar
TGO|TG|Togo|XOF|West African CFA franc
TON|TO|Tonga|TOP|Tongan paanga
TTO|TT|Trinidad and Tobago|TTD|Trinidad and Tobago dollar
TUN|TN|Tunisia|TND|Tunisian dinar
TUR|TR|Turkiye|TRY|Turkish lira
TKM|TM|Turkmenistan|TMT|Turkmenistan manat
TUV|TV|Tuvalu|AUD|Australian dollar
UGA|UG|Uganda|UGX|Ugandan shilling
UKR|UA|Ukraine|UAH|Ukrainian hryvnia
ARE|AE|United Arab Emirates|AED|UAE dirham
GBR|GB|United Kingdom|GBP|British pound
USA|US|United States|USD|US dollar
URY|UY|Uruguay|UYU|Uruguayan peso
UZB|UZ|Uzbekistan|UZS|Uzbekistani som
VUT|VU|Vanuatu|VUV|Vanuatu vatu
VEN|VE|Venezuela|VES|Venezuelan bolivar
VNM|VN|Vietnam|VND|Vietnamese dong
YEM|YE|Yemen|YER|Yemeni rial
ZMB|ZM|Zambia|ZMW|Zambian kwacha
ZWE|ZW|Zimbabwe|ZWG|Zimbabwe gold
"""


def _load_countries() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for line in _COUNTRY_TABLE.strip().splitlines():
        iso3, iso2, name, cur, cur_name = [p.strip() for p in line.split("|")]
        out[iso3] = {"iso2": iso2, "name": name, "cur": cur, "cur_name": cur_name}
    return out


COUNTRIES = _load_countries()
# Euro area first, then alphabetical by name
COUNTRY_CODES = ["G163"] + sorted(
    [c for c in COUNTRIES if c != "G163"], key=lambda c: COUNTRIES[c]["name"]
)


def flag(iso2: str) -> str:
    """Turn a 2-letter code into a flag emoji (EU gives the EU flag)."""
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in iso2.upper())


def country_label(iso3: str) -> str:
    c = COUNTRIES[iso3]
    return f"{flag(c['iso2'])}  {c['name']}  ({c['cur']})"


def short_name(iso3: str) -> str:
    name = COUNTRIES[iso3]["name"]
    return name.split(" (")[0]


# ---------------------------------------------------------------------------
# Number formatting
# ---------------------------------------------------------------------------
def fmt(x: float | None, sig: int = 4) -> str:
    """Format a number with roughly `sig` significant digits, never in
    scientific notation, with thousands separators."""
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "n/a"
    ax = abs(x)
    if ax == 0:
        return "0"
    decimals = max(0, sig - 1 - int(math.floor(math.log10(ax))))
    return f"{x:,.{decimals}f}"


_NO_PLURAL = {"won", "yen", "yuan", "baht", "rand", "kip", "riel", "rupiah", "naira",
              "som", "tenge", "dong", "kyat", "togrog", "vatu", "tala", "paanga",
              "lilangeni", "loti", "ngultrum", "rufiyaa", "kina", "gold"}


def plural(cur_name: str, amount: float) -> str:
    """'Indian rupee' -> 'Indian rupees'; 'South Korean won' stays the same."""
    if abs(amount - 1.0) < 1e-12:
        return cur_name
    last = cur_name.split()[-1].lower()
    if last in _NO_PLURAL or last.endswith("s"):
        return cur_name
    return cur_name + "s"


def month_label(p: pd.Period) -> str:
    return p.strftime("%b %Y")


# ---------------------------------------------------------------------------
# IMF data access
# ---------------------------------------------------------------------------
class IMFError(Exception):
    """Raised when the IMF API cannot be reached or returns something odd."""


_PERIOD_RE = re.compile(r"^(\d{4})-?M?(\d{1,2})$")


def parse_period(value: str) -> pd.Period | None:
    """IMF monthly periods look like '1976-M01' (sometimes '1976-01')."""
    m = _PERIOD_RE.match(str(value).strip())
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        return None
    return pd.Period(year=year, month=month, freq="M")


def _code(v):
    if isinstance(v, dict):
        return v.get("id", v.get("value", v.get("code")))
    return v


def parse_sdmx_json(payload: dict) -> pd.Series:
    """Convert an SDMX-JSON (2.0, as served by the IMF 3.0 API) response
    into a monthly pandas Series indexed by Period."""
    data = payload.get("data", payload)
    structures = data.get("structures") or data.get("structure")
    if isinstance(structures, list):
        structures = structures[0] if structures else {}
    structures = structures or {}

    datasets = data.get("dataSets") or []
    if not datasets:
        return pd.Series(dtype="float64")
    ds0 = datasets[0]

    obs_dims = (structures.get("dimensions") or {}).get("observation") or []
    time_dim = next(
        (d for d in obs_dims if isinstance(d, dict) and d.get("id") == "TIME_PERIOD"),
        obs_dims[0] if obs_dims else {"values": []},
    )
    time_values = [_code(v) for v in (time_dim.get("values") or [])]

    values: dict[pd.Period, float] = {}
    for sobj in (ds0.get("series") or {}).values():
        for tpos, obs in (sobj.get("observations") or {}).items():
            try:
                period = parse_period(time_values[int(tpos)])
            except (ValueError, IndexError):
                continue
            raw = obs[0] if isinstance(obs, list) and obs else obs
            try:
                val = float(raw)
            except (TypeError, ValueError):
                continue
            if period is not None and np.isfinite(val):
                values[period] = val

    if not values:
        return pd.Series(dtype="float64")
    return pd.Series(values, dtype="float64").sort_index()


def parse_sdmx_csv(text: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text))
    if "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
        return pd.Series(dtype="float64")
    periods = df["TIME_PERIOD"].map(parse_period)
    vals = pd.to_numeric(df["OBS_VALUE"], errors="coerce")
    s = pd.Series(vals.values, index=periods.values).dropna()
    s = s[[p is not None for p in s.index]]
    return s.groupby(level=0).last().sort_index().astype("float64")


@st.cache_data(ttl=60 * 60 * 12, show_spinner=False)
def fetch_imf_series(dataflow: str, key: str) -> pd.Series:
    """Download one monthly series from the IMF SDMX 3.0 API.

    Returns an empty Series when the IMF has no data for this key.
    Raises IMFError when the API cannot be reached.
    """
    url = f"{IMF_BASE}/data/dataflow/{IMF_AGENCY}/{dataflow}/+/{key}"
    params = {"dimensionAtObservation": "TIME_PERIOD"}
    formats = [
        ("application/json", "json"),
        ("application/vnd.sdmx.data+json;version=2.0.0", "json"),
        ("application/vnd.sdmx.data+csv;version=2.0.0", "csv"),
    ]
    last_problem = "no response"

    for accept, kind in formats:
        headers = {
            "Accept": accept,
            "User-Agent": "real-exchange-rate-app/1.0 (Streamlit; educational use)",
        }
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, headers=headers, timeout=45)
            except requests.RequestException as exc:
                last_problem = f"network error: {exc}"
                time.sleep(1.5 * (attempt + 1))
                continue

            if r.status_code == 404:
                return pd.Series(dtype="float64")  # IMF: no data for this key
            if r.status_code in (429, 500, 502, 503, 504):
                last_problem = f"HTTP {r.status_code} from IMF"
                time.sleep(2.0 * (attempt + 1))
                continue
            if r.status_code in (406, 415):
                last_problem = f"HTTP {r.status_code}: format {accept} not accepted"
                break  # try the next format
            if r.status_code != 200:
                raise IMFError(f"HTTP {r.status_code} for {key}: {r.text[:300]}")

            try:
                if kind == "json":
                    return parse_sdmx_json(r.json())
                return parse_sdmx_csv(r.text)
            except ValueError as exc:
                last_problem = f"could not read {accept} response: {exc}"
                break  # try the next format

    raise IMFError(f"Could not download {dataflow} {key} ({last_problem}).")


def cpi_key(iso3: str) -> str:
    return f"{iso3}.CPI._T.IX.M"


def fx_key(iso3: str) -> str:
    return f"{iso3}.XDC_USD.PA_RT.M"


def load_pair(c1: str, c2: str) -> tuple[pd.DataFrame, dict]:
    """Fetch CPI and FX for both countries and compute S and RER for every
    month from Jan 1976 onwards."""
    raw = {
        "P1": fetch_imf_series("CPI", cpi_key(c1)),
        "P2": fetch_imf_series("CPI", cpi_key(c2)),
        # The IMF does not publish a US dollar per US dollar series, so the
        # United States' rate is exactly 1 by definition.
        "e1": None if c1 == "USA" else fetch_imf_series("ER", fx_key(c1)),
        "e2": None if c2 == "USA" else fetch_imf_series("ER", fx_key(c2)),
    }

    last_obs = [s.index.max() for s in raw.values() if s is not None and not s.empty]
    end = max(last_obs) if last_obs else FIRST_MONTH
    months = pd.period_range(FIRST_MONTH, max(end, FIRST_MONTH), freq="M")

    df = pd.DataFrame(index=months)
    for col, s in raw.items():
        if s is None:
            df[col] = 1.0
        else:
            df[col] = s.reindex(months)

    df["S"] = df["e2"] / df["e1"]
    df["RER"] = df["S"] * df["P1"] / df["P2"]
    df["valid"] = (
        df[["e1", "e2", "P1", "P2"]].notna().all(axis=1)
        & (df[["e1", "e2", "P1", "P2"]] > 0).all(axis=1)
    )
    df.loc[~df["valid"], ["S", "RER"]] = np.nan

    coverage = {}
    names = {
        "P1": f"CPI, {short_name(c1)}",
        "P2": f"CPI, {short_name(c2)}",
        "e1": f"{COUNTRIES[c1]['cur']} per USD",
        "e2": f"{COUNTRIES[c2]['cur']} per USD",
    }
    keys = {"P1": cpi_key(c1), "P2": cpi_key(c2), "e1": fx_key(c1), "e2": fx_key(c2)}
    for col, s in raw.items():
        if s is None:
            coverage[col] = {
                "Series": names[col],
                "IMF key": "(none: USD per USD is 1)",
                "First month": "always",
                "Last month": "always",
                "Months since Jan 1976": len(months),
            }
            continue
        s76 = s[s.index >= FIRST_MONTH]
        coverage[col] = {
            "Series": names[col],
            "IMF key": keys[col],
            "First month": month_label(s76.index.min()) if not s76.empty else "no data",
            "Last month": month_label(s76.index.max()) if not s76.empty else "no data",
            "Months since Jan 1976": int(len(s76)),
        }
    return df, coverage


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

html, body, [data-testid="stAppViewContainer"], .stMarkdown, button, input, select, textarea {{
  font-family: 'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif;
}}
[data-testid="stAppViewContainer"] {{ background: #F5F7F9; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ max-width: 1160px; padding-top: 2.2rem; padding-bottom: 4rem; }}

h1.app-title {{
  font-size: 2.35rem; line-height: 1.15; font-weight: 600; letter-spacing: -0.02em;
  color: {INK}; margin: 0 0 .35rem 0; padding: 0;
}}
p.app-sub {{ color: {MUTED}; font-size: 1.05rem; max-width: 62ch; margin: 0 0 1.6rem 0; }}

.reading {{
  background: #FFFFFF; border: 1px solid {LINE}; border-radius: 16px;
  padding: 1.6rem 1.8rem 1.4rem; margin: .6rem 0 1.1rem 0;
}}
.reading .lead {{
  font-size: 1.6rem; line-height: 1.35; font-weight: 500; color: {INK};
  letter-spacing: -0.01em; max-width: 60ch; margin: 0;
}}
.reading .lead b {{ font-weight: 700; font-variant-numeric: tabular-nums; }}
.reading .lead .nom {{ color: {NOMINAL}; }}
.reading .lead .real {{ color: {REAL}; }}
.reading .follow {{ color: {MUTED}; font-size: 1.02rem; line-height: 1.55; max-width: 72ch; margin: .8rem 0 0 0; }}

.stats {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .8rem; margin-bottom: .6rem; }}
.stat {{ background: #FFFFFF; border: 1px solid {LINE}; border-radius: 12px; padding: .9rem 1rem .85rem; }}
.stat-label {{ color: {MUTED}; font-size: .86rem; }}
.stat-value {{ color: {INK}; font-size: 1.7rem; font-weight: 600; font-variant-numeric: tabular-nums; margin: .15rem 0 .1rem; }}
.stat-note {{ color: {MUTED}; font-size: .84rem; line-height: 1.35; }}
@media (max-width: 900px) {{ .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}

[data-testid="stMetric"] {{
  background: #FFFFFF; border: 1px solid {LINE}; border-radius: 12px; padding: .85rem 1rem .75rem;
}}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: .88rem; }}
[data-testid="stMetricValue"] {{ font-variant-numeric: tabular-nums; color: {INK}; font-weight: 600; font-size: 1.65rem; }}

.formula {{
  background: #FFFFFF; border: 1px solid {LINE}; border-radius: 12px;
  padding: 1rem 1.2rem; margin: .2rem 0 .8rem 0; color: {INK};
}}
.formula ol {{ margin: 0; padding-left: 1.2rem; }}
.formula li {{ margin: .55rem 0; line-height: 1.5; }}
.formula .eq {{ font-variant-numeric: tabular-nums; }}
.formula .res {{ font-weight: 700; }}
.formula .why {{ color: {MUTED}; font-size: .92rem; display: block; }}

.note {{ color: {MUTED}; font-size: .92rem; line-height: 1.5; }}
.legend-key {{ display:inline-block; width: 14px; height: 3px; border-radius: 2px; vertical-align: middle; margin-right: 6px; }}

[data-testid="stDownloadButton"] button {{ border-radius: 10px; font-weight: 600; }}
button:focus-visible {{ outline: 3px solid #7FB3FF !important; outline-offset: 2px; }}
footer {{ visibility: hidden; }}

@media (max-width: 640px) {{
  h1.app-title {{ font-size: 1.8rem; }}
  .reading {{ padding: 1.1rem 1.1rem 1rem; }}
  .reading .lead {{ font-size: 1.25rem; }}
}}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Header and country pickers
# ---------------------------------------------------------------------------
st.markdown(
    '<h1 class="app-title">Real exchange rate explorer</h1>'
    '<p class="app-sub">Compare two currencies in plain money terms and after '
    "adjusting for inflation, using monthly IMF data from January 1976 onwards.</p>",
    unsafe_allow_html=True,
)

if "c1" not in st.session_state:
    st.session_state["c1"] = "GBR"
if "c2" not in st.session_state:
    st.session_state["c2"] = "USA"


def swap_countries() -> None:
    st.session_state["c1"], st.session_state["c2"] = (
        st.session_state["c2"],
        st.session_state["c1"],
    )


col_a, col_swap, col_b = st.columns([10, 1, 10], vertical_alignment="bottom")
with col_a:
    st.selectbox(
        "Country 1 (the currency you are pricing)",
        COUNTRY_CODES,
        key="c1",
        format_func=country_label,
    )
with col_swap:
    st.button("⇄", on_click=swap_countries, help="Swap Country 1 and Country 2",
              width="stretch")
with col_b:
    st.selectbox(
        "Country 2 (the currency you are pricing it in)",
        COUNTRY_CODES,
        key="c2",
        format_func=country_label,
    )

c1, c2 = st.session_state["c1"], st.session_state["c2"]
cur1, cur2 = COUNTRIES[c1]["cur"], COUNTRIES[c2]["cur"]
curname1, curname2 = COUNTRIES[c1]["cur_name"], COUNTRIES[c2]["cur_name"]

if c1 == c2:
    st.info("Pick two different countries to compare.")
    st.stop()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
try:
    with st.spinner(f"Downloading IMF data for {short_name(c1)} and {short_name(c2)}..."):
        df, coverage = load_pair(c1, c2)
except IMFError as exc:
    st.error(
        "The IMF data service did not respond properly, so nothing could be "
        "calculated. This is usually temporary. Wait a minute and press "
        "**Try again**."
    )
    with st.expander("Technical details"):
        st.code(str(exc))
    if st.button("Try again", type="primary"):
        st.cache_data.clear()
        st.rerun()
    st.stop()

valid_months = df.index[df["valid"]]
if len(valid_months) == 0:
    st.warning(
        f"The IMF has no months where all four series overlap for "
        f"{short_name(c1)} and {short_name(c2)} since January 1976, so the real "
        "exchange rate cannot be calculated. The table below shows which series "
        "are missing. Try a different pair."
    )
    st.dataframe(pd.DataFrame(coverage.values()), hide_index=True, width="stretch")
    st.stop()

# ---------------------------------------------------------------------------
# Sample period
# ---------------------------------------------------------------------------
month_options = list(valid_months)
range_key = f"range_{c1}_{c2}"
start_m, end_m = st.select_slider(
    "Sample period (RER* is the average over these months)",
    options=month_options,
    value=(month_options[0], month_options[-1]),
    format_func=month_label,
    key=range_key,
)
if start_m > end_m:
    start_m, end_m = end_m, start_m

sample = df.loc[start_m:end_m].copy()
valid = sample["valid"]
n_valid = int(valid.sum())
rer_star = float(sample.loc[valid, "RER"].mean())
sample["RER_star"] = rer_star
sample["Real_index"] = 100.0 * sample["RER"] / rer_star

first_row = sample.loc[valid].iloc[0]
last_row = sample.loc[valid].iloc[-1]
first_m = sample.index[valid][0]
last_m = sample.index[valid][-1]

# ---------------------------------------------------------------------------
# Plain-language reading
# ---------------------------------------------------------------------------
idx_last = float(last_row["Real_index"])
gap = idx_last - 100.0
direction = "stronger" if gap >= 0 else "weaker"
nominal_change = (last_row["S"] / first_row["S"] - 1.0) * 100.0
real_change = (last_row["Real_index"] / first_row["Real_index"] - 1.0) * 100.0


def change_words(pct: float) -> str:
    if abs(pct) < 0.05:
        return "stayed about the same"
    return f"{'rose' if pct > 0 else 'fell'} {abs(pct):,.1f}%"


lead = (
    f"In {month_label(last_m)}, 1 {curname1} bought "
    f'<b class="nom">{fmt(last_row["S"])} {plural(curname2, float(last_row["S"]))}</b>. '
    f"Adjusted for inflation in both countries, the {curname1} was "
    f'<b class="real">{abs(gap):,.1f}% {direction}</b> than its average for the period.'
)
follow = (
    f"Between {month_label(first_m)} and {month_label(last_m)}, the nominal rate "
    f"({cur2} per {cur1}) {change_words(nominal_change)}, while the real index "
    f"{change_words(real_change)}. The difference between the two is inflation: "
    f"it shows how much of the currency move was offset (or amplified) by price "
    f"changes in {short_name(c1)} versus {short_name(c2)}."
)
st.markdown(
    f'<div class="reading"><p class="lead">{lead}</p><p class="follow">{follow}</p></div>',
    unsafe_allow_html=True,
)

def stat_card(label: str, value: str, note: str, tip: str = "") -> str:
    title = f' title="{tip}"' if tip else ""
    return (f'<div class="stat"{title}><div class="stat-label">{label}</div>'
            f'<div class="stat-value">{value}</div><div class="stat-note">{note}</div></div>')


gap_note = f"{gap:+,.1f} points vs the period average of 100"
cards = "".join([
    stat_card(f"Nominal rate, {month_label(last_m)}", fmt(last_row["S"]),
              f"{cur2} per 1 {cur1}", "S(t) = e2 / e1"),
    stat_card(f"Real index, {month_label(last_m)}", f"{idx_last:,.1f}", gap_note,
              "100 x RER(t) / RER*"),
    stat_card("RER*, the sample average", fmt(rer_star, 5),
              "Average of S x P1 / P2 over valid months", "Recalculated when the dates change"),
    stat_card("Valid months", f"{n_valid:,}",
              f"of {len(sample):,} months in the period", "Months where all four IMF series exist"),
])
st.markdown(f'<div class="stats">{cards}</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------
st.write("")
ctl_left, ctl_right = st.columns([3, 2], vertical_alignment="bottom")
with ctl_left:
    view = st.segmented_control(
        "Chart view",
        ["Real", "Nominal", "Both"],
        default="Both",
        key="view",
    ) or "Both"


def build_csv(sample: pd.DataFrame) -> bytes:
    out = pd.DataFrame(
        {
            "Month": [p.strftime("%Y-%m") for p in sample.index],
            "Country_1": c1,
            "Country_2": c2,
            f"e1_{cur1}_per_USD": sample["e1"].values,
            f"e2_{cur2}_per_USD": sample["e2"].values,
            f"S_{cur2}_per_{cur1}": sample["S"].values,
            f"P1_CPI_{c1}": sample["P1"].values,
            f"P2_CPI_{c2}": sample["P2"].values,
            "RER": sample["RER"].values,
            "Valid_month": sample["valid"].values,
            "RER_star": sample["RER_star"].values,
            "Real_index": sample["Real_index"].values,
        }
    )
    return out.to_csv(index=False, float_format="%.10g").encode("utf-8")


csv_name = f"rer_{c1}_{c2}_{start_m.strftime('%Y-%m')}_to_{end_m.strftime('%Y-%m')}.csv"
with ctl_right:
    st.download_button(
        f"Download CSV ({len(sample):,} months)",
        data=build_csv(sample),
        file_name=csv_name,
        mime="text/csv",
        type="primary",
        width="stretch",
        help="All observations and calculations for the selected period",
    )

x = sample.index.to_timestamp()
real_trace = go.Scatter(
    x=x, y=sample["Real_index"], name="Real index (left)" if view == "Both" else "Real index",
    mode="lines", line=dict(color=REAL, width=2.4),
    hovertemplate="Real index: %{y:,.2f}<extra></extra>", connectgaps=False,
)
nom_trace = go.Scatter(
    x=x, y=sample["S"], name=f"Nominal S, {cur2} per {cur1}" + (" (right)" if view == "Both" else ""),
    mode="lines", line=dict(color=NOMINAL, width=2.0),
    hovertemplate=f"S: %{{y:,.4g}} {cur2} per {cur1}<extra></extra>", connectgaps=False,
)

fig = make_subplots(specs=[[{"secondary_y": view == "Both"}]])
if view in ("Real", "Both"):
    fig.add_trace(real_trace, secondary_y=False)
    fig.add_hline(y=100, line=dict(color=REAL, width=1, dash="dot"), opacity=0.6,
                  annotation_text="period average = 100", annotation_position="top left",
                  annotation_font=dict(color=REAL, size=12))
if view == "Nominal":
    fig.add_trace(nom_trace, secondary_y=False)
if view == "Both":
    fig.add_trace(nom_trace, secondary_y=True)

axis_font = dict(family="IBM Plex Sans, sans-serif", size=12, color=MUTED)
fig.update_layout(
    height=470,
    margin=dict(l=10, r=10, t=30, b=10),
    paper_bgcolor="#FFFFFF",
    plot_bgcolor="#FFFFFF",
    font=dict(family="IBM Plex Sans, sans-serif", color=INK, size=13),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
)
fig.update_xaxes(showgrid=False, linecolor=LINE, tickfont=axis_font)
if view == "Real":
    fig.update_yaxes(title_text="Real index (average = 100)", gridcolor="#EEF1F4",
                     title_font=dict(color=REAL), tickfont=axis_font, zeroline=False)
elif view == "Nominal":
    fig.update_yaxes(title_text=f"{cur2} per 1 {cur1}", gridcolor="#EEF1F4",
                     title_font=dict(color=NOMINAL), tickfont=axis_font, zeroline=False)
else:
    fig.update_yaxes(title_text="Real index (average = 100)", secondary_y=False,
                     gridcolor="#EEF1F4", title_font=dict(color=REAL),
                     tickfont=dict(family=axis_font["family"], size=12, color=REAL), zeroline=False)
    fig.update_yaxes(title_text=f"Nominal S: {cur2} per 1 {cur1}", secondary_y=True,
                     showgrid=False, tickmode="auto", nticks=6, tickformat=",.4~g", title_font=dict(color=NOMINAL),
                     tickfont=dict(family=axis_font["family"], size=12, color=NOMINAL), zeroline=False)

with st.container(border=True):
    st.plotly_chart(fig, width="stretch",
                    config={"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]})

st.markdown(
    f'<p class="note">Reading the chart: when the <span style="color:{REAL};font-weight:600">real index</span> '
    f"is above 100, goods in {short_name(c1)} cost more, measured in {short_name(c2)} goods, than they "
    f"did on average over the period, so the {curname1} is strong in real terms. The "
    f'<span style="color:{NOMINAL};font-weight:600">nominal rate</span> is shown in actual currency units, '
    f"not normalized.</p>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Details
# ---------------------------------------------------------------------------
st.write("")
tab_math, tab_data, tab_cov, tab_about = st.tabs(
    ["Check the math", "Data table", "Data coverage", "Method and sources"]
)

with tab_math:
    st.markdown(
        "Pick any month to see each step of the calculation with the actual IMF numbers. "
        "You can redo these steps by hand from the downloaded CSV."
    )
    valid_in_sample = list(sample.index[valid])
    chosen = st.selectbox(
        "Month to verify",
        valid_in_sample[::-1],
        format_func=month_label,
        key=f"verify_{c1}_{c2}",
    )
    r = sample.loc[chosen]
    e1_txt = "1 (by definition)" if c1 == "USA" else fmt(r["e1"], 6)
    e2_txt = "1 (by definition)" if c2 == "USA" else fmt(r["e2"], 6)
    st.markdown(
        f"""
<div class="formula"><ol>
<li><span class="eq">S = e2 / e1 = {e2_txt} {cur2} per USD / {e1_txt} {cur1} per USD
 = <span class="res">{fmt(r['S'], 6)} {cur2} per {cur1}</span></span>
 <span class="why">The IMF quotes every currency per US dollar, so dividing the two cancels out the dollar.</span></li>
<li><span class="eq">RER = S x P1 / P2 = {fmt(r['S'], 6)} x {fmt(r['P1'], 6)} / {fmt(r['P2'], 6)}
 = <span class="res">{fmt(r['RER'], 6)}</span></span>
 <span class="why">P1 and P2 are the CPI index levels for {short_name(c1)} and {short_name(c2)}.</span></li>
<li><span class="eq">RER* = average of RER over {n_valid:,} valid months
 ({month_label(first_m)} to {month_label(last_m)}) = <span class="res">{fmt(rer_star, 6)}</span></span>
 <span class="why">This changes whenever you move the sample period slider.</span></li>
<li><span class="eq">Real index = 100 x RER / RER* = 100 x {fmt(r['RER'], 6)} / {fmt(rer_star, 6)}
 = <span class="res">{r['Real_index']:,.4f}</span></span>
 <span class="why">Average of the real index over the valid months: {sample.loc[valid, 'Real_index'].mean():,.6f}</span></li>
</ol></div>
""",
        unsafe_allow_html=True,
    )

with tab_data:
    show = pd.DataFrame(
        {
            "Month": [month_label(p) for p in sample.index],
            f"{cur1} per USD": sample["e1"].values,
            f"{cur2} per USD": sample["e2"].values,
            f"S ({cur2} per {cur1})": sample["S"].values,
            f"CPI {short_name(c1)}": sample["P1"].values,
            f"CPI {short_name(c2)}": sample["P2"].values,
            "RER": sample["RER"].values,
            "Real index": sample["Real_index"].values,
            "Valid": sample["valid"].values,
        }
    )
    st.dataframe(show.iloc[::-1], hide_index=True, width="stretch", height=420)

with tab_cov:
    st.markdown(
        "IMF series start and stop at different dates and can have gaps. A month is "
        "**valid** only when all four series have a value; other months are left blank "
        "and excluded from RER*."
    )
    st.dataframe(pd.DataFrame(coverage.values()), hide_index=True, width="stretch")
    missing = int((~valid).sum())
    if missing:
        st.caption(f"{missing:,} month(s) in the selected period are missing at least one series.")

with tab_about:
    st.markdown(
        f"""
**Definitions**

- S(t): units of Country 2 currency per 1 unit of Country 1 currency, built as
  e2(t) / e1(t), where e is the IMF's local currency per US dollar (period average).
- P1(t), P2(t): consumer price index levels (all items) for each country.
- RER(t) = S(t) x P1(t) / P2(t). A higher RER means Country 1's goods have become
  more expensive relative to Country 2's goods, i.e. a real appreciation of Country 1's currency.
- RER* = average RER(t) over the valid months in the selected period.
- Real index(t) = 100 x RER(t) / RER*, so it averages exactly 100 over the period.

**IMF series used**

- CPI: dataflow `IMF.STA/CPI`, key `{{ISO3}}.CPI._T.IX.M`
- Exchange rate: dataflow `IMF.STA/ER`, key `{{ISO3}}.XDC_USD.PA_RT.M`
- Euro area code: `G163`. United States: the IMF has no USD-per-USD series, so e = 1.
- API: `{IMF_BASE}`. Data are cached for 12 hours.

**Caveats**

CPI base years differ by country, which is why the RER level itself has no natural meaning
and we look at the index instead. Currency labels show today's currency; for countries that
redenominated or joined the euro, check how the IMF reports earlier history.
"""
    )

st.markdown(
    f'<p class="note" style="margin-top:2rem">Data: International Monetary Fund, SDMX 3.0 API '
    f"(CPI and ER datasets). Built for Kellogg International Finance.</p>",
    unsafe_allow_html=True,
)
