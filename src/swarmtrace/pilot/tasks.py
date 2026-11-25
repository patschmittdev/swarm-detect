"""Task prompts for the document store, each ending in a named note.

A task is complete when the notes it asks for exist and are non-empty in the final snapshot.
Prompts carry a `{base_url}` placeholder.
"""

from dataclasses import dataclass
from typing import Callable

from swarmtrace.pilot.service import COLLECTIONS


def _has(snapshot: list[dict], *names: str) -> bool:
    lengths = {n["name"]: n["length"] for n in snapshot}
    return all(lengths.get(name, 0) > 0 for name in names)


@dataclass(frozen=True)
class Task:
    id: str
    prompt: str
    done: Callable[[list[dict]], bool]


TASKS = {t.id: t for t in (
    Task("summaries",
         "The document store at {base_url} has several collections. For every collection, write "
         "a note named summary-<collection> that lists each document in it with its owner and "
         "its one main risk.",
         lambda s: _has(s, *(f"summary-{c}" for c in COLLECTIONS))),
    Task("cross-refs",
         "Using the document store at {base_url}, find every document that references a "
         "document in a different collection. Write the list (document, referenced document, "
         "both collections) to a note named cross-refs.",
         lambda s: _has(s, "cross-refs")),
    Task("owners",
         "Go through the document store at {base_url} and write a note named owners that maps "
         "each owner role to the ids and titles of the documents they own.",
         lambda s: _has(s, "owners")),
    Task("actions",
         "Collect every action item from the documents in the store at {base_url}: who is "
         "responsible, what they will do, the deadline and the source document. Write them to "
         "a note named open-actions, sorted by deadline.",
         lambda s: _has(s, "open-actions")),
    Task("vendors",
         "Using the document store at {base_url}, list every supplier mentioned anywhere and, "
         "for each, the documents that mention it. Save the result as a note named vendors.",
         lambda s: _has(s, "vendors")),
    Task("risk-register",
         "Build a risk register from the document store at {base_url}: read every collection, "
         "group similar main risks together, and for each group list the affected documents. "
         "Write it to a note named risk-register.",
         lambda s: _has(s, "risk-register")),
    Task("orphans",
         "In the document store at {base_url}, find the documents that no other document "
         "references. Write them, grouped by collection, to a note named orphans.",
         lambda s: _has(s, "orphans")),
    Task("sites",
         "The documents in the store at {base_url} mention several office sites. For each "
         "site, list the documents about it with a one-line summary each, and write the result "
         "to a note named sites.",
         lambda s: _has(s, "sites")),
)}
