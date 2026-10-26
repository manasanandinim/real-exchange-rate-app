# Real Exchange Rate Explorer

A Streamlit app that compares any two IMF countries (or the Euro area) in
nominal and real terms, using monthly IMF CPI and exchange-rate data from
January 1976 onwards.

Built by Manasa Nandini Manimozhi for International Finance, Kellogg School of
Management (Fall 2026). Code written with Claude (Anthropic), model
`claude-opus-5-5` (Claude Opus 5.5), on 26 October 2026; prompts and economic
checks by the author.

## What it calculates

| Symbol | Meaning |
|---|---|
| e1(t), e2(t) | IMF exchange rate: local currency per 1 US dollar (period average) |
| S(t) = e2(t) / e1(t) | Units of Country 2 currency per 1 unit of Country 1 currency |
| P1(t), P2(t) | Consumer price index (all items) of Country 1 and Country 2 |
| RER(t) = S(t) x P1(t) / P2(t) | Real exchange rate |
| RER* | Average of RER(t) over the valid months in the selected sample period |
| Real index(t) = 100 x RER(t) / RER* | Real exchange rate index, averages 100 over the sample |

A month is **valid** only when both CPIs and both exchange rates exist. RER*
is recalculated whenever the sample dates change. The nominal rate S(t) is
plotted in actual currency units, not normalized.

A rise in RER (or the real index) means Country 1's goods have become more
expensive relative to Country 2's goods: a real appreciation of Country 1's
currency.

## Features

- Pick Country 1 and Country 2 from IMF economies and the Euro area; swap them in one click.
- Choose the sample period with a month slider.
- Chart views: Real, Nominal, or Both (Both uses separate left and right axes).
- A plain-language summary of what the latest numbers mean.
- "Check the math" tab that walks through S, RER, RER* and the real index for any month.
- CSV download of every month in the sample period with all inputs and calculations.
- Data coverage table showing where IMF series start, stop or have gaps.

## Data

IMF SDMX 3.0 API: `https://api.imf.org/external/sdmx/3.0`

- CPI: dataflow `IMF.STA/CPI`, key `{ISO3}.CPI._T.IX.M`
- Exchange rate: dataflow `IMF.STA/ER`, key `{ISO3}.XDC_USD.PA_RT.M`
- Euro area code: `G163`
- United States: the IMF does not publish a US dollar per US dollar series, so e = 1 by definition.

No API key is needed. Responses are cached for 12 hours. IMF coverage varies by
country, and live downloads occasionally fail; the app shows a "Try again"
button when that happens.

## CSV columns

`Month, Country_1, Country_2, e1_<CUR1>_per_USD, e2_<CUR2>_per_USD,
S_<CUR2>_per_<CUR1>, P1_CPI_<ISO1>, P2_CPI_<ISO2>, RER, Valid_month, RER_star,
Real_index`

## Run it yourself

The app is deployed on Streamlit Community Cloud (Python 3.12). To run locally:

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Files

- `app.py`: the app
- `requirements.txt`: Python packages
- `README.md`: this file
- `.streamlit/config.toml`: optional light theme and colors
