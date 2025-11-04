# thunder_bot.py
# Posts "Did the Oklahoma City Thunder win last night?" using BallDontLie + X API.
# Runs daily; figures out "yesterday" in America/Chicago.

import os
import sys
import requests
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from requests_oauthlib import OAuth1

BALLDONTLIE_API = "https://api.balldontlie.io/v1"
GAMES_URL = f"{BALLDONTLIE_API}/games"
TEAMS_URL = f"{BALLDONTLIE_API}/teams"

TEAM_ABBR = "OKC"
TEAM_NICK = "Thunder"
TEAM_CITY_FULL = "Oklahoma City Thunder"

# BallDontLie API key (GitHub Secret: BDL_API_KEY) — no "Bearer" prefix
BDL_API_KEY = os.getenv("BDL_API_KEY")
HEADERS = {"Authorization": BDL_API_KEY} if BDL_API_KEY else {}

# X (Twitter) creds (GitHub Secrets)
API_KEY = os.getenv("TWITTER_API_KEY")
API_SECRET = os.getenv("TWITTER_API_SECRET")
ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")

def fail(msg, code=1):
    print(msg)
    sys.exit(code)

def chicago_yesterday_date():
    """
    Default: yesterday in America/Chicago.
    Optional override via env FORCE_DATE='YYYY-MM-DD' for manual tests.
    """
    force = os.getenv("FORCE_DATE")
    if force:
        try:
            return date.fromisoformat(force)
        except Exception:
            pass  # fall back if bad format
    tz = ZoneInfo("America/Chicago")
    now_ct = datetime.now(tz)
    yday_ct = now_ct - timedelta(days=1)
    return yday_ct.date()

def resolve_team_id():
    """
    Resolve Thunder team_id from BallDontLie so we don't hardcode.
    You can override with env TEAM_ID if you prefer.
    """
    env_id = os.getenv("TEAM_ID")
    if env_id:
        try:
            return int(env_id)
        except ValueError:
            pass

    r = requests.get(TEAMS_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    for t in r.json().get("data", []):
        if t.get("abbreviation") == TEAM_ABBR or t.get("full_name") == TEAM_CITY_FULL:
            return t["id"]
    fail(f"Could not resolve team_id for {TEAM_CITY_FULL} / {TEAM_ABBR}")

def fetch_game_for(team_id, date_obj):
    params = {
        "dates[]": date_obj.isoformat(),
        "team_ids[]": team_id,
        "per_page": 100,
    }
    r = requests.get(GAMES_URL, params=params, headers=HEADERS, timeout=20)
    print("DEBUG requesting:", r.url)
    r.raise_for_status()
    data = r.json().get("data", [])
    if not data:
        return None
    # Prefer completed games (final/finished or any with recorded scores)
    for g in data:
        if g.get("status", "").lower() in ("final", "final/ot", "finished") or (
            g.get("home_team_score", 0) + g.get("visitor_team_score", 0) > 0
        ):
            return g
    return data[0]

def format_tweet(game, date_obj, team_id):
    if game is None:
        print("No game found for date:", date_obj)
        return None

    home = game["home_team"]
    away = game["visitor_team"]
    home_score = game["home_team_score"]
    away_score = game["visitor_team_score"]

    is_home = home["id"] == team_id
    team_score = home_score if is_home else away_score
    opp = away if is_home else home
    opp_score = away_score if is_home else home_score

    won = team_score > opp_score
    yes_no = "YES" if won else "NO"

    month = date_obj.strftime("%b")
    date_str = f"{month} {date_obj.day}, {date_obj.year}"

    venue = "vs" if is_home else "@"
    opponent_line = f"{venue} {opp['full_name']}"
    score_line = f"{TEAM_NICK} {team_score} – {opp_score} {opp['name']}"

    # Blank line after YES/NO for readability
    tweet = f"{yes_no}\n\n{date_str}\n{opponent_line}\n{score_line}"
    return tweet[:280]

def post_to_x(status_text):
    if not all([API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_SECRET]):
        fail("Missing one or more Twitter credentials in environment variables.")

    # X API v2 create tweet endpoint
    auth = OAuth1(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_SECRET)
    url = "https://api.twitter.com/2/tweets"
    payload = {"text": status_text}
    r = requests.post(url, auth=auth, json=payload, timeout=20)
    if r.status_code >= 400:
        fail(f"Twitter post failed [{r.status_code}]: {r.text}")
    tid = r.json().get("data", {}).get("id")
    print("Tweet posted:", tid)

def main():
    ydate = chicago_yesterday_date()
    team_id = resolve_team_id()
    game = fetch_game_for(team_id, ydate)
    tweet = format_tweet(game, ydate, team_id)
    if tweet is None:
        print("No Thunder game yesterday — nothing to post.")
        return
    post_to_x(tweet)

if __name__ == "__main__":
    main()
