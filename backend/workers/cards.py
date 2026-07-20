"""Render branded post images (PNG) for LinkedIn — several types, no AI image model.

Types: stat_card, tweet (a clean X-style screenshot), quote, comparison (two-panel), list.
Just typography on the brand, so it reads deliberate. Best-effort: if Pillow or a font is
missing, returns None and the post goes out without an image.
"""
from __future__ import annotations

import io
from typing import Any

BG = (11, 11, 12)
WHITE = (244, 244, 245)
MUTED = (150, 150, 155)
SKY = (56, 189, 248)
INK = (15, 20, 25)          # tweet text (near-black)
TW_GRAY = (83, 100, 113)    # twitter secondary text
TW_BLUE = (29, 155, 240)
# X (Twitter) dark "lights out" palette — the tweet card mimics a real dark-mode screenshot.
X_CANVAS = (0, 0, 0)         # page behind the card
X_CARD = (22, 24, 28)        # #16181C the tweet surface (subtle elevation)
X_TEXT = (231, 233, 234)     # #E7E9EA primary text
X_DIM = (113, 118, 123)      # #71767B handle / metric labels
X_LINE = (47, 51, 54)        # #2F3336 divider + card border
X_BLUE = (29, 155, 240)      # #1D9BF0 verified badge
W = H = 1080
M = 96

_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "DejaVuSans-Bold.ttf",
]
_REG = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "DejaVuSans.ttf",
]
_AVATAR = [(56, 189, 248), (16, 185, 129), (244, 114, 182), (251, 191, 36), (167, 139, 250)]


def _font(paths: list[str], size: int):
    from PIL import ImageFont

    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def _wrap(draw, text: str, font, maxw: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for word in (text or "").split():
        trial = f"{cur} {word}".strip()
        if not cur or draw.textlength(trial, font=font) <= maxw:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _lh(font) -> int:
    asc, desc = font.getmetrics()
    return int((asc + desc) * 1.16)


def _fit(draw, text: str, paths: list[str], maxw: int, maxh: int, hi: int, lo: int):
    fallback = None
    size = hi
    while size >= lo:
        f = _font(paths, size)
        lines = _wrap(draw, text, f, maxw)
        if _lh(f) * len(lines) <= maxh and all(draw.textlength(ln, font=f) <= maxw for ln in lines):
            return f, lines
        fallback = (f, lines)
        size -= 5
    return fallback


def _wordmark(d, color=WHITE):
    f = _font(_BOLD, 36)
    label = "Agentry"
    lw = d.textlength(label, font=f)
    r = 8
    bw = r * 2 + 14 + lw
    x0 = (W - bw) / 2
    cy = H - 92
    d.ellipse([x0, cy + 8, x0 + r * 2, cy + 8 + r * 2], fill=SKY)
    d.text((x0 + r * 2 + 14, cy), label, font=f, fill=color)


def _save(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _avatar_color(name: str) -> tuple[int, int, int]:
    return _AVATAR[sum((name or "A").encode("utf-8", "ignore")) % len(_AVATAR)]


def _count(n) -> str:
    """Human count like X shows: 1200 -> 1.2K, 3400000 -> 3.4M."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}".rstrip("0").rstrip(".") + "K"
    return str(n)


def _new():
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (W, H), BG)
    return img, ImageDraw.Draw(img)


def render_stat_card(spec: dict) -> bytes | None:
    top, big, bottom = spec.get("top", ""), spec.get("big", ""), spec.get("bottom", "")
    if not (top or big or bottom):
        return None
    img, d = _new()
    blocks = []
    if top:
        f = _font(_REG, 44)
        blocks.append((_wrap(d, top, f, W - 2 * M), f, MUTED))
    if big:
        f, lines = _fit(d, big, _BOLD, W - 2 * M, 560, 132, 54)
        blocks.append((lines, f, WHITE))
    if bottom:
        f = _font(_REG, 50)
        blocks.append((_wrap(d, bottom, f, W - 2 * M), f, SKY))
    total = sum(_lh(f) * len(lines) + 30 for lines, f, _c in blocks)
    y = max(M, (H - 130 - total) // 2)
    for lines, f, color in blocks:
        for ln in lines:
            d.text(((W - d.textlength(ln, font=f)) / 2, y), ln, font=f, fill=color)
            y += _lh(f)
        y += 30
    _wordmark(d)
    return _save(img)


def render_quote(spec: dict) -> bytes | None:
    quote = spec.get("quote") or spec.get("big") or spec.get("text") or ""
    author = spec.get("author") or ""
    if not quote:
        return None
    img, d = _new()
    qf = _font(_BOLD, 200)
    d.text((M - 10, M - 60), '"', font=qf, fill=SKY)
    f, lines = _fit(d, quote, _BOLD, W - 2 * M, 540, 96, 48)
    total = _lh(f) * len(lines)
    y = max(M + 120, (H - 120 - total) // 2)
    for ln in lines:
        d.text(((W - d.textlength(ln, font=f)) / 2, y), ln, font=f, fill=WHITE)
        y += _lh(f)
    if author:
        af = _font(_REG, 46)
        y += 24
        d.text(((W - d.textlength(author, font=af)) / 2, y), author, font=af, fill=SKY)
    _wordmark(d)
    return _save(img)


def render_comparison(spec: dict) -> bytes | None:
    left, right = spec.get("left") or "", spec.get("right") or ""
    if not (left or right):
        return None
    img, d = _new()
    title = spec.get("title") or ""
    if title:
        tf = _font(_REG, 42)
        d.text(((W - d.textlength(title, font=tf)) / 2, M - 20), title, font=tf, fill=MUTED)
    d.line([(W / 2, 240), (W / 2, H - 200)], fill=(40, 40, 44), width=2)

    def panel(x0, label, value, accent):
        half = W / 2
        maxw = int(half - 2 * 60)
        if label:
            lf = _font(_REG, 36)
            d.text((x0 + (half - d.textlength(label, font=lf)) / 2, 300), label, font=lf, fill=MUTED)
        vf, lines = _fit(d, value, _BOLD, maxw, 420, 92, 40)
        total = _lh(vf) * len(lines)
        y = (H - total) / 2
        for ln in lines:
            d.text((x0 + (half - d.textlength(ln, font=vf)) / 2, y), ln, font=vf, fill=accent)
            y += _lh(vf)

    panel(0, spec.get("left_label") or "", left, WHITE)
    panel(W / 2, spec.get("right_label") or "", right, SKY)
    _wordmark(d)
    return _save(img)


def render_list(spec: dict) -> bytes | None:
    items = [str(i) for i in (spec.get("items") or []) if str(i).strip()][:6]
    if not items:
        return None
    img, d = _new()
    title = spec.get("title") or ""
    y = M
    if title:
        tf, tlines = _fit(d, title, _BOLD, W - 2 * M, 220, 70, 44)
        for ln in tlines:
            d.text((M, y), ln, font=tf, fill=WHITE)
            y += _lh(tf)
        y += 40
    nf = _font(_BOLD, 40)
    itf = _font(_REG, 44)
    avail = H - 140 - y
    gap = max(18, min(40, (avail - sum(len(_wrap(d, it, itf, W - 2 * M - 70)) for it in items) * _lh(itf)) // max(1, len(items))))
    for i, it in enumerate(items, 1):
        d.text((M, y + 4), f"{i}", font=nf, fill=SKY)
        for ln in _wrap(d, it, itf, W - 2 * M - 70):
            d.text((M + 70, y), ln, font=itf, fill=WHITE)
            y += _lh(itf)
        y += gap
    _wordmark(d)
    return _save(img)


def _sized(url: str) -> str:
    """Ask X's CDN for a bounded variant so we don't pull multi-MB originals."""
    if "pbs.twimg.com/media/" in url and "name=" not in url and "?" not in url:
        return url + "?format=jpg&name=medium"  # medium ≈ 1200px on the long edge
    return url


def _fetch_media(items: list, *, timeout: float = 8.0) -> list:
    """Download attached media as (RGB image, kind) tuples. Best-effort: any failure drops the item.

    `items` may be {"url","kind"} dicts (photo/video/gif) or bare url strings (treated as photos).
    A video/GIF has no still of its own, so we fetch its poster frame and tag it for a play badge.
    """
    out: list = []
    if not items:
        return out
    try:
        import httpx
        from PIL import Image
    except Exception:  # noqa: BLE001
        return out
    norm: list = []
    for it in items[:4]:
        if isinstance(it, dict):
            u, kind = it.get("url"), (it.get("kind") or "photo")
        else:
            u, kind = it, "photo"
        if isinstance(u, str) and u.startswith("http"):
            norm.append((u, kind))
    # pbs.twimg.com occasionally 403s a bare client; a normal browser UA sidesteps that.
    ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=ua) as c:
            for u, kind in norm:
                try:
                    r = c.get(_sized(u))
                    r.raise_for_status()
                    out.append((Image.open(io.BytesIO(r.content)).convert("RGB"), kind))
                except Exception:  # noqa: BLE001
                    continue
    except Exception:  # noqa: BLE001
        return out
    return out


def _cover(im, w: int, h: int):
    """Scale + center-crop `im` to exactly (w, h) — how X fills a grid cell."""
    from PIL import Image

    resample = getattr(Image, "Resampling", Image).LANCZOS
    iw, ih = im.size
    scale = max(w / iw, h / ih)
    nw, nh = max(w, round(iw * scale)), max(h, round(ih * scale))
    im = im.resize((nw, nh), resample)
    left, top = (nw - w) // 2, (nh - h) // 2
    return im.crop((left, top, left + w, top + h))


def _play_badge(size: int):
    """An RGBA ▶ badge — translucent dark disc + white triangle — to mark a video/GIF still."""
    from PIL import Image, ImageDraw

    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(badge)
    d.ellipse([0, 0, size - 1, size - 1], fill=(0, 0, 0, 140))
    cx = cy = size / 2
    t = size * 0.22
    d.polygon([(cx - t * 0.5, cy - t), (cx - t * 0.5, cy + t), (cx + t * 0.95, cy)],
              fill=(255, 255, 255, 240))  # rightward triangle, nudged for optical centering
    return badge


def _stamp_play(canvas, cx: int, cy: int, region_min: int) -> None:
    """Paste a play badge centered at (cx, cy), sized to the region it sits on (in place)."""
    size = max(48, min(150, int(region_min * 0.28)))
    badge = _play_badge(size)
    canvas.paste(badge, (int(cx - size / 2), int(cy - size / 2)), badge)


def _compose_media(items: list, maxw: int, maxh: int):
    """Lay 1–4 attached media into one block using X's layouts, badging any video/GIF still.

    `items` are (RGB image, kind) tuples. Returns (RGB image, height)."""
    from PIL import Image

    resample = getattr(Image, "Resampling", Image).LANCZOS
    g = 8  # gutter between items, like X
    items = items[:4]
    n = len(items)

    def cell(idx, w, h, x, y, canvas):
        im, kind = items[idx]
        canvas.paste(_cover(im, w, h), (x, y))
        if kind in ("video", "gif"):
            _stamp_play(canvas, x + w // 2, y + h // 2, min(w, h))

    if n == 1:  # single item: contain-fit, keep the real aspect ratio
        im, kind = items[0]
        iw, ih = im.size
        scale = min(maxw / iw, maxh / ih)
        nw, nh = max(1, round(iw * scale)), max(1, round(ih * scale))
        canvas = im.resize((nw, nh), resample)
        if kind in ("video", "gif"):
            _stamp_play(canvas, nw // 2, nh // 2, min(nw, nh))
        return canvas, nh

    if n == 2:  # side by side
        cw = (maxw - g) // 2
        ch = min(maxh, round(cw * 1.1))
        canvas = Image.new("RGB", (cw * 2 + g, ch), X_CARD)
        cell(0, cw, ch, 0, 0, canvas)
        cell(1, cw, ch, cw + g, 0, canvas)
        return canvas, ch

    if n == 3:  # one tall item left, two stacked right
        cw = (maxw - g) // 2
        bh = min(maxh, round(cw * 1.4))
        sh = (bh - g) // 2
        canvas = Image.new("RGB", (cw * 2 + g, bh), X_CARD)
        cell(0, cw, bh, 0, 0, canvas)
        cell(1, cw, sh, cw + g, 0, canvas)
        cell(2, cw, sh, cw + g, sh + g, canvas)
        return canvas, bh

    cw = (maxw - g) // 2  # n == 4: 2×2 grid
    ch = min((maxh - g) // 2, round(cw * 0.62))
    canvas = Image.new("RGB", (cw * 2 + g, ch * 2 + g), X_CARD)
    for i in range(4):
        r, c = divmod(i, 2)
        cell(i, cw, ch, c * (cw + g), r * (ch + g), canvas)
    return canvas, ch * 2 + g


def _paste_rounded(base, block, x: int, y: int, radius: int = 16) -> None:
    """Paste `block` onto `base` at (x, y) with rounded corners, X-style."""
    from PIL import Image, ImageDraw

    w, h = block.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    base.paste(block, (x, y), mask)


def render_tweet(spec: dict) -> bytes | None:
    """A dark-mode X ('lights out') tweet card with real text, author, engagement, and any
    photo the original tweet had attached (baked in below the text, so the card is faithful)."""
    from PIL import Image, ImageDraw

    text = spec.get("text") or spec.get("quote") or ""
    if not text:
        return None
    name = (spec.get("name") or "Agentry").strip()
    handle = (spec.get("handle") or "agentry").lstrip("@")
    img = Image.new("RGB", (W, H), X_CANVAS)
    d = ImageDraw.Draw(img)

    cx0, cx1, P = 64, W - 64, 56
    inner = cx1 - cx0 - 2 * P
    bf, lines = _fit(d, text, _REG, inner, 540, 56, 34)
    header_h, footer_h, body_h = 132, 60, _lh(bf) * len(lines)
    card_h = P + header_h + body_h + 40 + footer_h + P

    # Bake in the original tweet's own photo(s) below the text, so the card reproduces what people
    # actually saw — only when there's genuine vertical room left, and never at the card's expense.
    media_block, media_gap = None, 20
    try:
        budget = (H - 24) - card_h  # keep ≥12px canvas slack top and bottom
        if spec.get("media") and budget >= 180:
            imgs = _fetch_media(list(spec["media"]))
            if imgs:
                media_block, media_h = _compose_media(imgs, inner, min(budget - media_gap, 460))
                card_h += media_gap + media_h
    except Exception:  # noqa: BLE001 — a broken image must never lose the whole card
        media_block = None

    y0 = (H - card_h) // 2
    d.rounded_rectangle([cx0, y0, cx1, y0 + card_h], radius=32, fill=X_CARD, outline=X_LINE, width=2)

    # header — avatar, name + verified badge, handle, X logo
    ax, ay, ar = cx0 + P, y0 + P, 46
    d.ellipse([ax, ay, ax + ar * 2, ay + ar * 2], fill=_avatar_color(name))
    af = _font(_BOLD, 48)
    ini = (name[:1] or "A").upper()
    d.text((ax + ar - d.textlength(ini, font=af) / 2, ay + ar - _lh(af) / 2), ini, font=af, fill=(255, 255, 255))
    nf, hf = _font(_BOLD, 40), _font(_REG, 33)
    nx = ax + ar * 2 + 26
    d.text((nx, ay + 6), name, font=nf, fill=X_TEXT)
    nw = d.textlength(name, font=nf)
    if spec.get("verified", True):
        bx, by, br = nx + nw + 12, ay + 12, 16  # verified badge
        d.ellipse([bx, by, bx + br * 2, by + br * 2], fill=X_BLUE)
        d.line([(bx + 9, by + 16), (bx + 14, by + 23), (bx + 25, by + 9)], fill=(255, 255, 255), width=4)
    d.text((nx, ay + 8 + _lh(nf)), f"@{handle}", font=hf, fill=X_DIM)
    lx, ly, s = cx1 - P - 36, ay + 4, 36  # X logo
    d.line([(lx, ly), (lx + s, ly + s)], fill=X_TEXT, width=7)
    d.line([(lx + s, ly), (lx, ly + s)], fill=X_TEXT, width=7)

    # body
    y = y0 + P + header_h
    for ln in lines:
        d.text((cx0 + P, y), ln, font=bf, fill=X_TEXT)
        y += _lh(bf)
    if media_block is not None:
        y += media_gap
        mw = media_block.size[0]
        _paste_rounded(img, media_block, cx0 + P + (inner - mw) // 2, y, radius=16)
        y += media_block.size[1]
    y += 24
    d.line([(cx0 + P, y), (cx1 - P, y)], fill=X_LINE, width=2)

    # footer — real engagement: bold light number + dim label (X tweet-detail style)
    fy = y + 22
    nbf, lbf = _font(_BOLD, 30), _font(_REG, 30)
    x, drew = cx0 + P, False
    for val, label in ((spec.get("reposts"), "Reposts"), (spec.get("likes"), "Likes"), (spec.get("views"), "Views")):
        num = _count(val)
        if not num:
            continue
        drew = True
        d.text((x, fy), num, font=nbf, fill=X_TEXT)
        x += d.textlength(num, font=nbf) + 8
        lab = f"{label}     "
        d.text((x, fy), lab, font=lbf, fill=X_DIM)
        x += d.textlength(lab, font=lbf)
    if not drew:
        d.text((cx0 + P, fy), "Posted on X", font=lbf, fill=X_DIM)
    return _save(img)


_RENDERERS = {
    "stat_card": render_stat_card,
    "quote": render_quote,
    "comparison": render_comparison,
    "list": render_list,
    "tweet": render_tweet,
}


def render_image(spec: dict | None) -> bytes | None:
    if not isinstance(spec, dict):
        return None
    try:
        from PIL import Image  # noqa: F401
    except Exception:  # noqa: BLE001
        return None
    fn = _RENDERERS.get((spec.get("type") or "stat_card").lower(), render_stat_card)
    try:
        return fn(spec)
    except Exception:  # noqa: BLE001
        return None
