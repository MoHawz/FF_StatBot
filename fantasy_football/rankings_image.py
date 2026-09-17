"""
Renders the weekly power rankings as a single PNG graphic instead of a wall
of text. GroupMe collapses long text messages behind a "Read more..." tap,
which is exactly the readability complaint this solves -- an image posts as
one glanceable card with no truncation, closer to the old screenshot-a-
spreadsheet habit but built fresh from the live data every week.

Posting it as an actual inline image in GroupMe (not just a link) requires
uploading through GroupMe's own Image Service, which needs a personal
access token (not the bot_id) -- see SETUP.md for the two-minute steps to
grab one. groupme_bot.post_power_rankings_image() handles the upload +
posting once that token is in `.env`.
"""
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

from . import config
from .power_rankings import PowerRankingRow

WIDTH = 900
ROW_HEIGHT = 92
HEADER_HEIGHT = 130
FOOTER_HEIGHT = 40
PADDING = 24

COLOR_BG = (18, 28, 43)          # near-black navy
COLOR_HEADER = (31, 58, 95)      # dark navy accent -- swap freely, purely visual
COLOR_ROW_A = (26, 40, 61)
COLOR_ROW_B = (32, 48, 72)
COLOR_TEXT = (240, 240, 240)
COLOR_SUBTEXT = (160, 172, 190)
COLOR_UP = (86, 200, 120)
COLOR_DOWN = (220, 90, 90)
COLOR_FLAT = (140, 150, 165)
COLOR_ACCENT = (222, 178, 58)     # gold, for #1
COLOR_BAR_BG = (52, 68, 94)

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(f"{FONT_DIR}{name}", size)
    except OSError:
        return ImageFont.load_default()


F_TITLE = _font("DejaVuSans-Bold.ttf", 36)
F_SUB = _font("DejaVuSans.ttf", 20)
F_RANK = _font("DejaVuSans-Bold.ttf", 30)
F_TEAM = _font("DejaVuSans-Bold.ttf", 26)
F_OWNER = _font("DejaVuSans.ttf", 18)
F_SCORE = _font("DejaVuSans-Bold.ttf", 30)
F_DETAIL = _font("DejaVuSans.ttf", 17)
F_ARROW = _font("DejaVuSans-Bold.ttf", 18)


def _movement_text(movement: int):
    if movement > 0:
        return f"▲ {movement}", COLOR_UP
    if movement < 0:
        return f"▼ {abs(movement)}", COLOR_DOWN
    return "—", COLOR_FLAT


def render_power_rankings(
    week: int,
    rows: List[PowerRankingRow],
    out_path: str,
    subtitle: Optional[str] = None,
) -> str:
    height = HEADER_HEIGHT + ROW_HEIGHT * len(rows) + FOOTER_HEIGHT
    img = Image.new("RGB", (WIDTH, height), COLOR_BG)
    draw = ImageDraw.Draw(img)

    # header
    draw.rectangle([0, 0, WIDTH, HEADER_HEIGHT], fill=COLOR_HEADER)
    draw.text((PADDING, 30), f"WEEK {week} POWER RANKINGS", font=F_TITLE, fill=COLOR_TEXT)
    draw.text((PADDING, 82), subtitle or config.LEAGUE_DISPLAY_NAME, font=F_SUB, fill=COLOR_SUBTEXT)

    max_score = max((r.power_score for r in rows), default=1) or 1

    for i, r in enumerate(rows):
        y0 = HEADER_HEIGHT + i * ROW_HEIGHT
        y1 = y0 + ROW_HEIGHT
        draw.rectangle([0, y0, WIDTH, y1], fill=(COLOR_ROW_A if i % 2 == 0 else COLOR_ROW_B))

        # rank circle
        cx, cy, r_rad = 56, y0 + ROW_HEIGHT // 2, 30
        circle_color = COLOR_ACCENT if r.rank == 1 else COLOR_BAR_BG
        draw.ellipse([cx - r_rad, cy - r_rad, cx + r_rad, cy + r_rad], fill=circle_color)
        rank_text = str(r.rank)
        tw = draw.textlength(rank_text, font=F_RANK)
        draw.text((cx - tw / 2, cy - 18), rank_text, font=F_RANK, fill=(20, 20, 20) if r.rank == 1 else COLOR_TEXT)

        # team + owner
        tx = 104
        draw.text((tx, y0 + 16), r.team_name, font=F_TEAM, fill=COLOR_TEXT)
        draw.text((tx, y0 + 50), f"{r.owner}  •  {r.wins}-{r.losses}{'-' + str(r.ties) if r.ties else ''}  •  {r.ppg} ppg",
                   font=F_OWNER, fill=COLOR_SUBTEXT)

        # power score bar (visual, quick scan of "how far ahead")
        bar_x0, bar_w, bar_y, bar_h = tx, 320, y0 + 74, 10
        draw.rounded_rectangle([bar_x0, bar_y, bar_x0 + bar_w, bar_y + bar_h], radius=5, fill=COLOR_BAR_BG)
        fill_w = max(6, int(bar_w * (r.power_score / max_score)))
        bar_color = COLOR_ACCENT if r.rank == 1 else (90, 140, 210)
        draw.rounded_rectangle([bar_x0, bar_y, bar_x0 + fill_w, bar_y + bar_h], radius=5, fill=bar_color)

        # score + movement, right-aligned
        score_text = f"{r.power_score}"
        stw = draw.textlength(score_text, font=F_SCORE)
        score_x = WIDTH - PADDING - 90
        draw.text((score_x - stw, y0 + 22), score_text, font=F_SCORE, fill=COLOR_TEXT)

        move_text, move_color = _movement_text(r.movement)
        mtw = draw.textlength(move_text, font=F_ARROW)
        draw.text((WIDTH - PADDING - mtw, y0 + 58), move_text, font=F_ARROW, fill=move_color)

    draw.text((PADDING, height - FOOTER_HEIGHT + 8), f"{config.BOT_NAME}'s Power Rankings",
               font=F_DETAIL, fill=COLOR_SUBTEXT)

    img.save(out_path, "PNG")
    return out_path
