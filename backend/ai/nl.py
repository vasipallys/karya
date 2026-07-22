"""Deterministic natural-language helpers shared by the chat interpreters.

Both the offline mock provider ([backend/llm/mock.py]) and the local-model
routing path ([backend/ai/agents.py] `_interpret_local_chat`) turn a chat message
into a `ChatCommand` without a large-schema LLM call. The relation phrasing —
"add route to payments through api-gateway" — is subtle enough (the intermediary
after *through/via* is the source, not the target) that both paths must agree, so
the logic lives here once and is imported by each.
"""

from __future__ import annotations

import re

_REL_TRIGGER = re.compile(r"\b(route|routes|connect|connects|link|links|wire|wires|connection)\b", re.IGNORECASE)
# Leading qualifiers dropped before name resolution so "L2 payment" and
# "the api gateway" resolve to their element names.
_LEADING_FILLER = re.compile(r"^(?:\s*(?:the|a|an|new|l[1-4])\b)+", re.IGNORECASE)

_LEVEL_RE = re.compile(r"\bl([1-4])\b", re.IGNORECASE)
_TYPE_WORD = re.compile(r"element|container|component|service|module|task|stor(?:y|ies)|initiative|epic|node", re.IGNORECASE)
# Verbs/nouns that ask to enumerate the model, as opposed to a whole-project question.
_ENUMERATE = re.compile(r"\b(list|show|display|enumerate|summar(?:y|ise|ize|ies)|how many|which|items?|everything)\b", re.IGNORECASE)
# Status words a "list" request may filter on; "pending" maps to the proposed status.
_STATUS_WORDS = {"pending": "proposed", "proposed": "proposed", "draft": "proposed",
                 "active": "active", "reviewed": "reviewed", "baselined": "baselined"}
_REPORT = re.compile(r"\bnext\b|what should i|recommend|roll.?up|\breport\b|estimat", re.IGNORECASE)
_READINESS = re.compile(r"readiness|how ready|are we ready|is it ready", re.IGNORECASE)
_DESCRIBE = re.compile(
    r"\b(describe|description|purpose|responsibilit(?:y|ies)|details?)\b|"
    r"\b(?:what is|what's|tell me)\b.*\babout\b|\bwhat does\b.*\bdo\b",
    re.IGNORECASE,
)
_OVERVIEW = re.compile(r"overview|project status|\bstatus\b|progress|where am i|how are we|health|state of|summar(?:y|ise|ize)", re.IGNORECASE)
_WRITE_INTENT = re.compile(
    r"\b(create|add|rename|delete|remove|set|update|change|connect|route|link|wire)\b",
    re.IGNORECASE,
)


def _squash(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def is_write_intent(text: str) -> bool:
    """Whether a message should reach mutation routing before read routing."""
    return bool(_WRITE_INTENT.search(text))


def resolve_element_name(fragment: str, names: list[str]) -> str:
    """Map a free-text fragment ("the api gateway", "L2 payment") to a known
    element name ("api-gateway"), or "" when nothing matches. Longest names win
    first so "api-gateway" beats a bare "api"."""
    frag = _squash(_LEADING_FILLER.sub("", fragment.strip()))
    if not frag:
        return ""
    for name in sorted(names, key=len, reverse=True):
        squashed = _squash(name)
        if not squashed:
            continue
        # Forward: the canonical name appears in the user's phrase ("the api gateway").
        # Reverse: the user typed a shorter form than the canonical name — only trust
        # this when the fragment is distinctive enough (>=4 chars) so filler words like
        # "it"/"to" don't spuriously match ("it" is a substring of "dig-it-al").
        if squashed in frag or (len(frag) >= 4 and frag in squashed):
            return name
    return ""


def match_relation(text: str, names: list[str]) -> tuple[str, str, str] | None:
    """Detect a request to connect two *existing* elements.

    Returns `(source, target, label)` or None. Both endpoints must resolve to
    known elements, so "create X and route it to Y" (X is new, unknown) still
    falls through to create_element rather than being read as a relation.

    Direction rules (source → target):
    - "route/connect A to/into/with B"      → A → B
    - "route from A to B"                    → A → B  (*from* names the source)
    - "route to B from A"                    → A → B
    - "route to X through/via Y"            → Y → X  (the *through/via* hop is the source)
    - "route/connection between A and B"    → A → B
    """
    if not _REL_TRIGGER.search(text):
        return None
    low = text.lower()
    label = "routes" if "rout" in low else "links to" if "link" in low else "connects to"

    def pair(source_frag: str, target_frag: str) -> tuple[str, str, str] | None:
        source, target = resolve_element_name(source_frag, names), resolve_element_name(target_frag, names)
        if source and target and source != target:
            return (source, target, label)
        return None

    # "… between A and B"
    m = re.search(r"\bbetween\s+(.+?)\s+and\s+(.+?)[?.]*$", text, re.IGNORECASE)
    if m and (found := pair(m.group(1), m.group(2))):
        return found
    # "… from A to B"  → A is the source
    m = re.search(r"\bfrom\s+(.+?)\s+to\s+(.+?)[?.]*$", text, re.IGNORECASE)
    if m and (found := pair(m.group(1), m.group(2))):
        return found
    # "… to B from A"  → A (named after *from*) is the source
    m = re.search(r"\bto\s+(.+?)\s+from\s+(.+?)[?.]*$", text, re.IGNORECASE)
    if m and (found := pair(m.group(2), m.group(1))):
        return found
    # "… to X through/via Y"  → Y routes to X (intermediary named after through/via is the source)
    m = re.search(r"\bto\s+(.+?)\s+(?:through|via)\s+(.+?)[?.]*$", text, re.IGNORECASE)
    if m and (found := pair(m.group(2), m.group(1))):
        return found
    # "route/connect A to/into/with/through/via B"  → A routes to B
    m = re.search(
        r"\b(?:route|connect|link|wire|call)s?\s+(.+?)\s+(?:to|into|with|through|via)\s+(.+?)[?.]*$",
        text, re.IGNORECASE,
    )
    if m and (found := pair(m.group(1), m.group(2))):
        return found
    return None


_CREATE_TRIGGER = re.compile(r"\b(create|add|new)\b", re.IGNORECASE)
_TYPE_TAIL = r"(?:container|component|service|module|task|stor(?:y|ies)|system|element|node|initiative|epic)"


def _clean_name(raw: str) -> str:
    """Strip quotes, leading articles/level tokens, and a trailing type word from a
    captured element name so 'a "Payments"' / 'the L3 payments container' → 'Payments'."""
    s = raw.strip().strip("\"'“”‘’").strip()
    s = re.sub(r"^(?:(?:a|an|the|new|l[1-4])\s+)+", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(rf"\s+{_TYPE_TAIL}$", "", s, flags=re.IGNORECASE).strip()
    return s.strip("\"'“”‘’").strip()


def _new_element_name(text: str) -> str:
    """Extract the name for a new element across the phrasings people actually use,
    including a quoted literal and the name appearing *before* the level/type
    ("add a \"Payments\" as a new L3 container")."""
    patterns = (
        # explicit "called/named X" (stop at a following clause word)
        r"\b(?:called|named)\s+[\"'“‘]?(.+?)[\"'”’]?(?:\s+(?:under|as|and|,|that|which)\b|[?.,]|$)",
        # a quoted literal anywhere: "Payments" / “Payments”
        r"[\"'“‘]([^\"'”’]{1,60})[\"'”’]",
        # "<verb> <name> as [a/an/the] [new] L#"
        r"\b(?:create|add)\b\s+(.+?)\s+as\s+(?:a|an|the\s+)?(?:new\s+)?l[1-4]\b",
        # "<verb> [a/an] [new] L# <name> <type>"
        rf"\bl[1-4]\s+(.+?)\s+{_TYPE_TAIL}\b",
        # "<verb> [a/an] <name> <type>"
        rf"\b(?:create|add)\b\s+(?:a|an|the|new|\s)*?(.+?)\s+{_TYPE_TAIL}\b",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            name = _clean_name(m.group(1))
            if name and not re.fullmatch(r"(?:a|an|the|new|l[1-4])", name, re.IGNORECASE):
                return name
    return ""


def parse_create(text: str, names: list[str]) -> dict[str, str] | None:
    """Parse a create request into {level, name, parent, target, label}, or None.

    Handles a compound "… and connect/route it through/to <existing element>"
    tail — the new element is wired to that element on apply — plus an optional
    "name the route as X" label. Shared so the mock and local paths agree.
    """
    if not _CREATE_TRIGGER.search(text):
        return None
    level_match = _LEVEL_RE.search(text)
    level = f"L{level_match.group(1)}" if level_match else ""
    name = _new_element_name(text)

    parent = ""
    parent_match = re.search(r"\bunder\s+(.+?)(?:\s+and\b|[?.]*$)", text, re.IGNORECASE)
    if parent_match:
        parent = _clean_name(parent_match.group(1))

    target, label = "", ""
    # Exact relation verbs only — must not match "called"/"calling" from a name clause.
    rel_match = re.search(r"\b(?:and\s+)?(?:routes?|connects?|links?|wires?|publishes?|calls?)\b(.+)$", text, re.IGNORECASE)
    if rel_match:
        target = resolve_element_name(rel_match.group(1), names)
        label_match = re.search(r"\bname\s+(?:the\s+)?(?:route|connection|link|relation)\s+(?:as|to)\s+[\"'“‘]?([^\"'”’?.,]+)",
                                text, re.IGNORECASE)
        if label_match:
            label = label_match.group(1).strip()
    return {"level": level, "name": name, "parent": parent, "target": target, "label": label}


def classify_read(text: str, names: list[str], screen_level: str = "", screen_element: str = "") -> tuple[str, str, str] | None:
    """Route a *read* request to a deterministic, DB-grounded action.

    Returns `(action, level, name)` for one of overview / report / list /
    describe / readiness, or None when the message isn't a recognizable read (so the caller
    can try writes or fall back to a free-form answer). Keeping this shared means
    "give me complete project status" → overview and "summary of all L2" → list
    are answered from real data on every path instead of the model hallucinating.

    `screen_level`/`screen_element` are the level and selected element of the
    screen the user is on. They resolve otherwise-ambiguous requests: a bare
    "readiness" while an element is open → that element; "list"/"show" on an
    L2 screen with no explicit level → that level.
    """
    low = text.lower()
    level_match = _LEVEL_RE.search(low)
    level = f"L{level_match.group(1)}" if level_match else ""
    found = resolve_element_name(text, names)

    # "what's next / roll-up / report / estimation progress" → deterministic report.
    if _REPORT.search(low):
        return ("report", "", "")
    # Description/details of a resolved element come from its persisted C4 and
    # architecture records, never a free-form model answer.
    if found and _DESCRIBE.search(low):
        return ("describe", "", found)
    # An explicitly named lifecycle status is a list filter (for example,
    # "list L1 status active"), not a readiness request.
    if level and re.search(r"\b(status|progress)\b", low) and any(
        re.search(rf"\b{word}\b", low) for word in _STATUS_WORDS
    ):
        return ("list", level, "")
    # A named element or explicit level scopes status/progress to readiness.
    # This keeps "status of each L1 item" out of the project overview route.
    if re.search(r"\b(status|progress)\b", low) and (found or level):
        return ("readiness", "" if found else level, found)
    # Readiness of a named element (explicit, else the open element), or a whole level.
    if _READINESS.search(low):
        name = found or screen_element
        return ("readiness", "" if name else (level or screen_level), name)
    # Explicitly scoped enumeration: an enumerate verb plus a level or element-type word.
    if _ENUMERATE.search(low) and (level or _TYPE_WORD.search(low)):
        return ("list", level, "")
    # Whole-project status / progress / summary (checked before the screen-scoped list
    # so "summary of the project" stays an overview rather than listing the open level).
    if _OVERVIEW.search(low):
        return ("overview", "", "")
    # Bare enumeration on a level screen ("list", "show me") → that screen's level.
    if _ENUMERATE.search(low) and screen_level:
        return ("list", screen_level, "")
    return None


def list_status_filter(text: str) -> str:
    """The element status a list request wants to filter on ("pending items" →
    proposed), or "" for the default (non-proposed) view."""
    low = text.lower()
    for word, status in _STATUS_WORDS.items():
        if re.search(rf"\b{word}\b", low):
            return status
    return ""
