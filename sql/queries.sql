-- =========================================================
-- NHL Analytics Hub - SQL Analysis Queries (MySQL 8.0+)
-- 5 given queries + 10 own queries
-- Covers aggregation, JOINs, subqueries, GROUP BY,
-- ORDER BY, HAVING, and multi-condition WHERE clauses.
-- =========================================================

USE NHL_Analytics_Hub;
SET @season = '20252026';

-- Hint: Set @season to the season loaded in your database.
-- Requires unique team/season standings and player/season stats.
-- Season stats use the stored team attribution, not trade-aware splits.

-- ---------------------------------------------------------
-- Query 1: Which team has scored the most total goals this season?
-- Category: Given query
-- Technique: Aggregation + GROUP BY + ORDER BY
-- Business use case: Team scoring analysis
-- ---------------------------------------------------------
SELECT
    t.team_name,
    t.team_abbrev,
    SUM(s.goals_for) AS total_goals
FROM teams t
JOIN standings s ON t.team_id = s.team_id
WHERE s.season = @season
GROUP BY t.team_id, t.team_name, t.team_abbrev
ORDER BY total_goals DESC, t.team_abbrev
LIMIT 1;


-- ---------------------------------------------------------
-- Query 2: Who are the top 5 point scorers across the entire league?
-- Category: Given query
-- Technique: JOIN + ORDER BY
-- Business use case: Fantasy sports / player rankings
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
WHERE ss.season = @season
ORDER BY ss.points DESC
LIMIT 5;


-- ---------------------------------------------------------
-- Query 3: Which players have scored more than 20 goals AND recorded more than 30 assists?
-- Category: Given query
-- Technique: WHERE with multiple conditions
-- Business use case: Player scouting
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
WHERE ss.season = @season
  AND ss.goals > 20
  AND ss.assists > 30
ORDER BY ss.points DESC;


-- ---------------------------------------------------------
-- Query 4: Which teams have a season points total above the league average?
-- Category: Given query
-- Technique: Subquery
-- Business use case: Team performance comparison
-- ---------------------------------------------------------
SELECT
    t.team_name,
    t.team_abbrev,
    s.points
FROM teams t
JOIN standings s ON t.team_id = s.team_id
WHERE s.season = @season
  AND s.points > (
    SELECT AVG(points) FROM standings WHERE season = @season
)
ORDER BY s.points DESC;


-- ---------------------------------------------------------
-- Query 5: Which divisions have an average team points total above 90?
-- Category: Given query
-- Technique: GROUP BY + HAVING
-- Business use case: Division strength comparison
-- ---------------------------------------------------------
SELECT
    t.division_name,
    ROUND(AVG(s.points), 1) AS avg_division_points,
    COUNT(*) AS num_teams
FROM teams t
JOIN standings s ON t.team_id = s.team_id
WHERE s.season = @season
GROUP BY t.division_name
HAVING AVG(s.points) > 90
ORDER BY avg_division_points DESC;


-- ---------------------------------------------------------
-- Query 6: Which goalies have the best save percentage among those with at least 20 games?
-- Category: Own query 1
-- Technique: WHERE + JOIN + ORDER BY
-- Business use case: Fantasy sports / goalie scouting
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
WHERE gs.season = @season
  AND gs.games_played >= 20
ORDER BY gs.save_pct DESC
LIMIT 10;


-- ---------------------------------------------------------
-- Query 7: Which teams have the most wins this season?
-- Category: Own query 2
-- Technique: JOIN + ORDER BY
-- Business use case: Team performance rankings
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
WHERE s.season = @season
ORDER BY s.wins DESC
LIMIT 10;


-- ---------------------------------------------------------
-- Query 8: Who is the leading point scorer on each team?
-- Category: Own query 3
-- Technique: Window function (ROW_NUMBER) partitioned by team
-- Business use case: Team leaders / broadcast graphics
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
            ORDER BY ss.points DESC, ss.goals DESC, ss.player_id
        ) AS team_rank
    FROM skater_season_stats ss
    JOIN players p ON ss.player_id = p.player_id
    JOIN teams t ON ss.team_id = t.team_id
    WHERE ss.season = @season
) ranked
WHERE team_rank = 1
ORDER BY points DESC;


-- ---------------------------------------------------------
-- Query 9: Which teams have the best goal differential?
-- Category: Own query 4
-- Technique: Calculated column + ORDER BY
-- Business use case: Power rankings
-- ---------------------------------------------------------
SELECT
    t.team_name,
    t.team_abbrev,
    s.goals_for,
    s.goals_against,
    (s.goals_for - s.goals_against) AS goal_differential
FROM teams t
JOIN standings s ON t.team_id = s.team_id
WHERE s.season = @season
ORDER BY goal_differential DESC
LIMIT 10;


-- ---------------------------------------------------------
-- Query 10: Which players have the most penalty minutes, and what is their point production?
-- Category: Own query 5
-- Technique: Multiple JOINs + ORDER BY
-- Business use case: Discipline and player scouting
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
WHERE ss.season = @season
ORDER BY ss.penalty_min DESC
LIMIT 10;


-- ---------------------------------------------------------
-- Query 11: Which teams have the largest difference between home wins and away wins?
-- Category: Own query 6
-- Technique: Calculated column + ORDER BY
-- Business use case: Home and away record comparison
-- ---------------------------------------------------------
SELECT
    t.team_name,
    s.home_wins,
    s.away_wins,
    (s.home_wins - s.away_wins) AS home_ice_advantage
FROM teams t
JOIN standings s ON t.team_id = s.team_id
WHERE s.season = @season
ORDER BY home_ice_advantage DESC
LIMIT 10;


-- ---------------------------------------------------------
-- Query 12: Which teams average more than 3 goals across at least 10 completed regular-season games?
-- Category: Own query 7
-- Technique: UNION ALL + aggregation + GROUP BY + HAVING
-- Business use case: Offensive team scouting
-- ---------------------------------------------------------
SELECT
    t.team_abbrev,
    COUNT(*) AS games_played,
    SUM(r.goals) AS total_goals,
    ROUND(AVG(r.goals), 2) AS goals_per_game
FROM (
    SELECT home_team_id AS team_id, home_score AS goals
    FROM games WHERE season=@season AND game_type=2 AND game_state='OFF'
      AND home_score IS NOT NULL AND away_score IS NOT NULL
    UNION ALL
    SELECT away_team_id, away_score
    FROM games WHERE season=@season AND game_type=2 AND game_state='OFF'
      AND home_score IS NOT NULL AND away_score IS NOT NULL
) r
JOIN teams t ON t.team_id=r.team_id
GROUP BY t.team_id, t.team_abbrev
HAVING COUNT(*) >= 10 AND AVG(r.goals) > 3
ORDER BY goals_per_game DESC, t.team_abbrev;


-- ---------------------------------------------------------
-- Query 13: Which players have the most three-point regular-season games?
-- Category: Own query 8
-- Technique: Multiple JOINs + aggregation + GROUP BY
-- Business use case: Fantasy sports / high-impact player analysis
-- ---------------------------------------------------------
SELECT
    p.player_id,
    p.first_name,
    p.last_name,
    COUNT(*) AS three_point_games
FROM game_stats gs
JOIN players p ON p.player_id=gs.player_id
JOIN games g ON g.game_id=gs.game_id
WHERE g.season=@season AND g.game_type=2 AND g.game_state='OFF'
  AND gs.points >= 3
GROUP BY p.player_id, p.first_name, p.last_name
ORDER BY three_point_games DESC, p.player_id
LIMIT 10;


-- ---------------------------------------------------------
-- Query 14: Which teams have the highest shooting percentage in completed regular-season games?
-- Category: Own query 9
-- Technique: Aggregation + NULLIF + GROUP BY + HAVING
-- Business use case: Scoring efficiency analysis
-- ---------------------------------------------------------
SELECT
    t.team_abbrev,
    SUM(gs.goals) AS goals,
    SUM(gs.shots_on_goal) AS shots,
    ROUND(100.0 * SUM(gs.goals) / NULLIF(SUM(gs.shots_on_goal), 0), 2) AS shooting_percentage
FROM game_stats gs
JOIN teams t ON t.team_id=gs.team_id
JOIN games g ON g.game_id=gs.game_id
WHERE g.season=@season AND g.game_type=2 AND g.game_state='OFF'
  AND gs.goals IS NOT NULL AND gs.shots_on_goal IS NOT NULL
GROUP BY t.team_id, t.team_abbrev
HAVING SUM(gs.shots_on_goal) > 0
ORDER BY shooting_percentage DESC, t.team_abbrev;


-- ---------------------------------------------------------
-- Query 15: Which goalies have the most shutouts among those with at least 20 games?
-- Category: Own query 10
-- Technique: WHERE + multiple JOINs + ORDER BY
-- Business use case: Goalie leaderboards
-- ---------------------------------------------------------
SELECT
    p.player_id,
    p.first_name,
    p.last_name,
    t.team_abbrev,
    gs.games_played,
    gs.shutouts,
    gs.wins
FROM goalie_season_stats gs
JOIN players p ON p.player_id=gs.player_id
JOIN teams t ON t.team_id=gs.team_id
WHERE gs.season=@season AND gs.games_played >= 20
ORDER BY gs.shutouts DESC, gs.wins DESC, p.player_id
LIMIT 10;


