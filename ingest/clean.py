import re

UNSUB_PATTERNS = [
    r"unsubscribe",
    r"manage (?:your )?preferences",
    r"view (?:this )?(?:email )?in (?:your )?browser",
    r"click here to view",
    r"email preferences",
    r"copyright ©",
    r"all rights reserved",
    r"you(?:'re| are) receiving this",
    r"sent to .+@",
    r"mailto:",
    r"^subscribe\s*sign in$",
    r"^subscribe$",
    r"^sign in$",
    r"^share$",
    r"^restacks$",
    r"^comments$",
    r"^previous$",
    r"^ready for more\?$",
    r"^start your substack",
    r"^get the app$",
    r"^discussion about this post",
    r"^\d+\s+likes$",
    r"^∙$",
    r"^\d+\s+restacks$",
    r"^semiAnalysis is a reader-supported",
    r"^© \d{4}",
    r"^privacy ∙ terms",
]

NOISE_RE = re.compile("|".join(UNSUB_PATTERNS), re.IGNORECASE)


def clean_newsletter_text(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if NOISE_RE.search(stripped):
            continue
        if re.fullmatch(r"\d+", stripped):
            continue
        if stripped.startswith("http") and len(stripped) > 120:
            continue
        lines.append(stripped)

    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
