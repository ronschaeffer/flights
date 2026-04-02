"""Airline logo resolution: sync formats, AI generation, and git publishing.

Finds missing airline logos, optionally generates them with AI (Claude or Gemini),
syncs SVG/PNG formats, and can commit/tag/push updates to git.

Environment variables:
    LOGO_AI_PROVIDER: "claude" or "gemini" (default: disabled)
    ANTHROPIC_API_KEY: API key for Claude logo generation
    GEMINI_API_KEY: API key for Gemini logo generation
"""

import json
import logging
import os
import re
import subprocess

from flights.config import BASE_DIR

logger = logging.getLogger(__name__)

LOGOS_DIR = os.path.join(BASE_DIR, "assets", "images", "logos")
SVG_DIR = os.path.join(LOGOS_DIR, "svg")
PNG_DIR = os.path.join(LOGOS_DIR, "png")
MISSING_FILE = os.path.join(BASE_DIR, "output", "missing.json")

# Reference SVG style for AI generation prompt
_SVG_STYLE_PROMPT = """\
Generate an SVG airline logo icon for "{airline_name}" (ICAO code: {icao_code}).

Requirements:
- viewBox="0 0 80 80" (square, 80x80 coordinate space)
- MUST have a solid (non-transparent) background filling the entire viewBox
- Use a circular background (<circle cx="40" cy="40" r="40">) or full square \
(<rect width="80" height="80">)
- Background colour: white is preferred, but if the logo symbol is predominantly \
white or very light, use a complementary darker colour instead so the symbol \
remains visible
- Icon/symbol only - NO text, NO wordmarks, NO airline name
- Use the airline's real logo mark/symbol if you know it (tail logo, roundel, etc.)
- If unknown, create a distinctive geometric symbol using the airline's likely \
brand colours
- Clean vector paths, no embedded rasters or fonts
- Minimal SVG: use <path>, <circle>, <rect> etc. No <text>, <image>, <foreignObject>
- Use fill colours directly or simple <linearGradient>/<radialGradient> in <defs>
- xmlns="http://www.w3.org/2000/svg" on the root <svg> element
- No XML declaration, no comments, no extra whitespace

Return ONLY the SVG markup, nothing else. No markdown fences, no explanation.\
"""

# Max logos to generate per batch (avoid long-running API calls)
_AI_BATCH_SIZE = 20


def _get_existing_logos() -> tuple[set[str], set[str]]:
    """Return sets of ICAO codes that have SVG and PNG logos."""
    svg_codes: set[str] = set()
    png_codes: set[str] = set()
    if os.path.isdir(SVG_DIR):
        for f in os.listdir(SVG_DIR):
            if f.endswith(".svg") and not f.startswith("_"):
                svg_codes.add(f[:-4])
    if os.path.isdir(PNG_DIR):
        for f in os.listdir(PNG_DIR):
            if f.endswith(".png") and not f.startswith("_"):
                png_codes.add(f[:-4])
    return svg_codes, png_codes


def _is_valid_icao(code: str) -> bool:
    """Check if a string looks like a valid ICAO airline code (2-4 alphanumeric)."""
    return bool(code) and 2 <= len(code) <= 4 and code.isalnum()


def _load_missing_logos() -> dict[str, dict]:
    """Load the logos section from missing.json."""
    if not os.path.exists(MISSING_FILE):
        return {}
    try:
        with open(MISSING_FILE) as f:
            data = json.load(f)
        logos = data.get("logos", {})
        # Normalise: entries can be True or {"name": "..."}
        result = {}
        for code, info in logos.items():
            if isinstance(info, dict):
                result[code] = info
            else:
                result[code] = {}
        return result
    except Exception:
        logger.exception("Failed to load missing logos from %s", MISSING_FILE)
        return {}


def _remove_from_missing(codes: set[str]) -> None:
    """Remove resolved codes from the logos section of missing.json."""
    if not codes or not os.path.exists(MISSING_FILE):
        return
    try:
        with open(MISSING_FILE) as f:
            data = json.load(f)
        logos = data.get("logos", {})
        for code in codes:
            logos.pop(code, None)
        data["logos"] = logos
        with open(MISSING_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        logger.exception("Failed to update missing.json")


def _extract_svg(text: str) -> str | None:
    """Extract SVG markup from AI response text."""
    # Try to find <svg>...</svg> block
    match = re.search(r"(<svg\b[^>]*>.*?</svg>)", text, re.DOTALL)
    if match:
        return match.group(1)
    return None


def _validate_svg(svg_text: str) -> bool:
    """Basic validation that SVG is well-formed and meets style requirements."""
    if not svg_text or "<svg" not in svg_text or "</svg>" not in svg_text:
        return False
    # Reject SVGs with embedded text or images
    if "<text" in svg_text or "<image" in svg_text or "<foreignObject" in svg_text:
        return False
    # Must have a viewBox
    return "viewBox" in svg_text


# ---------------------------------------------------------------------------
# SVG ↔ PNG conversion
# ---------------------------------------------------------------------------


def _pick_background_colour(img) -> tuple[int, int, int]:
    """Choose a background colour based on the image content.

    Returns white unless the image is predominantly light, in which case
    a neutral dark background is returned.
    """
    # Sample non-transparent pixels
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    pixels = list(img.getdata())
    opaque = [(r, g, b) for r, g, b, a in pixels if a > 128]
    if not opaque:
        return (255, 255, 255)

    # Average brightness of opaque pixels (0-255)
    avg_brightness = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in opaque) / len(
        opaque
    )

    if avg_brightness > 200:
        # Logo is very light — use a dark slate background
        return (45, 55, 72)
    return (255, 255, 255)


def svg_to_png(svg_path: str, png_path: str, size: int = 90) -> bool:
    """Convert an SVG file to a square PNG with a solid background.

    Renders the SVG with transparency, picks an appropriate background
    colour (white, or dark if the logo is predominantly light), then
    composites and saves.

    Returns True on success.
    """
    try:
        import cairosvg
        from PIL import Image

        # Render SVG to PNG bytes (transparent)
        png_bytes = cairosvg.svg2png(
            url=svg_path,
            output_width=size,
            output_height=size,
        )

        # Open and composite onto solid background
        import io

        fg = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        bg_colour = _pick_background_colour(fg)
        bg = Image.new("RGBA", fg.size, (*bg_colour, 255))
        composite = Image.alpha_composite(bg, fg).convert("RGB")
        composite.save(png_path, "PNG")
        return True
    except ImportError as exc:
        logger.warning("Missing dependency for SVG→PNG: %s", exc)
        return False
    except Exception:
        logger.exception("Failed to convert %s to PNG", svg_path)
        return False


def sync_formats() -> dict[str, list[str]]:
    """Sync SVG and PNG directories: rasterise SVGs missing PNGs.

    Returns dict with lists of codes synced in each direction.
    """
    svg_codes, png_codes = _get_existing_logos()
    results: dict[str, list[str]] = {"svg_to_png": []}

    # SVGs without matching PNGs → rasterise
    svg_only = svg_codes - png_codes
    for code in sorted(svg_only):
        svg_path = os.path.join(SVG_DIR, f"{code}.svg")
        png_path = os.path.join(PNG_DIR, f"{code}.png")
        if svg_to_png(svg_path, png_path):
            results["svg_to_png"].append(code)
            logger.info("Converted %s.svg → PNG", code)

    return results


# ---------------------------------------------------------------------------
# AI logo generation
# ---------------------------------------------------------------------------


def _generate_with_claude(
    icao_code: str, airline_name: str, api_key: str
) -> str | None:
    """Generate an SVG logo using the Anthropic Claude API."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": _SVG_STYLE_PROMPT.format(
                        airline_name=airline_name, icao_code=icao_code
                    ),
                }
            ],
        )
        text = message.content[0].text
        return _extract_svg(text)
    except ImportError:
        logger.error("anthropic package not installed")
        return None
    except Exception:
        logger.exception("Claude API call failed for %s", icao_code)
        return None


def _generate_with_gemini(
    icao_code: str, airline_name: str, api_key: str
) -> str | None:
    """Generate an SVG logo using the Google Gemini API."""
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=_SVG_STYLE_PROMPT.format(
                airline_name=airline_name, icao_code=icao_code
            ),
        )
        return _extract_svg(response.text)
    except ImportError:
        logger.error("google-genai package not installed")
        return None
    except Exception:
        logger.exception("Gemini API call failed for %s", icao_code)
        return None


def generate_missing_logos(
    provider: str | None = None,
    api_key: str | None = None,
    airlines_json: list | None = None,
    batch_size: int = _AI_BATCH_SIZE,
) -> list[str]:
    """Generate logos for airlines that have none.

    Args:
        provider: "claude" or "gemini". None to skip AI generation.
        api_key: API key for the chosen provider.
        airlines_json: Airlines database for name lookups.
        batch_size: Max logos to generate per run.

    Returns:
        List of ICAO codes for which logos were successfully generated.
    """
    if not provider or not api_key:
        logger.info("AI logo generation disabled (no provider/key configured)")
        return []

    generator = {
        "claude": _generate_with_claude,
        "gemini": _generate_with_gemini,
    }.get(provider)

    if not generator:
        logger.error("Unknown AI provider: %s (use 'claude' or 'gemini')", provider)
        return []

    # Build airline name lookup
    name_lookup: dict[str, str] = {}
    if airlines_json:
        for airline in airlines_json:
            icao = airline.get("icao_code", "")
            if icao:
                name_lookup[icao] = airline.get("name", icao)

    # Collect candidates: from missing.json + airlines DB entries without logos
    svg_codes, png_codes = _get_existing_logos()
    has_logo = svg_codes | png_codes

    candidates: dict[str, str] = {}

    # From missing.json (actively seen in flights)
    missing_logos = _load_missing_logos()
    for code, info in missing_logos.items():
        if code not in has_logo and _is_valid_icao(code):
            name = info.get("name", "") or name_lookup.get(code, code)
            candidates[code] = name

    # Prioritise missing.json entries (actually seen), then fill from DB
    if len(candidates) < batch_size and airlines_json:
        for airline in airlines_json:
            icao = airline.get("icao_code", "")
            if (
                icao
                and _is_valid_icao(icao)
                and icao not in has_logo
                and icao not in candidates
            ):
                candidates[icao] = airline.get("name", icao)
            if len(candidates) >= batch_size:
                break

    # Generate
    batch = list(candidates.items())[:batch_size]
    generated: list[str] = []

    for icao_code, airline_name in batch:
        logger.info(
            "Generating logo for %s (%s) via %s", icao_code, airline_name, provider
        )
        svg_text = generator(icao_code, airline_name, api_key)

        if not svg_text or not _validate_svg(svg_text):
            logger.warning("Invalid SVG generated for %s, skipping", icao_code)
            continue

        # Save SVG
        svg_path = os.path.join(SVG_DIR, f"{icao_code}.svg")
        with open(svg_path, "w") as f:
            f.write(svg_text)

        # Convert to PNG
        png_path = os.path.join(PNG_DIR, f"{icao_code}.png")
        svg_to_png(svg_path, png_path)

        generated.append(icao_code)
        logger.info("Generated logo for %s", icao_code)

    # Clean up missing.json
    if generated:
        _remove_from_missing(set(generated))

    return generated


# ---------------------------------------------------------------------------
# Git operations
# ---------------------------------------------------------------------------


def _git(*args: str) -> tuple[int, str]:
    """Run a git command in the project directory. Returns (returncode, output)."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.returncode, result.stdout.strip() or result.stderr.strip()
    except FileNotFoundError:
        return 1, "git not found"
    except subprocess.TimeoutExpired:
        return 1, "git command timed out"


def publish_logo_updates() -> bool:
    """Commit new/changed logos, tag, and push to origin.

    Returns True if changes were committed and pushed.
    """
    # Check for changes in the logos directory
    rc, status = _git("status", "--porcelain", "assets/images/logos/")
    if rc != 0 or not status:
        logger.info("No logo changes to publish")
        return False

    # Count new files
    lines = [line for line in status.splitlines() if line.strip()]
    new_count = sum(1 for line in lines if line.startswith("?") or line.startswith("A"))
    modified_count = sum(1 for line in lines if line.startswith("M"))

    # Stage logo files
    rc, out = _git("add", "assets/images/logos/")
    if rc != 0:
        logger.error("git add failed: %s", out)
        return False

    # Build commit message
    parts = []
    if new_count:
        parts.append(f"{new_count} new")
    if modified_count:
        parts.append(f"{modified_count} updated")
    summary = ", ".join(parts) or "updated"
    commit_msg = f"chore(logos): {summary} airline logos"

    rc, out = _git("commit", "-m", commit_msg)
    if rc != 0:
        logger.error("git commit failed: %s", out)
        return False
    logger.info("Committed: %s", commit_msg)

    # Tag with date-based version
    from datetime import UTC, datetime

    tag = "logos-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    rc, out = _git("tag", tag)
    if rc != 0:
        logger.warning("git tag failed: %s", out)
        # Non-fatal, continue to push

    # Push commit and tags
    rc, out = _git("push", "origin", "main")
    if rc != 0:
        logger.error("git push failed: %s", out)
        return False

    rc, out = _git("push", "origin", "--tags")
    if rc != 0:
        logger.warning("git push --tags failed: %s", out)

    logger.info("Published logo updates (tag: %s)", tag)
    return True


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def update_logos(
    ai_provider: str | None = None,
    api_key: str | None = None,
    airlines_json: list | None = None,
    publish: bool = False,
) -> dict:
    """Run a full logo update cycle.

    1. Sync SVG → PNG for any SVG-only logos
    2. Optionally generate missing logos with AI
    3. Optionally commit/tag/push to git

    Returns summary dict with counts.
    """
    os.makedirs(SVG_DIR, exist_ok=True)
    os.makedirs(PNG_DIR, exist_ok=True)

    summary: dict = {"synced": [], "generated": [], "published": False}

    # Step 1: Sync formats
    sync_results = sync_formats()
    summary["synced"] = sync_results.get("svg_to_png", [])
    if summary["synced"]:
        logger.info("Synced %d SVGs to PNG", len(summary["synced"]))

    # Step 2: AI generation (if configured)
    generated = generate_missing_logos(
        provider=ai_provider,
        api_key=api_key,
        airlines_json=airlines_json,
    )
    summary["generated"] = generated

    # Step 3: Publish to git (if requested and there are changes)
    if publish and (summary["synced"] or summary["generated"]):
        summary["published"] = publish_logo_updates()

    svg_codes, png_codes = _get_existing_logos()
    summary["total_svg"] = len(svg_codes)
    summary["total_png"] = len(png_codes)

    return summary
