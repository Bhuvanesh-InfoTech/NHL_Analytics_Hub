# 🏒 NHL Analytics Hub

An NHL data pipeline with MySQL analysis and an interactive Streamlit dashboard.

## Overview

The project collects data from the NHL public API, converts JSON responses into
seven relational tables, and displays team, player, game and season statistics.

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3 |
| API requests | requests |
| Data processing | pandas |
| Database | MySQL 8.0+ |
| Database connector | mysql-connector-python |
| Dashboard | Streamlit and streamlit-option-menu |
| Charts | Plotly |
| Data collection | Jupyter notebooks |

## Project Structure

```text
NHL_Analytics_Hub/
├── app/
│   └── app.py
├── notebooks/
│   ├── 01_fetch_teams_standings_SQLServer.ipynb
│   ├── 02_fetch_players_MySQL.ipynb
│   ├── 03_fetch_games_MySQL.ipynb
│   └── 04_fetch_stats_MySQL.ipynb
├── sql/
│   └── queries.sql
├── .gitignore
├── README.md
└── requirements.txt
```

The first notebook retains `SQLServer` in its filename, but its code uses MySQL.

## Database Tables

| Table | API source | Data |
|---|---|---|
| teams | standings/now | Team names, abbreviations, conferences and divisions |
| standings | standings/now | Team season records and points |
| players | roster/{team}/current | Player details and current team |
| games | club-schedule-season/{team}/{season} | Schedules, scores and game states |
| game_stats | gamecenter/{game_id}/boxscore | Skater statistics for individual games |
| skater_season_stats | player/{player_id}/landing | Skater season totals |
| goalie_season_stats | player/{player_id}/landing | Goalie season statistics |

The notebooks contain the MySQL table creation statements. A separate
`create_tables.sql` file is not required for the current notebook setup.

## Setup

### 1. Install dependencies

Run from the project folder:

```text
python -m pip install streamlit streamlit-option-menu pandas requests mysql-connector-python plotly jupyterlab
```

### 2. Configure MySQL

Start MySQL and check the connection settings in each notebook and `DB_CONFIG`
in `app/app.py`. Use your own host, port, username, password and database name.
Do not publish database passwords to GitHub.

The first notebook creates the configured database and the teams and standings
tables. The remaining notebooks create their respective tables before loading data.

### 3. Run the notebooks

Open Jupyter or VS Code and run the notebooks in this order:

1. `notebooks/01_fetch_teams_standings_SQLServer.ipynb` — teams and standings.
2. `notebooks/02_fetch_players_MySQL.ipynb` — player details and rosters.
3. `notebooks/03_fetch_games_MySQL.ipynb` — schedules and game results.
4. `notebooks/04_fetch_stats_MySQL.ipynb` — game, skater and goalie statistics.

Use compatible season settings across data collection, SQL analysis and the dashboard.

### 4. Run the dashboard

```text
streamlit run app/app.py
```

Open the local URL displayed in the terminal, usually `http://localhost:8501`.

## SQL Analysis

`sql/queries.sql` contains **15 queries: 5 given questions and 10 original questions**.
The queries cover JOINs, aggregation, subqueries, GROUP BY, HAVING, ORDER BY,
multiple WHERE conditions and window functions.

Set the script's season variable to a season loaded in MySQL before running it.
The saved queries are also available in the dashboard's SQL Lab.

## Dashboard Pages

| Page | Features |
|---|---|
| Dashboard | Season overview, KPI cards and highlights |
| Teams | Standings, conference and division filters, team profiles and rosters |
| Players | Name search, player details and leaderboards |
| Games | Schedule and results with conference, team, date and game-state filters |
| Insights | Team comparisons and calculated observations |
| SQL Lab | Saved analysis queries and a custom SELECT query editor |

Dynamic filters add conditions to SQL queries before results are retrieved.

## Data Notes

- Current rosters may differ from historical game participants or past team assignments.
- Season statistics depend on the season returned or selected during data collection.
- Upcoming games may have no scores, and some API fields may be missing.
- Strict leaderboard thresholds can return no rows early in a season.
- Team-based statistics depend on the team attribution stored in the database.

## Author

Built as a data engineering and analytics portfolio project covering REST APIs,
JSON processing, relational database design, SQL analysis and dashboard development.
