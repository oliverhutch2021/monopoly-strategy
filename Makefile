# Monopoly Meta: everything you run on the PC is a target here. See RUNNING.md.
#
# The Python environment lives on the WSL disk (fast); the repo can stay on a Windows drive.

SHELL := /bin/bash
VENV ?= $(HOME)/.venvs/monopoly-strategy
PY := $(VENV)/bin/python
FORCE ?=
FORCE_FLAG := $(if $(FORCE),--force,)
WATCH ?= 1
JOB_FLAGS := $(FORCE_FLAG) $(if $(filter 0,$(WATCH)),--no-watch,)
HOST ?= 127.0.0.1
PORT ?= 8765

.DEFAULT_GOAL := help
.PHONY: help setup test golden doctor sync status watch play v03 exploit v04 v05 deep final-check review review2 smoke

help:  ## List the commands
	@grep -hE '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | expand -t 14

setup:  ## Create or update the Python environment (Python 3.12, on the WSL disk)
	@command -v uv >/dev/null || { echo "uv is missing: run bash bootstrap.sh"; exit 1; }
	@test -x $(PY) || uv venv --quiet --python 3.12 $(VENV)
	uv pip install --quiet --python $(PY) -e ".[dev]"
	@echo "Python environment ready at $(VENV)"

test:  ## Run the test suite
	$(PY) -m pytest -q -p no:cacheprovider

golden:  ## Check the stored regression digests (identical games to v0.3)
	$(PY) tests/golden.py

doctor:  ## Check this machine and print a pass/warn/fail table
	$(PY) scripts/doctor.py

sync:  ## Fast-forward to the code Claude left in .sync/claude.bundle
	$(PY) scripts/jobs.py sync

status:  ## Show which job steps are done
	$(PY) scripts/jobs.py status

watch:  ## Watch the running job's games live on a board in your browser (Ctrl+C stops it; the job carries on)
	$(PY) scripts/watch.py --host $(HOST) --port $(PORT)

play:  ## Play against the meta agents yourself, in your browser (Ctrl+C stops it)
	$(PY) scripts/watch.py --play --host $(HOST) --port $(PORT)

v03:  ## Run 2: finish v0.3 (about an hour; resumable; FORCE=1 restarts on new code)
	$(PY) scripts/jobs.py run v03 $(JOB_FLAGS)

exploit:  ## Run 3: can a bigger search beat the meta agents? (2-3 hours; resumable)
	$(PY) scripts/jobs.py run exploit $(JOB_FLAGS)

v04:  ## Run 4: unconventional strategies, with run 3 as its control (about 6 hours; resumable)
	$(PY) scripts/jobs.py run v04 $(JOB_FLAGS)

v05:  ## Run 5: harden the meta agents against the new moves, then re-measure them (about 7 hours; resumable)
	$(PY) scripts/jobs.py run v05 $(JOB_FLAGS)

deep:  ## Run 6: every study at 10x the samples with the final meta agents (about 8 hours; resumable)
	$(PY) scripts/jobs.py run deep $(JOB_FLAGS)

final-check:  ## After run 6: re-measure the 4-player official agent against its strongest known exploit (about 5 minutes)
	$(PY) scripts/jobs.py run final-check $(JOB_FLAGS)

review:  ## Run 7: the methodology review's corrections and rule-sensitivity tests (about 2 hours; resumable)
	$(PY) scripts/jobs.py run review $(JOB_FLAGS)

review2:  ## Run 8: the updated review's fixes: own-turn horizons and house auctions re-measured (about 75 minutes)
	$(PY) scripts/jobs.py run review2 $(JOB_FLAGS)

smoke:  ## Two-minute check that the job runner works end to end
	$(PY) scripts/jobs.py run smoke $(JOB_FLAGS)
