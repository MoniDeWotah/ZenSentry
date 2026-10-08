"""Match app identities and website hosts, never incidental title mentions."""

import re
from pathlib import PureWindowsPath
from urllib.parse import urlsplit


BROWSER_PROCESSES = {
    "chrome", "msedge", "firefox", "brave", "opera", "vivaldi", "chromium",
}
SITE_DOMAINS = {
    "facebook": ("facebook.com", "fb.com"),
    "twitter": ("twitter.com", "x.com"),
    "x": ("x.com", "twitter.com"),
    "reddit": ("reddit.com",),
    "instagram": ("instagram.com",),
    "discord": ("discord.com", "discord.gg"),
    "steam": ("steampowered.com", "steamcommunity.com"),
}
APP_ALIASES = {
    "x": {"x", "twitter"}, "twitter": {"twitter", "x"},
    "mem reduct": {"memreduct", "mem reduct"},
    "virtualbox": {"virtualbox", "virtualboxvm"},
}
TITLE_ALIASES = {"code": {"visual studio code"}, "cmd": {"command prompt"}}


def process_name(process):
    return PureWindowsPath(process or "").stem.casefold()


def website_host(address):
    address = (address or "").strip()
    if not address or any(c.isspace() for c in address):
        return ""
    try:
        parsed = urlsplit(address if "://" in address else "https://" + address)
        if parsed.scheme.casefold() not in {"http", "https"}:
            return ""
        return (parsed.hostname or "").casefold().rstrip(".")
    except ValueError:
        return ""


def matches_app(process, title, rules):
    identity = process_name(process)
    if identity and identity != "unknown_process":
        return any(identity in APP_ALIASES.get(process_name(rule), {process_name(rule)})
                   for rule in rules)
    # Fallback only when the OS could not supply an identity. A document title
    # containing an app's name is deliberately not evidence of that app.
    title = (title or "").strip().casefold()
    return any(title in {rule.casefold(), *TITLE_ALIASES.get(rule.casefold(), set())}
               for rule in rules)


def is_blocked(process, title, address, rules):
    if process_name(process) in BROWSER_PROCESSES:
        host = website_host(address)
        for rule in rules:
            rule = rule.strip().casefold()
            domains = SITE_DOMAINS.get(rule, (rule,) if "." in rule else ())
            if any(host == domain or host.endswith("." + domain) for domain in domains):
                return True
        return False
    return matches_app(process, title, rules)


def matches_keywords(title, keywords):
    return any(re.search(r"(?<!\w)" + re.escape(keyword.strip()) + r"(?!\w)",
                         title or "", re.IGNORECASE)
               for keyword in keywords if keyword.strip())
