"""Template-folding sequential alarm over hourly bins, written from the study's specification.

Each event carries an actor (or None) and a text. The text is sanitised, folded into a prefix
key and a suffix key, and an event is coordinated when one of its keys was used by at least
MIN_ACTORS distinct actors within the last WINDOW_BINS bins. The per-bin coordinated fraction C
is turned into a conformal p-value against past bins and into an e-value; the running product S
alarms when it reaches ALARM_S while the bin's mean key multiplicity M is at least M_MIN.
"""

import difflib
import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

BIN_SECONDS = 3600
WINDOW_BINS = 6
MIN_ACTORS = 5
WARMUP_BINS = 48
EPSILONS = (0.05, 0.1, 0.2, 0.35, 0.5)
ALARM_S = 100.0
M_MIN = 3.0
KEY_SLICE = 400
KEY_CHARS = 192
KEY_TOKENS = 12
MIN_KEY_TOKENS = 4
CAP = 1500
FALLBACK_CHARS = 500

URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
BLOB = re.compile(r"[A-Za-z0-9+/=_-]{200,}")
FOLD_URL = re.compile(r"(?:https?://|www\.)\S+|\[url\]")
DIGITS = re.compile(r"\d+")
NON_ALNUM = re.compile(r"[\W_]+")


def changed_text(previous: str | None, body: str, autojunk: bool = True) -> str:
    """Inserted or replacing character spans of body against previous, joined by newline.

    The first FALLBACK_CHARS characters of the body when there are none.
    """
    matcher = difflib.SequenceMatcher(None, previous or "", body, autojunk=autojunk)
    spans = [body[j1:j2] for op, _, _, j1, j2 in matcher.get_opcodes()
             if op in ("insert", "replace")]
    return "\n".join(spans) if spans else body[:FALLBACK_CHARS]


def sanitise(text: str, keep_newlines: bool = False) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cc"
                   or (keep_newlines and ch == "\n"))
    text = URL.sub("[URL]", text)
    text = BLOB.sub("[BLOB]", text)
    return text[:CAP]


def fold(text: str) -> str:
    text = FOLD_URL.sub(" u ", text.lower())
    text = DIGITS.sub("0", text)
    return NON_ALNUM.sub(" ", text).strip()


def keys(text: str) -> list[str]:
    """Prefix key and, when different, suffix key of a sanitised text."""
    head = text[:KEY_SLICE]
    out = []
    prefix = fold(head[:KEY_CHARS]).split()[:KEY_TOKENS]
    if len(prefix) >= MIN_KEY_TOKENS:
        out.append(" ".join(prefix))
    tail = head[-KEY_CHARS:]
    tokens = fold(tail).split()
    cut = len(head) - len(tail)
    if tokens and cut > 0 and head[cut - 1].isalnum() and tail[:1].isalnum():
        tokens = tokens[1:]
    suffix = tokens[-KEY_TOKENS:]
    if len(suffix) >= MIN_KEY_TOKENS:
        key = " ".join(suffix)
        if not out or key != out[0]:
            out.append(key)
    return out


@dataclass(frozen=True)
class Bins:
    start: int
    """Epoch hour (seconds // 3600) of bin 0."""
    n: list[int]
    coordinated: list[int]
    C: list[float]
    M: list[float]


def bin_series(events: list[tuple[float, str | None, list[str]]]) -> Bins:
    """Per-bin counts from (epoch seconds, actor or None, keys) events.

    For each key only the actors of the last WINDOW_BINS bins are held (a sparse map from bin
    index to actor set, evicted as bins leave the window). Bins between the first and the last
    event are zero-filled. An event's multiplicity is the larger of its keys' distinct-actor
    counts over bins b - 5 .. b; it is coordinated at MIN_ACTORS or more. C is the coordinated
    fraction of the bin's events (0 for an empty bin); M is the mean count over the bin's distinct
    keys that are at MIN_ACTORS or more.
    """
    if not events:
        return Bins(0, [], [], [], [])
    ordered = sorted(((int(t // BIN_SECONDS), actor, ks) for t, actor, ks in events),
                     key=lambda e: e[0])
    start, stop = ordered[0][0], ordered[-1][0]
    recent: dict[str, dict[int, set]] = defaultdict(dict)
    touched: dict[int, set] = defaultdict(set)
    n, coordinated, c_values, m_values = [], [], [], []
    i = 0
    for hour in range(start, stop + 1):
        here = []
        while i < len(ordered) and ordered[i][0] == hour:
            _, actor, ks = ordered[i]
            here.append(ks)
            for k in ks:
                touched[hour].add(k)
                if actor is not None:
                    recent[k].setdefault(hour, set()).add(actor)
            i += 1
        counts: dict[str, int] = {}
        coord, coord_keys = 0, {}
        for ks in here:
            for k in ks:
                if k not in counts:
                    counts[k] = len(set().union(*recent[k].values())) if k in recent else 0
            if ks and max(counts[k] for k in ks) >= MIN_ACTORS:
                coord += 1
            for k in ks:
                if counts[k] >= MIN_ACTORS:
                    coord_keys[k] = counts[k]
        n.append(len(here))
        coordinated.append(coord)
        c_values.append(coord / len(here) if here else 0.0)
        m_values.append(float(np.mean(list(coord_keys.values()))) if coord_keys else 0.0)
        old = hour - WINDOW_BINS + 1
        for k in touched.pop(old, ()):
            bins = recent.get(k)
            if bins is not None:
                bins.pop(old, None)
                if not bins:
                    del recent[k]
    return Bins(start, n, coordinated, c_values, m_values)


def e_value(p: float) -> float:
    """Mean over EPSILONS of eps * p ** (eps - 1), with p clipped to [1e-12, 1]."""
    p = min(max(p, 1e-12), 1.0)
    return float(np.mean([eps * p ** (eps - 1.0) for eps in EPSILONS]))


def sequential(bins: Bins, seed: int) -> tuple[list[float], list[bool]]:
    """log10 S after each bin and the alarm flags, for one seed of the tie-breaking draws.

    Bins 0 .. WARMUP_BINS - 1 are warm-up: p = 1 and e = 1, and no uniform is drawn. After that
    p = (G + U * (T + 1)) / (n + 1) against the n past C values, with G strictly greater, T
    equal and U one draw from numpy's default generator seeded with ``seed``; e = e_value(p).
    S starts at 1 and S = e * max(S_prev, 1). A bin alarms when S >= ALARM_S and M >= M_MIN,
    after which S is reset to 1. Every bin's C, empty bins included, is then added to the past.
    Because M averages only over keys already at MIN_ACTORS or more, M is at least MIN_ACTORS
    whenever any key is coordinated, so the gate binds only in bins with no coordinated key.
    """
    rng = np.random.default_rng(seed)
    past: list[float] = []
    s, log_s, alarms = 1.0, [], []
    for b, (c, m) in enumerate(zip(bins.C, bins.M)):
        if b < WARMUP_BINS:
            e = 1.0
        else:
            u = float(rng.random())
            greater = sum(v > c for v in past)
            ties = sum(v == c for v in past)
            e = e_value((greater + u * (ties + 1)) / (len(past) + 1))
        s = e * max(s, 1.0)
        log_s.append(math.log10(s))
        alarm = s >= ALARM_S and m >= M_MIN
        alarms.append(alarm)
        if alarm:
            s = 1.0
        past.append(c)
    return log_s, alarms
