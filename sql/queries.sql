-- =========================================================
-- NHL Analytics Hub — SQL Analysis Queries (SQLite)
-- 10+ queries covering aggregation, JOINs, subqueries,
-- GROUP BY, HAVING, and multi-condition WHERE clauses.
-- =========================================================


-- ---------------------------------------------------------
-- Query 1: Which team has scored the most total goals this season?
-- Technique: Aggregation + ORDER BY
-- ---------------------------------------------------------
SELECT
    t.team_name,
    t.team_abbrev,
    s.goals_for AS total_goals
FROM teams t
JOIN standings s ON t.team_id = s.team_id
ORDER BY s.goals_for DESC
LIMIT 1;


-- ---------------------------------------------------------
-- Query 2: Who are the top 5 point scorers across the entire league?
-- Technique: JOIN + ORDER BY
-- ---------------------------------------------------------
SELECT
    p.first_name,
    p.last_name,
    t.team_abbrev,
    ss.goals,
    ss.assists,
    ss.points
FROM skater_season_stats ss
JOIN players p ON ss.player_id = p.player_id
JOIN teams t ON ss.team_id = t.team_id
ORDER BY ss.points DESC
LIMIT 5;


-- ---------------------------------------------------------
-- Query 3: Which players have scored more than 20 goals AND
-- recorded more than 30 assists in the season?
-- Technique: WHERE with multiple conditions
-- ---------------------------------------------------------
SELECT
    p.first_name,
    p.last_name,
    t.team_abbrev,
    ss.goals,
    ss.assists,
    ss.points
FROM skater_season_stats ss
JOIN players p ON ss.player_id = p.player_id
JOIN teams t ON ss.team_id = t.team_id
WHERE ss.goals > 20
  AND ss.assists > 30
ORDER BY ss.points DESC;


-- ---------------------------------------------------------
-- Query 4: Which teams have a season points total above the
-- league average?
-- Technique: Subquery
-- ---------------------------------------------------------
SELECT
    t.team_name,
    t.team_abbrev,
    s.points
FROM teams t
JOIN standings s ON t.team_id = s.team_id
WHERE s.points > (
    SELECT AVG(points) FROM standings
)
ORDER BY s.points DESC;


-- ---------------------------------------------------------
-- Query 5: Which divisions have an average team points total
-- above 90?
-- Technique: GROUP BY + HAVING
-- ---------------------------------------------------------
SELECT
    t.division_name,
    ROUND(AVG(s.points), 1) AS avg_division_points,
    COUNT(*) AS num_teams
FROM teams t
JOIN standings s ON t.team_id = s.team_id
GROUP BY t.division_name
HAVING AVG(s.points) > 90
ORDER BY avg_division_points DESC;


-- ---------------------------------------------------------
-- Query 6: Which goalies have the best save percentage,
-- among those who have played at least 20 games?
-- Technique: WHERE (filtering out small-sample outliers) + ORDER BY
-- Business use case: fantasy sports / broadcast "best goalie" graphics
-- ---------------------------------------------------------
SELECT
    p.first_name,
    p.last_name,
    t.team_abbrev,
    gs.games_played,
    gs.save_pct,
    gs.goals_against_avg,
    gs.shutouts
FROM goalie_season_stats gs
JOIN players p ON gs.player_id = p.player_id
JOIN teams t ON gs.team_id = t.team_id
WHERE gs.games_played >= 20
ORDER BY gs.save_pct DESC
LIMIT 10;


-- ---------------------------------------------------------
-- Query 7: Which teams have the most total wins this season?
-- Technique: Aggregation + ORDER BY
-- Business use case: sports betting / odds modeling
-- ---------------------------------------------------------
SELECT
    t.team_name,
    t.conference_name,
    t.division_name,
    s.wins,
    s.losses,
    s.ot_losses
FROM teams t
JOIN standings s ON t.team_id = s.team_id
ORDER BY s.wins DESC
LIMIT 10;


-- ---------------------------------------------------------
-- Query 8: Who is the leading point scorer on each team?
-- Technique: Window function (ROW_NUMBER) partitioned by team
-- Business use case: team scouting / "team leaders" broadcast graphic
-- ---------------------------------------------------------
SELECT
    team_abbrev,
    first_name,
    last_name,
    goals,
    assists,
    points
FROM (
    SELECT
        t.team_abbrev,
        p.first_name,
        p.last_name,
        ss.goals,
        ss.assists,
        ss.points,
        ROW_NUMBER() OVER (
            PARTITION BY ss.team_id
            ORDER BY ss.points DESC
        ) AS team_rank
    FROM skater_season_stats ss
    JOIN players p ON ss.player_id = p.player_id
    JOIN teams t ON ss.team_id = t.team_id
) ranked
WHERE team_rank = 1
ORDER BY points DESC;


-- ---------------------------------------------------------
-- Query 9: Which teams have the best goal differential
-- (goals for minus goals against)?
-- Technique: Calculated column + ORDER BY
-- Business use case: odds modeling / power rankings
-- ---------------------------------------------------------
SELECT
    t.team_name,
    t.team_abbrev,
    s.goals_for,
    s.goals_against,
    (s.goals_for - s.goals_against) AS goal_differential
FROM teams t
JOIN standings s ON t.team_id = s.team_id
ORDER BY goal_differential DESC
LIMIT 10;


-- ---------------------------------------------------------
-- Query 10: Which players have the most penalty minutes,
-- and how does that compare to their point production?
-- Technique: Aggregation + multiple JOINs + ORDER BY
-- Business use case: scouting (identifying high-penalty players
-- who may hurt the team on the penalty kill)
-- ---------------------------------------------------------
SELECT
    p.first_name,
    p.last_name,
    t.team_abbrev,
    ss.penalty_min,
    ss.points,
    ss.games_played
FROM skater_season_stats ss
JOIN players p ON ss.player_id = p.player_id
JOIN teams t ON ss.team_id = t.team_id
ORDER BY ss.penalty_min DESC
LIMIT 10;


-- ---------------------------------------------------------
-- BONUS Query 11: Which teams have a home record notably
-- stronger than their away record?
-- Technique: Calculated column
-- Business use case: ticket pricing / home-ice advantage analysis
-- ---------------------------------------------------------
SELECT
    t.team_name,
    s.home_wins,
    s.away_wins,
    (s.home_wins - s.away_wins) AS home_ice_advantage
FROM teams t
JOIN standings s ON t.team_id = s.team_id
ORDER BY home_ice_advantage DESC
LIMIT 10;
