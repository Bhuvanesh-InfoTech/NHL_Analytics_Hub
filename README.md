# 🏒 NHL Analytics Hub

An end-to-end data pipeline and analytics dashboard built on the official
NHL public API — REST API ingestion → normalized SQL database → SQL
analysis → interactive Streamlit dashboard.

## Overview

This project fetches live data from the NHL API across teams, players,
games, and player statistics, parses and normalizes it into a 7-table
relational schema, answers business questions with SQL, and presents the
results through a multi-page Streamlit dashboard.

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3 |
| Data fetching | `requests` |
| Data wrangling | `pandas` |
| Database | **SQLite** (via Python's built-in `sqlite3` module — no server setup required) |
| Dashboard | `streamlit` + `streamlit-option-menu` |
| Notebooks | Jupyter (`.ipynb`) for the ETL pipeline |


## Database Schema

7 normalized tables:

| Table | Source Endpoint | Description |
|---|---|---|
| `teams` | `standings/now` | Team identity, conference, division |
| `standings` | `standings/now` | Season win/loss/points record per team |
| `players` | `roster/{team}/current` | Player bio and physical info |
| `games` | `club-schedule-season/{team}/{season}` | Full season schedule and scores |
| `game_stats` | `gamecenter/{game_id}/boxscore` | Per-game skater stats |
| `skater_season_stats` | `player/{player_id}/landing` | Season totals for skaters |
| `goalie_season_stats` | `player/{player_id}/landing` | Season totals for goalies |

Full column definitions and constraints are in [`sql/create_tables.sql`](sql/create_tables.sql).


### Build the database

Run the notebooks **in order** — each one depends on tables populated by
the previous one:

1. `notebooks/01_fetch_teams_standings.ipynb` — creates the database and
   loads `teams` + `standings`
2. `notebooks/02_fetch_players.ipynb` — loads `players`
3. `notebooks/03_fetch_games.ipynb` — loads `games`. Pinned to a completed
   season (`SEASON = "20252026"`) rather than `"now"`, since during the
   NHL off-season `"now"` resolves to the upcoming season with no played
   games yet.
4. `notebooks/04_fetch_stats.ipynb` — loads `game_stats`,
   `skater_season_stats`, and `goalie_season_stats`. Progress is
   checkpointed with a database commit every 25 records, so it's safe to
   re-run if interrupted.

Open each notebook in VS Code or Jupyter and **Run All**.

### Run the dashboard

Then open the URL Streamlit prints (typically `http://localhost:8501`).

## SQL Analysis

11 documented queries covering aggregation, JOINs, subqueries, GROUP BY +
HAVING, multi-condition WHERE clauses, and a window function — see
[`sql/queries.sql`](sql/queries.sql). The same queries are also available
interactively from the dashboard's **SQL Query** page.

## Dashboard Pages

| Page | What it shows |
|---|---|
| Home | League-wide KPIs, top scorer/goalie highlights, top-5 scorers chart |
| Standings | Full standings, filterable by conference/division |
| Team Info | Team detail + roster grouped by position |
| Player Search | Search any player, see stat cards and a headshot |
| Game Results | Browse games, filterable by team/date/game state |
| Leaderboards | Top scorers, most penalty minutes, best save %, most wins |
| SQL Query | Run any of the 11 pre-built queries, or write your own `SELECT` |

## Known Limitations

- `players.team_id` reflects each player's **current** roster, while
  `games`/`game_stats`/season stats target the most recently completed
  season by default — a player traded over the summer may show a
  mismatched team.
- The NHL's `roster/{team}/current` endpoint is known to intermittently
  omit active players from its response (a documented upstream API
  quirk), so player counts can vary slightly between runs.

## Author

Built as a data engineering / analytics portfolio project covering REST
API integration, JSON parsing, relational database design, SQL analysis,
and dashboard development.