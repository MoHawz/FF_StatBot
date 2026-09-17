"""
Posts a formatted weekly power rankings message to your GroupMe group via a
bot (see SETUP.md for creating one at https://dev.groupme.com/bots).
GroupMe messages are capped at 1000 characters, so long posts are split.
"""
import requests

from . import config
from .power_rankings import PowerRankingRow

GROUPME_POST_URL = "https://api.groupme.com/v3/bots/post"
GROUPME_IMAGE_UPLOAD_URL = "https://image.groupme.com/pictures"
MAX_LEN = 1000


def _arrow(movement: int) -> str:
    if movement > 0:
        return f"▲{movement}"
    if movement < 0:
        return f"▼{abs(movement)}"
    return "―"


def format_power_rankings_message(week: int, rows: list) -> str:
    lines = [f"🏈 WEEK {week} POWER RANKINGS 🏈"]
    for r in rows:
        lines.append(
            f"{r.rank}. {r.team_name} ({r.owner}) — {r.power_score} {_arrow(r.movement)}  "
            f"[{r.wins}-{r.losses}{'-' + str(r.ties) if r.ties else ''}, {r.ppg} ppg]"
        )
    return "\n".join(lines)


def _chunks(text: str, max_len: int = MAX_LEN):
    lines = text.split("\n")
    chunk = ""
    for line in lines:
        candidate = f"{chunk}\n{line}" if chunk else line
        if len(candidate) > max_len:
            yield chunk
            chunk = line
        else:
            chunk = candidate
    if chunk:
        yield chunk


def post_message(text: str, bot_id: str = None):
    bot_id = bot_id or config.GROUPME_BOT_ID
    if not bot_id:
        raise RuntimeError("GROUPME_BOT_ID is not set; skipping GroupMe post.")
    for chunk in _chunks(text):
        resp = requests.post(GROUPME_POST_URL, json={"bot_id": bot_id, "text": chunk}, timeout=10)
        resp.raise_for_status()


def post_power_rankings(week: int, rows: list, bot_id: str = None):
    post_message(format_power_rankings_message(week, rows), bot_id=bot_id)


def upload_image(image_path: str, access_token: str = None) -> str:
    """
    Uploads a local image file to GroupMe's Image Service and returns the
    hosted i.groupme.com URL. Requires a personal user access token (see
    SETUP.md) -- bots cannot upload images on their own, only post them
    once they already have a groupme.com URL.
    """
    access_token = access_token or config.GROUPME_ACCESS_TOKEN
    if not access_token:
        raise RuntimeError(
            "GROUPME_ACCESS_TOKEN is not set -- can't upload images to GroupMe. "
            "See SETUP.md for how to grab your personal access token from dev.groupme.com. "
            "(Text-only posts don't need this.)"
        )
    with open(image_path, "rb") as f:
        resp = requests.post(
            GROUPME_IMAGE_UPLOAD_URL,
            headers={"X-Access-Token": access_token, "Content-Type": "image/png"},
            data=f.read(),
            timeout=30,
        )
    resp.raise_for_status()
    return resp.json()["payload"]["url"]


def post_image_message(text: str, image_path: str, bot_id: str = None, access_token: str = None):
    """Uploads image_path to GroupMe and posts it as an attachment, with
    `text` as the accompanying caption (keep this short -- the image is the
    point)."""
    bot_id = bot_id or config.GROUPME_BOT_ID
    if not bot_id:
        raise RuntimeError("GROUPME_BOT_ID is not set; skipping GroupMe post.")
    image_url = upload_image(image_path, access_token=access_token)
    resp = requests.post(
        GROUPME_POST_URL,
        json={"bot_id": bot_id, "text": text, "attachments": [{"type": "image", "url": image_url}]},
        timeout=10,
    )
    resp.raise_for_status()


def post_power_rankings_image(week: int, image_path: str, bot_id: str = None, access_token: str = None):
    post_image_message(f"Week {week} Power Rankings \U0001F3C8", image_path, bot_id=bot_id, access_token=access_token)


def post_awards(week: int, awards: list, bot_id: str = None):
    """awards: list of (title, line) tuples, e.g. from banter.generate_weekly_awards()."""
    from .banter import format_awards_message
    post_message(format_awards_message(week, awards), bot_id=bot_id)


def format_faab_message(report, awards: list) -> str:
    from .faab_report import format_faab_table
    lines = [format_faab_table(report)]
    if awards:
        lines.append("")
        for title, line in awards:
            lines.append(f"{title}: {line}")
    return "\n".join(lines)


def post_faab_report(report, awards: list = None, bot_id: str = None):
    post_message(format_faab_message(report, awards or []), bot_id=bot_id)


def post_faab_report_image(week: int, image_path: str, awards: list = None,
                            bot_id: str = None, access_token: str = None):
    """Posts the FAAB table as an image; awards/banter still go out as a
    separate plain-text message right after, same as the rankings+awards
    pairing -- these always post together in the same run."""
    post_image_message(f"Week {week} FAAB Report \U0001F4B0", image_path,
                        bot_id=bot_id, access_token=access_token)
    if awards:
        awards_lines = [f"{title}: {line}" for title, line in awards]
        post_message("\n".join(awards_lines), bot_id=bot_id)


def format_predictions_message(week: int, predictions: list, banter_lines: list = None) -> str:
    lines = [f"\U0001F52E CLOSE ENOUGH FOR NOW: WEEK {week} PREDICTIONS \U0001F52E"]
    for p in predictions:
        tag = {"Lock": "\U0001F512", "Favored": "", "Toss-Up": "\U0001FA99"}.get(p.confidence, "")
        lines.append(
            f"{p.home_team} ({p.home_projected}, {p.home_win_pct}%) vs "
            f"{p.away_team} ({p.away_projected}, {p.away_win_pct}%) {tag} {p.confidence}"
        )
    if banter_lines:
        lines.append("")
        for title, line in banter_lines:
            lines.append(f"{title}: {line}")
    return "\n".join(lines)


def post_predictions(week: int, predictions: list, banter_lines: list = None, bot_id: str = None):
    post_message(format_predictions_message(week, predictions, banter_lines), bot_id=bot_id)


def post_predictions_image(week: int, image_path: str, banter_lines: list = None,
                            bot_id: str = None, access_token: str = None):
    """Posts the matchup predictions as an image; banter still goes out as
    a separate plain-text message right after, same run."""
    post_image_message(f"Week {week} Predictions \U0001F52E", image_path,
                        bot_id=bot_id, access_token=access_token)
    if banter_lines:
        lines = [f"{title}: {line}" for title, line in banter_lines]
        post_message("\n".join(lines), bot_id=bot_id)
