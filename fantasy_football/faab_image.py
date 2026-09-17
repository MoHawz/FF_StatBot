"""
Renders the Wednesday FAAB report as a single PNG graphic, matching the look
of rankings_image.py -- same motivation: GroupMe collapses long text behind
"Read more...", so the claims + budgets table becomes one glanceable card
instead of a wall of text. Posting requires GROUPME_ACCESS_TOKEN (see
SETUP.md); groupme_bot.post_faab_report_image() handles the upload.

The accompanying banter/awards stay as a separate plain-text GroupMe message,
same as today -- only the table itself becomes an image.
"""
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

from . import config
from .faab_report import FaabReport

WIDTH = 900
HEADER_HEIGHT = 130
SECTION_HEADER_HEIGHT = 46
CLAIM_ROW_HEIGHT = 78
BUDGET_ROW_HEIGHT = 46
FOOTER_HEIGHT = 40
PADDING = 24

COLOR_BG = (18, 28, 43)
COLOR_HEADER = (31, 58, 95)
COLOR_SECTION = (26, 40, 61)
COLOR_ROW_A = (26, 40, 61)
COLOR_ROW_B = (32, 48, 72)
COLOR_TEXT = (240, 240, 240)
COLOR_SUBTEXT = (160, 172, 190)
COLOR_ACCENT = (222, 178, 58)      # gold, biggest overpay / big spender
COLOR_GREEN = (86, 200, 120)       # bargain / healthy budget
COLOR_RED = (220, 90, 90)          # overpaid / low budget

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(f"{FONT_DIR}{name}", size)
    except OSError:
        return ImageFont.load_default()


F_TITLE = _font("DejaVuSans-Bold.ttf", 36)
F_SUB = _font("DejaVuSans.ttf", 20)
F_SECTION = _font("DejaVuSans-Bold.ttf", 22)
F_PLAYER = _font("DejaVuSans-Bold.ttf", 24)
F_DETAIL = _font("DejaVuSans.ttf", 17)
F_PAID = _font("DejaVuSans-Bold.ttf", 26)
F_TEAM = _font("DejaVuSans.ttf", 19)
F_TAG = _font("DejaVuSans-Bold.ttf", 16)


def render_faab_report(week: int, report: FaabReport, out_path: str, subtitle: Optional[str] = None) -> str:
    claims = report.claims
    budgets = report.budgets

    claims_height = SECTION_HEADER_HEIGHT + max(1, len(claims)) * CLAIM_ROW_HEIGHT
    budgets_height = SECTION_HEADER_HEIGHT + len(budgets) * BUDGET_ROW_HEIGHT
    height = HEADER_HEIGHT + claims_height + budgets_height + FOOTER_HEIGHT

    img = Image.new("RGB", (WIDTH, height), COLOR_BG)
    draw = ImageDraw.Draw(img)

    # header
    draw.rectangle([0, 0, WIDTH, HEADER_HEIGHT], fill=COLOR_HEADER)
    draw.text((PADDING, 30), f"WEEK {week} FAAB REPORT", font=F_TITLE, fill=COLOR_TEXT)
    draw.text((PADDING, 82), subtitle or config.LEAGUE_DISPLAY_NAME, font=F_SUB, fill=COLOR_SUBTEXT)

    y = HEADER_HEIGHT

    # claims section
    draw.rectangle([0, y, WIDTH, y + SECTION_HEADER_HEIGHT], fill=COLOR_SECTION)
    draw.text((PADDING, y + 10), "CONTESTED CLAIMS", font=F_SECTION, fill=COLOR_ACCENT)
    y += SECTION_HEADER_HEIGHT

    if not claims:
        draw.rectangle([0, y, WIDTH, y + CLAIM_ROW_HEIGHT], fill=COLOR_ROW_A)
        draw.text((PADDING, y + 28), "No contested waiver claims this week.", font=F_DETAIL, fill=COLOR_SUBTEXT)
        y += CLAIM_ROW_HEIGHT
    else:
        max_overpaid = max((c.overpaid for c in claims), default=1) or 1
        for i, c in enumerate(claims):
            y0 = y
            draw.rectangle([0, y0, WIDTH, y0 + CLAIM_ROW_HEIGHT], fill=(COLOR_ROW_A if i % 2 == 0 else COLOR_ROW_B))

            draw.text((PADDING, y0 + 12), c.player, font=F_PLAYER, fill=COLOR_TEXT)
            draw.text((PADDING, y0 + 44),
                       f"{c.winning_team}  •  {c.bidders} bidder{'s' if c.bidders != 1 else ''}",
                       font=F_TEAM, fill=COLOR_SUBTEXT)

            paid_text = f"${c.paid}"
            ptw = draw.textlength(paid_text, font=F_PAID)
            paid_x = WIDTH - PADDING - 170
            draw.text((paid_x - ptw, y0 + 14), paid_text, font=F_PAID, fill=COLOR_TEXT)

            if c.overpaid == c.paid:
                tag_text, tag_color = "UNCONTESTED", COLOR_SUBTEXT
            elif c.overpaid >= max_overpaid * 0.6 and c.overpaid >= 10:
                tag_text, tag_color = f"OVERPAID +${c.overpaid}", COLOR_ACCENT
            else:
                tag_text, tag_color = f"beat next by ${c.overpaid}", COLOR_SUBTEXT
            ttw = draw.textlength(tag_text, font=F_TAG)
            draw.text((WIDTH - PADDING - ttw, y0 + 48), tag_text, font=F_TAG, fill=tag_color)

            y += CLAIM_ROW_HEIGHT

    # budgets section
    draw.rectangle([0, y, WIDTH, y + SECTION_HEADER_HEIGHT], fill=COLOR_SECTION)
    draw.text((PADDING, y + 10), "BUDGETS REMAINING", font=F_SECTION, fill=COLOR_ACCENT)
    y += SECTION_HEADER_HEIGHT

    max_budget = max((b.remaining_budget for b in budgets), default=1) or 1
    for i, b in enumerate(budgets):
        y0 = y
        draw.rectangle([0, y0, WIDTH, y0 + BUDGET_ROW_HEIGHT], fill=(COLOR_ROW_A if i % 2 == 0 else COLOR_ROW_B))

        draw.text((PADDING, y0 + 12), b.team, font=F_TEAM, fill=COLOR_TEXT)

        bar_x0, bar_w, bar_y, bar_h = 300, 220, y0 + 18, 10
        draw.rounded_rectangle([bar_x0, bar_y, bar_x0 + bar_w, bar_y + bar_h], radius=5, fill=(52, 68, 94))
        frac = max(0.0, min(1.0, b.remaining_budget / max_budget))
        fill_w = max(4, int(bar_w * frac))
        bar_color = COLOR_RED if frac < 0.25 else (COLOR_ACCENT if frac < 0.5 else COLOR_GREEN)
        draw.rounded_rectangle([bar_x0, bar_y, bar_x0 + fill_w, bar_y + bar_h], radius=5, fill=bar_color)

        # amount pinned right after the bar (fixed spot, not right-aligned to
        # the far edge) so it never collides with the Big Spender tag
        amt_text = f"${b.remaining_budget}"
        draw.text((bar_x0 + bar_w + 24, y0 + 13), amt_text, font=F_DETAIL, fill=COLOR_TEXT)

        if b.is_big_spender:
            tag_text = "BIG SPENDER"
            ttw = draw.textlength(tag_text, font=F_TAG)
            draw.text((WIDTH - PADDING - ttw, y0 + 13), tag_text, font=F_TAG, fill=COLOR_ACCENT)

        y += BUDGET_ROW_HEIGHT

    draw.text((PADDING, height - FOOTER_HEIGHT + 8), f"{config.BOT_NAME}'s FAAB Report",
               font=F_DETAIL, fill=COLOR_SUBTEXT)

    img.save(out_path, "PNG")
    return out_path
