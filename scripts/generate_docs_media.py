#!/usr/bin/env python3
"""Generate small, reproducible GIF assets for the public docs."""

from __future__ import annotations

from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
SIZE = (860, 484)


COLORS = {
    "bg": "#050607",
    "panel": "#0e1116",
    "panel_2": "#17120c",
    "paper": "#fff4b8",
    "paper_2": "#fffdf1",
    "ink": "#f7f0d8",
    "muted": "#9ca3af",
    "blue": "#5b8cff",
    "green": "#54c79d",
    "yellow": "#ffd342",
    "red": "#ff6d5f",
    "border": "#17120c",
}


def _font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = []
    if mono:
        candidates.extend(
            [
                "/System/Library/Fonts/Menlo.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            ]
        )
    if bold:
        candidates.extend(
            [
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            ]
        )
    candidates.extend(
        [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


FONT_TITLE = _font(24, bold=True)
FONT_SUBTITLE = _font(15)
FONT_MONO = _font(16, mono=True)
FONT_MONO_SMALL = _font(13, mono=True)
FONT_MONO_BOLD = _font(16, bold=True, mono=True)


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if draw.textbbox((0, 0), candidate, font=font)[2] <= width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def _draw_text_block(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    line_gap: int = 6,
) -> int:
    x, y = xy
    for line in _fit_text(draw, text, font, max_width):
        draw.text((x, y), line, font=font, fill=fill)
        y += draw.textbbox((0, 0), line, font=font)[3] + line_gap
    return y


def _save_gif(frames: list[Image.Image], path: Path, duration: int = 1350) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    palette_frames = [frame.convert("P", palette=Image.Palette.ADAPTIVE) for frame in frames]
    palette_frames[0].save(
        path,
        save_all=True,
        append_images=palette_frames[1:],
        duration=duration,
        loop=0,
        optimize=True,
        disposal=2,
    )


def _window_frame(title: str, subtitle: str = "") -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", SIZE, COLORS["paper"])
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, SIZE[0] - 1, SIZE[1] - 1), fill=COLORS["paper"], outline=COLORS["border"], width=4)
    draw.rectangle((4, 4, SIZE[0] - 5, 54), fill=COLORS["paper_2"], outline=COLORS["border"], width=2)
    for x, color in [(24, COLORS["red"]), (48, COLORS["yellow"]), (72, COLORS["green"])]:
        draw.ellipse((x, 21, x + 13, 34), fill=color, outline=COLORS["border"], width=2)
    draw.text((102, 18), title, font=FONT_TITLE, fill=COLORS["border"])
    if subtitle:
        draw.text((102, 56), subtitle, font=FONT_SUBTITLE, fill=COLORS["muted"])
    return image, draw


def _make_ui_tour() -> None:
    shots = [
        ("Start with prompts", "The local viewer gives a human-readable front door.", "link-home-dark.png"),
        ("Ingest safely", "Raw files are scanned, represented, and validated.", "link-ingest-dark.png"),
        ("Brief before work", "Agents get compact, source-backed context.", "link-brief-dark.png"),
        ("Review memory", "Memories are inspectable, explainable, and reversible.", "link-memory-dashboard-dark.png"),
        ("Explore the graph", "Large graphs open bounded first, then expand on demand.", "link-graph-dark.png"),
    ]
    frames: list[Image.Image] = []
    for title, caption, filename in shots:
        screenshot = Image.open(ASSETS / filename).convert("RGB").resize(SIZE)
        overlay = Image.new("RGBA", SIZE, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.rectangle((0, 0, SIZE[0], 76), fill=(0, 0, 0, 220))
        draw.text((28, 15), title, font=FONT_TITLE, fill=COLORS["ink"])
        draw.text((28, 45), caption, font=FONT_SUBTITLE, fill="#d1d5db")
        frames.append(Image.alpha_composite(screenshot.convert("RGBA"), overlay).convert("RGB"))
    _save_gif(frames, ASSETS / "link-ui-tour.gif")
    _save_gif(frames, ASSETS / "link-product-tour-dark.gif")


def _terminal_frame(title: str, lines: list[tuple[str, str]]) -> Image.Image:
    image, draw = _window_frame(title, "CLI commands stay local and scriptable.")
    draw.rectangle((34, 96, SIZE[0] - 34, SIZE[1] - 34), fill=COLORS["bg"], outline=COLORS["border"], width=3)
    y = 122
    for kind, line in lines:
        color = {
            "prompt": COLORS["green"],
            "cmd": "#93c5fd",
            "ok": COLORS["ink"],
            "muted": "#9ca3af",
            "warn": COLORS["yellow"],
        }.get(kind, COLORS["ink"])
        prefix = "$ " if kind == "cmd" else "  "
        for wrapped in wrap(line, width=78) or [""]:
            draw.text((58, y), prefix + wrapped if wrapped == line else "  " + wrapped, font=FONT_MONO, fill=color)
            y += 25
        y += 4
    return image


def _make_cli_tour() -> None:
    frames = [
        _terminal_frame(
            "1. Check readiness",
            [
                ("cmd", "link status --validate"),
                ("ok", "Ready: yes"),
                ("ok", "Pages: 25 · Memories: 1 active · Search: sqlite-fts"),
                ("muted", "Next: query, brief, ingest, or serve the local viewer."),
            ],
        ),
        _terminal_frame(
            "2. Ask for compact context",
            [
                ("cmd", 'link query "why does Link help agents?" --budget small'),
                ("ok", "Answer-ready packet: 3 memories, 5 pages, graph neighborhood."),
                ("muted", "has_more: true · follow_up: widen budget or open context."),
            ],
        ),
        _terminal_frame(
            "3. Prime an agent",
            [
                ("cmd", 'link brief "working on Link release" --project link'),
                ("ok", "Relevant decisions, preferences, open review items, and project context."),
                ("muted", "Local Markdown. No hosted memory service."),
            ],
        ),
        _terminal_frame(
            "4. Prove scale locally",
            [
                ("cmd", 'link benchmark "agent memory"'),
                ("ok", "cache 0.10s · search 0.009s · query 0.018s · graph 0.022s"),
                ("ok", "Verdict: interactive"),
            ],
        ),
    ]
    _save_gif(frames, ASSETS / "link-cli-tour.gif", duration=1450)


def _bubble(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    width: int,
    title: str,
    body: str,
    fill: str,
    accent: str,
) -> int:
    x, y = xy
    draw.rounded_rectangle((x, y, x + width, y + 114), radius=14, fill=fill, outline=accent, width=3)
    draw.text((x + 18, y + 14), title, font=FONT_MONO_BOLD, fill=accent)
    return _draw_text_block(draw, (x + 18, y + 45), body, FONT_SUBTITLE, COLORS["ink"], width - 36)


def _mcp_frame(title: str, step: str, calls: list[tuple[str, str, str]]) -> Image.Image:
    image, draw = _window_frame(title, step)
    x_positions = [40, 330]
    y_positions = [110, 260]
    for index, (name, body, tone) in enumerate(calls):
        x = x_positions[index % 2]
        y = y_positions[index // 2]
        accent = COLORS["blue"] if tone == "tool" else COLORS["green"]
        fill = "#e8edff" if tone == "tool" else "#dff8ef"
        _bubble(draw, (x, y), 250 if index % 2 == 0 else 490, name, body, fill, accent)
    return image


def _make_mcp_tour() -> None:
    frames = [
        _mcp_frame(
            "1. User asks naturally",
            "No path memorization required.",
            [
                ("User", "is Link ready?", "user"),
                ("MCP tool", "link_status checks schema, pages, search backend, and safe next actions.", "tool"),
            ],
        ),
        _mcp_frame(
            "2. Agent primes itself",
            "The packet is small by design.",
            [
                ("User", "brief me from Link before we continue", "user"),
                ("MCP tool", "memory_brief returns relevant memories, project context, review warnings, and rules.", "tool"),
            ],
        ),
        _mcp_frame(
            "3. Agent queries smart context",
            "No whole-wiki dump.",
            [
                ("User", "query Link for release process", "user"),
                ("MCP tool", "query_link returns budgeted memory, pages, graph context, why_selected, and follow-ups.", "tool"),
            ],
        ),
        _mcp_frame(
            "4. Agent keeps memory healthy",
            "Writes are reviewable.",
            [
                ("User", "remember that I prefer short release notes", "user"),
                ("MCP tool", "remember_memory checks duplicates/conflicts, writes Markdown, and logs the change.", "tool"),
            ],
        ),
    ]
    _save_gif(frames, ASSETS / "link-mcp-tour.gif", duration=1500)


def main() -> None:
    _make_ui_tour()
    _make_cli_tour()
    _make_mcp_tour()
    print("Generated docs GIFs:")
    for name in ["link-ui-tour.gif", "link-cli-tour.gif", "link-mcp-tour.gif", "link-product-tour-dark.gif"]:
        print(f"- docs/assets/{name}")


if __name__ == "__main__":
    main()
