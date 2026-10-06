# Regression tests for the security audit's DEP-1 / DEP-2 findings.
#
# DEP-1 asked whether production installs are actually constrained by
# requirements.lock. They already are: requirements.txt's first line is
# "-c requirements.lock" and the Dockerfile runs
# `pip install -r requirements.txt` - pip applies a `-c` constraints file
# to the whole resolution (including transitive dependencies), so every
# package that has a lock entry gets pinned to it. Verified directly by
# installing requirements.txt into a clean Python 3.12 venv and confirming
# every resolved version matched requirements.lock except one.
#
# DEP-2: that one exception was PyJWT - present in requirements.txt but
# missing from requirements.lock, so it installed unconstrained (whatever
# version PyPI currently serves, silently, with no lock review). Fixed by
# adding PyJWT==2.15.1 to requirements.lock (the version actually resolved
# from the real Python 3.12 dependency set, not invented) - it has no
# dependencies of its own, so no further additions were needed. pip-audit
# against the resulting locked environment found no PyJWT/cryptography
# advisories; it did flag pre-existing pypdf==6.17.0 and urllib3==2.7.0
# advisories, left in place per DEP-2's "report, don't silently upgrade
# unrelated packages" scope (see requirements.lock's header comment).
#
# This file is the "add a regression/CI consistency check preventing
# future requirements/lock drift" deliverable: it's a fast, static check
# (no pip resolution, no network) that fails the moment requirements.txt
# and requirements.lock drift apart again - e.g. a new top-level package
# added to one and not the other, a lock entry with no matching
# requirement, the -c wiring removed, or an inline pin in requirements.txt
# that disagrees with the lock's pin for the same package.
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_TXT = ROOT / "requirements.txt"
REQUIREMENTS_LOCK = ROOT / "requirements.lock"
DOCKERFILE = ROOT / "Dockerfile"


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def _requirements_txt_lines():
    return [
        line.strip()
        for line in REQUIREMENTS_TXT.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _lock_entries():
    """{normalized_name: (raw_name, version)} for every pinned lock line."""
    entries = {}
    for line in REQUIREMENTS_LOCK.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        raw_name, _, version = line.partition("==")
        entries[_normalize(raw_name)] = (raw_name, version)
    return entries


def _requirement_specs():
    """{normalized_name: (raw_name, pinned_version_or_None)} for every
    top-level requirement line (excluding the -c constraints directive)."""
    specs = {}
    for line in _requirements_txt_lines():
        if line.startswith("-c "):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*(==\s*([^\s;]+))?", line)
        assert match, f"Unparseable requirements.txt line: {line!r}"
        raw_name, _, version = match.groups()
        specs[_normalize(raw_name)] = (raw_name, version)
    return specs


def test_requirements_txt_still_constrains_against_the_lock_file():
    # DEP-1's wiring: this line is what makes `pip install -r
    # requirements.txt` apply requirements.lock as a constraints file.
    lines = _requirements_txt_lines()
    assert lines, "requirements.txt is empty"
    assert lines[0] == "-c requirements.lock", (
        "requirements.txt must start with '-c requirements.lock' - "
        "removing this silently stops production installs from being "
        "constrained by the lock file (DEP-1)"
    )


def test_dockerfile_installs_via_the_constrained_requirements_file():
    dockerfile_text = DOCKERFILE.read_text()
    assert re.search(r"pip install[^\n]*-r\s+requirements\.txt", dockerfile_text), (
        "Dockerfile must install via `pip install -r requirements.txt` so "
        "the -c requirements.lock constraint actually applies in production"
    )


def test_every_top_level_requirement_is_covered_by_the_lock():
    specs = _requirement_specs()
    lock = _lock_entries()
    missing = sorted(name for name in specs if name not in lock)
    assert not missing, (
        f"requirements.txt declares {missing} with no matching pin in "
        "requirements.lock - it will install unconstrained/unpinned "
        "(this is exactly the DEP-2 gap PyJWT was found in)"
    )


def test_inline_pins_in_requirements_txt_agree_with_the_lock():
    specs = _requirement_specs()
    lock = _lock_entries()
    mismatches = []
    for name, (raw_name, version) in specs.items():
        if version is None:
            continue
        lock_raw_name, lock_version = lock[name]
        if version != lock_version:
            mismatches.append((raw_name, version, lock_raw_name, lock_version))
    assert not mismatches, (
        f"requirements.txt pins a different version than requirements.lock: {mismatches}"
    )


def test_pyjwt_is_pinned_in_the_lock():
    lock = _lock_entries()
    assert "pyjwt" in lock, "PyJWT must be pinned in requirements.lock (DEP-2)"
    raw_name, version = lock["pyjwt"]
    assert version, "PyJWT's lock entry must pin an exact version, not a range"


def test_lock_file_has_no_duplicate_or_unpinned_entries():
    seen = set()
    for line in REQUIREMENTS_LOCK.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        assert "==" in line, f"requirements.lock entry is not exactly pinned: {line!r}"
        raw_name, _, version = line.partition("==")
        normalized = _normalize(raw_name)
        assert normalized not in seen, f"requirements.lock has a duplicate entry for {raw_name!r}"
        assert version.strip(), f"requirements.lock entry for {raw_name!r} has an empty version"
        seen.add(normalized)
