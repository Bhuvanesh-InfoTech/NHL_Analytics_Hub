-- =========================================================
-- NHL Analytics Hub — Database Schema (SQLite)
-- =========================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------
-- Table 1: teams
-- Source: GET https://api-web.nhle.com/v1/standings/now
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS teams (
    team_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    team_abbrev      VARCHAR(10) UNIQUE NOT NULL,
    team_name        VARCHAR(100) NOT NULL,
    conference_name  VARCHAR(50),
    division_name    VARCHAR(50),
    logo_url         TEXT
);

-- ---------------------------------------------------------
-- Table 2: standings
-- Source: GET https://api-web.nhle.com/v1/standings/now
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS standings (
    standing_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id       INTEGER NOT NULL,
    season        VARCHAR(20),
    games_played  INT,
    wins          INT,
    losses        INT,
    ot_losses     INT,
    points        INT,
    goals_for     INT,
    goals_against INT,
    home_wins     INT,
    away_wins     INT,
    streak_type   VARCHAR(20),
    streak_count  INT,
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

-- ---------------------------------------------------------
-- Table 3: players
-- Source: GET https://api-web.nhle.com/v1/roster/{team_abbrev}/current
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS players (
    player_id       BIGINT PRIMARY KEY,
    team_id         INTEGER NOT NULL,
    first_name      VARCHAR(100),
    last_name       VARCHAR(100),
    position        VARCHAR(10),
    jersey_number   INT,
    birth_date      DATE,
    birth_country   VARCHAR(10),
    height_cm       REAL,
    weight_kg       REAL,
    shoots_catches  VARCHAR(5),
    headshot_url    TEXT,
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

-- ---------------------------------------------------------
-- Table 4: games
-- Source: GET https://api-web.nhle.com/v1/club-schedule-season/{team_abbrev}/now
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS games (
    game_id       BIGINT PRIMARY KEY,
    season        VARCHAR(20),
    game_type     INT,
    game_date     DATE,
    home_team_id  INTEGER,
    away_team_id  INTEGER,
    home_score    INT,
    away_score    INT,
    game_state    VARCHAR(20),
    venue_name    VARCHAR(150),
    FOREIGN KEY (home_team_id) REFERENCES teams(team_id),
    FOREIGN KEY (away_team_id) REFERENCES teams(team_id)
);

-- ---------------------------------------------------------
-- Table 5: game_stats (skaters only, per game)
-- Source: GET https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS game_stats (
    stat_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id        BIGINT NOT NULL,
    player_id      BIGINT NOT NULL,
    team_id        INTEGER NOT NULL,
    goals          INT,
    assists        INT,
    points         INT,
    shots_on_goal  INT,
    penalty_min    INT,
    toi            VARCHAR(10),
    plus_minus     INT,
    FOREIGN KEY (game_id) REFERENCES games(game_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

-- ---------------------------------------------------------
-- Table 6: skater_season_stats
-- Source: GET https://api-web.nhle.com/v1/player/{player_id}/landing
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS skater_season_stats (
    stat_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id     BIGINT NOT NULL,
    season        VARCHAR(20),
    team_id       INTEGER,
    games_played  INT,
    goals         INT,
    assists       INT,
    points        INT,
    plus_minus    INT,
    penalty_min   INT,
    shots         INT,
    avg_toi       VARCHAR(10),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

-- ---------------------------------------------------------
-- Table 7: goalie_season_stats
-- Source: GET https://api-web.nhle.com/v1/player/{player_id}/landing
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS goalie_season_stats (
    stat_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id          BIGINT NOT NULL,
    season             VARCHAR(20),
    team_id            INTEGER,
    games_played       INT,
    wins               INT,
    losses             INT,
    ot_losses          INT,
    save_pct           FLOAT,
    goals_against_avg  FLOAT,
    shutouts           INT,
    saves              INT,
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);
