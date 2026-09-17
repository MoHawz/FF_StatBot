"""
Central configuration for the fantasy football automation.

Nothing sensitive is hard-coded here. All secrets are read from environment
variables (or a local `.env` file loaded via python-dotenv if present), so
this file is safe to commit / share.

Required environment variables
-------------------------------
ESPN_LEAGUE_ID      - your league id (the number in your league's ESPN URL)
ESPN_SEASON_YEAR    - the season to operate on, e.g. 2026
ESPN_S2             - "espn_s2" cookie value (only needed for a private league)
ESPN_SWID           - "SWID" cookie value, including the curly braces (private league only)

GROUPME_BOT_ID      - bot_id from https://dev.groupme.com/bots (optional; leave unset to skip posting)

GOOGLE_SERVICE_ACCOUNT_JSON - path to a Google service-account JSON key file (optional; leave unset to skip Sheets)
GOOGLE_SHEET_ID              - the spreadsheet ID (the long id in the sheet's URL) to write results into

LEAGUE_DISPLAY_NAME - your league's name, shown as the subtitle on the
                      rendered image cards (optional; defaults to a
                      generic placeholder). Purely cosmetic -- kept out of
                      the committed code so this repo can be public without
                      naming your actual league.
BOT_NAME             - your GroupMe bot's name, shown in the footer of the
                      rendered image cards (optional; defaults to a generic
                      placeholder). Same reasoning as LEAGUE_DISPLAY_NAME --
                      this is just the little "<Bot Name>'s Power Rankings"
                      caption at the bottom of each card.

See SETUP.md in this folder for step-by-step instructions on getting each of these.
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _get_int(name, default=None):
    val = os.environ.get(name)
    return int(val) if val not in (None, "") else default


LEAGUE_ID = _get_int("ESPN_LEAGUE_ID", 0)
SEASON_YEAR = _get_int("ESPN_SEASON_YEAR")  # e.g. 2026; if unset, code will default to "current year"
ESPN_S2 = os.environ.get("ESPN_S2") or None
ESPN_SWID = os.environ.get("ESPN_SWID") or None

GROUPME_BOT_ID = os.environ.get("GROUPME_BOT_ID") or None
# A personal GroupMe access token (from https://dev.groupme.com after logging
# in -- NOT the bot_id). Only needed to post the power-rankings graphic as an
# actual image: GroupMe's Image Service requires a real user's token to
# upload to, bots can't upload images on their own. Text-only posts (awards,
# FAAB report, predictions) work fine without this.
GROUPME_ACCESS_TOKEN = os.environ.get("GROUPME_ACCESS_TOKEN") or None

GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or None
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID") or None

# Cosmetic only -- shown on the rendered image cards. Kept as env vars
# (rather than hard-coded in the image renderers) so this repo can be
# public without the source revealing your actual league/bot names.
LEAGUE_DISPLAY_NAME = os.environ.get("LEAGUE_DISPLAY_NAME") or "Fantasy League"
BOT_NAME = os.environ.get("BOT_NAME") or "Stat Bot"


def require(*names):
    """Raise a clear error if any of the named config values are missing."""
    missing = [n for n in names if globals().get(n) in (None, "")]
    if missing:
        raise RuntimeError(
            f"Missing required configuration: {', '.join(missing)}. "
            f"Set these as environment variables (see SETUP.md)."
        )
