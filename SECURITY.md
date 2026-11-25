# Security Policy

Swarmtrace is a simulation and analysis codebase. The default branch is the
supported version. The original study is offline and deterministic. The agent
pilot added three things that are not:

- `python -m swarmtrace.pilot serve` and `run` start a small HTTP service that
  listens on loopback addresses only, for the length of a run.
- `python -m swarmtrace.pilot run` and `batch` launch third-party agent
  command-line tools as child processes. Those agents are told to use only
  curl against the local service and run with the permission settings recorded
  in each run's manifest, but nothing confines their network access to the
  service. Run them only on a machine where that is acceptable.
- `python -m swarmtrace.study fetch-control` downloads one public file of about
  82 MB and records its SHA-256; the transfer test checks pinned hashes of both
  of its input files before parsing them.

These commands accept `--fetch` to retrieve reproduction inputs. Each verifies
the pinned SHA-256 before writing or parsing the downloaded bytes.

| Command (accepts `--fetch`) | Download checks |
| --- | --- |
| `swarmtrace.reproduce.approval_text_source` | Pinned SHA-256 and a 5 MB limit. |
| `swarmtrace.reproduce.authority_external` | Pinned size and SHA-256 for each file. |
| `swarmtrace.reproduce.authority_vectors` | Pinned size and SHA-256 for the archive. |
| `swarmtrace native-hook-benchmark` | Pinned size and SHA-256 for each capture. |
| `swarmtrace dispatch-workflows` or `swarmtrace operation-authority` | Pinned SHA-256 from the frozen protocol and a 5 MB limit. |

See [docs/reproduce.md](docs/reproduce.md) for full invocations. The 5 MB limit
applies to the final response body that is read. The standard library follows
HTTP redirects before that bounded read begins.

To report a vulnerability privately, open the repository's **Security** tab
and select **Report a vulnerability**. If the **Report a vulnerability** button
is unavailable, open a public issue that asks for a private contact channel and
contains no vulnerability details.
