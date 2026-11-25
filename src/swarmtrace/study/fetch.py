"""Download the control log once and record its SHA-256 and size next to it."""

import hashlib
import json
import urllib.request
from pathlib import Path

CONTROL_URL = ("https://dumps.wikimedia.org/other/mediawiki_history/2026-10/ndswiki/"
               "2026-10.ndswiki.all-time.tsv.bz2")
USER_AGENT = "study-replay/0.1 (research script)"
CHUNK = 1 << 20


def fetch_control(out: Path, url: str = CONTROL_URL, opener=urllib.request.urlopen) -> dict:
    """Write url to out (refusing to overwrite) and out + '.sha256.json'; returns that record."""
    out = Path(out)
    record_path = out.with_name(out.name + ".sha256.json")
    for path in (out, record_path):
        if path.exists():
            raise FileExistsError(f"{path} already exists")
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.name + ".partial")
    digest, size = hashlib.sha256(), 0
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener(request) as response, open(partial, "wb") as handle:
            while chunk := response.read(CHUNK):
                digest.update(chunk)
                size += len(chunk)
                handle.write(chunk)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    partial.rename(out)
    record = {"url": url, "sha256": digest.hexdigest(), "bytes": size}
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record
