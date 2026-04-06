import pandas as pd
import requests
import re
from bs4 import BeautifulSoup

import iso_emoji # ISO_TO_EMOJI mapping
import top_riders # Arrays of readable names for manual star assignment

import how_won #

# ---------------------------------------------------------
# CONFIG — ingest etc
# ---------------------------------------------------------

STARTLIST_URL = "https://www.procyclingstats.com/race/paris-roubaix/2026/startlist"
TOP_URL = f"{STARTLIST_URL}/top-competitors"
DEBUT_URL = f"{STARTLIST_URL}/debutants"
RACE_NAME = "Paris-Roubaix 2026"

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _normalise_spaces(s: str) -> str:
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s.strip())
    return s

def make_lookup_from_pcs(raw_name: str) -> str:
    """
    PCS format: SURNAME SURNAME Firstname
    → canonical: 'surname surname firstname' (lowercase)
    """
    s = _normalise_spaces(raw_name)
    parts = s.split(" ")
    if len(parts) < 2:
        return s.lower()
    surname = " ".join(parts[:-1]).lower()
    firstname = parts[-1].lower()
    return f"{surname} {firstname}"

def make_lookup_from_readable(name: str) -> str:
    """
    Readable format: Firstname Surname Surname
    → canonical: 'surname surname firstname' (lowercase)
    """
    s = _normalise_spaces(name)
    parts = s.split(" ")
    if len(parts) < 2:
        return s.lower()
    firstname = parts[0].lower()
    surname = " ".join(parts[1:]).lower()
    return f"{surname} {firstname}"

def flip_name_from_pcs(raw_name: str) -> str:
    """
    PCS format: SURNAME SURNAME Firstname
    → 'Firstname Surname Surname' with nice caps
    """
    s = _normalise_spaces(raw_name)
    parts = s.split(" ")
    if len(parts) < 2:
        return s
    firstname = parts[-1].capitalize()
    surname_parts = [p.capitalize() for p in parts[:-1]]
    surname = " ".join(surname_parts)
    return f"{firstname} {surname}"

# Convert readable names → canonical lookup keys
TIER_6 = {make_lookup_from_readable(n) for n in top_riders.READABLE_TIER_6}
TIER_5 = {make_lookup_from_readable(n) for n in top_riders.READABLE_TIER_5}
TIER_4 = {make_lookup_from_readable(n) for n in top_riders.READABLE_TIER_4}
TIER_3 = {make_lookup_from_readable(n) for n in top_riders.READABLE_TIER_3}
TIER_2 = {make_lookup_from_readable(n) for n in top_riders.READABLE_TIER_2}
TIER_1 = {make_lookup_from_readable(n) for n in top_riders.READABLE_TIER_1}

DEFAULT_STARS = "☆☆☆☆☆"

def manual_star_assign_lookup(lookup: str) -> str:
    if lookup in TIER_6: return "★★★★★★"
    if lookup in TIER_5: return "★★★★★"
    if lookup in TIER_4: return "★★★★☆"
    if lookup in TIER_3: return "★★★☆☆"
    if lookup in TIER_2: return "★★☆☆☆"
    if lookup in TIER_1: return "★☆☆☆☆"
    return DEFAULT_STARS

#----------------------------------------------------------
# IMPORT FROM PCS
# ---------------------------------------------------------
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
    "DNT": "1",
}

def fetch_html(url):
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.text

startlist_html = fetch_html(STARTLIST_URL)
top_html = fetch_html(TOP_URL)

# ---------------------------------------------------------
# PARSE STARTLIST
# ---------------------------------------------------------

def parse_startlist(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for team_li in soup.select("ul.startlist_v4 > li"):
        team_name_tag = team_li.select_one(".ridersCont a.team")
        if not team_name_tag:
            continue

        team_name = team_name_tag.get_text(strip=True)

        for rider_li in team_li.select(".ridersCont ul > li"):
            bib_tag = rider_li.select_one(".bib")
            name_tag = rider_li.select_one("a[href*='rider']")
            flag_tag = rider_li.select_one("span.flag")

            if not name_tag:
                continue

            bib = bib_tag.get_text(strip=True) if bib_tag else ""
            raw_name = name_tag.get_text(strip=True)

            # PCS → canonical lookup key
            lookup_key = make_lookup_from_pcs(raw_name)
            display_name = flip_name_from_pcs(raw_name)

            # Flag ISO code
            iso = ""
            if flag_tag:
                for cls in flag_tag.get("class") or []:
                    if cls != "flag":
                        iso = cls.lower()

            flag = iso_emoji.ISO_TO_EMOJI.get(iso, iso.upper()) if iso else "—"

            rows.append([bib, display_name, flag, team_name, lookup_key])

    return pd.DataFrame(rows, columns=["Number", "Rider", "Flag", "Team", "Lookup"])


# ---------------------------------------------------------
# PARSE TOP COMPETITORS
# ---------------------------------------------------------

def parse_top_competitors(html):
    soup = BeautifulSoup(html, "html.parser")
    favs = {}

    for row in soup.select("table tr"):
        cells = row.select("td")
        if len(cells) < 6:
            continue

        name_tag = cells[1].select_one("a[href*='rider']")
        if not name_tag:
            continue

        raw_name = name_tag.get_text(strip=True)
        key = make_lookup_from_pcs(raw_name)
        score = cells[-1].get_text(strip=True)

        favs[key] = score

    return favs

# ---------------------------------------------------------
# TWO-COLUMN PDF-READY HTML
# ---------------------------------------------------------

def make_two_column_html(df):
    df = df.sort_values("Rider")

    rows = []
    for _, r in df.iterrows():
        rows.append(f"""
        <div class="row">
            <span class="num">{r['Number']}</span>
            <span class="name">{r['Rider']}</span>
            <span class="flag">{r['Flag']}</span>
            <span class="team">{r['Team']}</span>
            <span class="fav">{r['Fav']}</span>
        </div>
        """)

    return f"""
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: 'Courier New', monospace;
                margin: 15mm;
            }}
            h2 {{
                text-align: center;
                margin-bottom: 10mm;
            }}
            .columns {{
                column-count: 2;
                column-gap: 20mm;
            }}
            .row {{
                break-inside: avoid;
                padding: 3px 0;
                display: block;
                width: 100%;
            }}
            .num {{ display: inline-block; width: 35px; }}
            .name {{ display: inline-block; width: 180px; }}
            .flag {{ display: inline-block; width: 30px; }}
            .team {{ display: inline-block; width: 180px; }}
            .fav {{ display: inline-block; width: 40px; text-align: right; }}

            @media print {{
                body {{ margin: 10mm; }}
                .columns {{ column-count: 2; column-gap: 15mm; }}
                .row {{ padding: 2px 0; font-size: 12px; }}
                h2 {{ margin-bottom: 5mm; }}
            }}
        </style>
    </head>
    <body>
        <h2>{RACE_NAME} — Startlist + PCS Favourites</h2>
        <div class="columns">
            {''.join(rows)}
        </div>
    </body>
    </html>
    """

def make_team_grouped_html(df):
    df = df.sort_values(["Team", "Number"])

    html_blocks = []

    for team, group in df.groupby("Team"):
        rows = []
        for _, r in group.iterrows():
            rows.append(f"""
            <div class="row">
                <span class="num">{r['Number']}</span>
                <span class="name">{r['Rider']}</span>
                <span class="flag">{r['Flag']}</span>
                <span class="stars">{r['Stars']}</span>
            </div>
            """)

        block = f"""
        <div class="team-block">
            <h3>{team}</h3>
            {''.join(rows)}
        </div>
        """
        html_blocks.append(block)

    return f"""
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: 'Courier New', monospace;
                margin: 15mm;
            }}
            h2 {{
                text-align: center;
                margin-bottom: 10mm;
            }}
            h3 {{
                margin-top: 8mm;
                margin-bottom: 3mm;
                border-bottom: 1px solid #ccc;
                padding-bottom: 2px;
            }}
            .columns {{
                column-count: 2;
                column-gap: 20mm;
            }}
            .row {{
                break-inside: avoid;
                padding: 2px 0;
                display: block;
                width: 100%;
            }}
            .num {{ display: inline-block; width: 35px; }}
            .name {{ display: inline-block; width: 160px; }}
            .flag {{ display: inline-block; width: 30px; }}
            .fav {{ display: inline-block; width: 30px; text-align: right; }}
            .stars {{ display: inline-block; width: 70px; }}

            @media print {{
                body {{ margin: 10mm; }}
                .columns {{ column-count: 2; column-gap: 15mm; }}
                .row {{ font-size: 12px; }}
            }}
        </style>
    </head>
    <body>
        <h2>{RACE_NAME} — Team‑Grouped Startlist</h2>
        <div class="columns">
            {''.join(html_blocks)}
        </div>
    </body>
    </html>
    """

# ---------------------------------------------------------
# RACE RADIO HTML
# ---------------------------------------------------------

def make_race_radio_html(df):
    df = df.sort_values("Number")

    rows = []
    for _, r in df.iterrows():
        stars = r['Stars']

        # Default: one row, no scenario
        scenario_list = [""]

        if stars == "★★★★★★":      # 6-star
            scenario_list = how_won.WIN_SCENARIOS_6
        elif stars == "★★★★★":      # 5-star
            scenario_list = how_won.WIN_SCENARIOS_5

        for scenario in scenario_list:
            rows.append(f"""
            <tr>
                <td>{r['Number']}</td>
                <td>{r['Rider']}<strong>{' — ' + scenario if scenario else ''}</strong></td>
                <td>{r['Team']}</td>
                <td>{r['Flag']}</td>
                <td>{r['Stars']}</td>
            </tr>
            """)

    return f"""
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Courier New', monospace; margin: 15mm; }}
            table {{ width: 1240px; border-collapse: collapse; font-size: 16px; }}
            th, td {{ padding: 10px 8px; border-bottom: 1px solid #ddd; }}
            th {{ text-align: left; font-size: 15px; }}
        </style>
    </head>
    <body>
        <h2>Race Radio — {RACE_NAME}</h2>
        <table>
            <tr><th>No.</th><th>Rider</th><th>Nat</th><th>Ranking</th></tr>
            {''.join(rows)}
        </table>
    </body>
    </html>
    """

# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

df = parse_startlist(startlist_html)
favs = parse_top_competitors(top_html)

df["Fav"] = df["Lookup"].map(lambda x: favs.get(x, "—"))
df["Stars"] = df["Lookup"].map(manual_star_assign_lookup)

two_col_html = make_two_column_html(df)
race_radio_html = make_race_radio_html(df)
team_grouped_html = make_team_grouped_html(df)

#with open(f"pages/{RACE_NAME}_startlist.html", "w", encoding="utf-8") as f:
#    f.write(startlist_html)
with open(f"index.html", "w", encoding="utf-8") as f:
    f.write(race_radio_html)
with open(f"pages/{RACE_NAME}_race_radio.html", "w", encoding="utf-8") as f:
    f.write(race_radio_html)
with open(f"pages/{RACE_NAME}_teams.html", "w", encoding="utf-8") as f:
    f.write(team_grouped_html)

print("Generated:")
print(f" - {RACE_NAME}_two_column.html")
print(f" - {RACE_NAME}_race_radio.html")
print(f" - {RACE_NAME}_teams.html")
print(f"Total riders: {len(df)}")