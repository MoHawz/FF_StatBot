"""
Renders the Wednesday FAAB report as a single PNG graphic, matching the look
of rankings_image.py -- same motivation: GroupMe collapses long text behind
"Read more...", so the claims + budgets table becomes one glanceable card
instead of a wall of text. Posting requires GROUPME_ACCESS_TOKEN (see
SETUP.md); groupme_bot.post_faab_report_image() handles the upload.

The accompanying banter/awards stay as a separate plain-text GroupMe message,
same as today -- only the table itself becomes an image.

Colors and the optional logo come from branding.py / config.LOGO_PATH.
"""
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from . import branding, config
from .faab_report import FaabReport

WIDTH = 900
HEADER_HEIGHT = 130
SECTION_HEADER_HEIGHT = 46
CLAIM_ROW_HEIGHT = 78
BUDGET_ROW_HEIGHT = 46
FOOTER_HEIGHT = 40
PADDING = 24

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

    img = Image.new("RGBA", (WIDTH, height), branding.BLACK + (255,))
    draw = ImageDraw.Draw(img)
    logo = branding.load_logo()

    # header
    draw.rectangle([0, 0, WIDTH, HEADER_HEIGHT], fill=branding.MAROON)
    if logo:
        branding.paste_watermark(img, logo, box=(WIDTH - 340, 0, WIDTH, HEADER_HEIGHT), opacity=0.16)
    draw.text((PADDING, 30), f"WEEK {week} FAAB REPORT", font=F_TITLE, fill=branding.WHITE)
    draw.text((PADDING, 82), subtitle or config.LEAGUE_DISPLAY_NAME, font=F_SUB, fill=branding.WHITE)
    if logo:
        branding.paste_badge(img, logo, size=76, margin=16)

    y = HEADER_HEIGHT

    # claims section
    draw.rectangle([0, y, WIDTH, y + SECTION_HEADER_HEIGHT], fill=branding.ROW_B)
    draw.text((PADDING, y + 10), "CONTESTED CLAIMS", font=F_SECTION, fill=branding.WHITE)
    y += SECTION_HEADER_HEIGHT

    if not claims:
        draw.rectangle([0, y, WIDTH, y + CLAIM_ROW_HEIGHT], fill=branding.ROW_A)
        draw.text((PADDING, y + 28), "No contested waiver claims this week.", font=F_DETAIL, fill=branding.GRAY_SUBTEXT)
        y += CLAIM_ROW_HEIGHT
    else:
        max_overpaid = max((c.overpaid for c in claims), default=1) or 1
        for i, c in enumerate(claims):
            y0 = y
            draw.rectangle([0, y0, WIDTH, y0 + CLAIM_ROW_HEIGHT], fill=(branding.ROW_A if i % 2 == 0 else branding.ROW_B))

            draw.text((PADDING, y0 + 12), c.player, font=F_PLAYER, fill=branding.WHITE)
            draw.text((PADDING, y0 + 44),
                       f"{c.winning_team}  •  {c.bidders} bidder{'s' if c.bidders != 1 else ''}",
                       font=F_TEAM, fill=branding.GRAY_SUBTEXT)

            paid_text = f"${c.paid}"
            ptw = draw.textlength(paid_text, font=F_PAID)
            paid_x = WIDTH - PADDING - 170
            draw.text((paid_x - ptw, y0 + 14), paid_text, font=F_PAID, fill=branding.WHITE)

            if c.overpaid == c.paid:
                tag_text, tag_color = "UNCONTESTED", branding.GRAY_SUBTEXT
            elif c.overpaid >= max_overpaid * 0.6 and c.overpaid >= 10:
                tag_text, tag_color = f"OVERPAID +${c.overpaid}", branding.WHITE
            else:
                tag_text, tag_color = f"beat next by ${c.overpaid}", branding.GRAY_SUBTEXT
            ttw = draw.textlength(tag_text, font=F_TAG)
            draw.text((WIDTH - PADDING - ttw, y0 + 48), tag_text, font=F_TAG, fill=tag_color)

            y += CLAIM_ROW_HEIGHT

    # budgets section
    draw.rectangle([0, y, WIDTH, y + SECTION_HEADER_HEIGHT], fill=branding.ROW_B)
    draw.text((PADDING, y + 10), "BUDGETS REMAINING", font=F_SECTION, fill=branding.WHITE)
    y += SECTION_HEADER_HEIGHT

    max_budget = max((b.remaining_budget for b in budgets), default=1) or 1
    for i, b in enumerate(budgets):
        y0 = y
        draw.rectangle([0, y0, WIDTH, y0 + BUDGET_ROW_HEIGHT], fill=(branding.ROW_A if i % 2 == 0 else branding.ROW_B))

        draw.text((PADDING, y0 + 12), b.team, font=F_TEAM, fill=branding.WHITE)

        bar_x0, bar_w, bar_y, bar_h = 300, 220, y0 + 18, 10
        draw.rounded_rectangle([bar_x0, bar_y, bar_x0 + bar_w, bar_y + bar_h], radius=5, fill=branding.GRAY_TRACK)
        frac = max(0.0, min(1.0, b.remaining_budget / max_budget))
        fill_w = max(4, int(bar_w * frac))
        bar_color = branding.STATUS_BAD if frac < 0.25 else (branding.MAROON_LIGHT if frac < 0.5 else branding.STATUS_GOOD)
        draw.rounded_rectangle([bar_x0, bar_y, bar_x0 + fill_w, bar_y + bar_h], radius=5, fill=bar_color)

        # amount pinned right after the bar (fixed spot, not right-aligned to
        # the far edge) so it never collides with the Big Spender tag
        amt_text = f"${b.remaining_budget}"
        draw.text((bar_x0 + bar_w + 24, y0 + 13), amt_text, font=F_DETAIL, fill=branding.WHITE)

        if b.is_big_spender:
            tag_text = "BIG SPENDER"
            ttw = draw.textlength(tag_text, font=F_TAG)
            draw.text((WIDTH - PADDING - ttw, y0 + 13), tag_text, font=F_TAG, fill=branding.WHITE)

        y += BUDGET_ROW_HEIGHT

    draw.text((PADDING, height - FOOTER_HEIGHT + 8), f"{config.BOT_NAME}'s FAAB Report",
               font=F_DETAIL, fill=branding.GRAY_SUBTEXT)

    img.convert("RGB").save(out_path, "PNG")
    return out_path
