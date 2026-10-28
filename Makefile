# Monopoly Meta: everything you run on the PC is a target here. See RUNNING.md.
#
# The Python environment lives on the WSL disk (fast); the repo can stay on a Windows drive.

SHELL := /bin/bash
VENV ?= $(HOME)/.venvs/monopoly-strategy
PY := $(VENV)/bin/python
FORCE ?=
FORCE_FLAG := $(if $(FORCE),--force,)

.DEFAULT_GOAL := help
.PHONY: help setup test golden doctor sync status v03 exploit smoke

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

v03:  ## Run 2: finish v0.3 (about an hour; resumable; FORCE=1 restarts on new code)
	$(PY) scripts/jobs.py run v03 $(FORCE_FLAG)

exploit:  ## Run 3: can a bigger search beat the meta agents? (2-3 hours; resumable)
	$(PY) scripts/jobs.py run exploit $(FORCE_FLAG)

smoke:  ## Two-minute check that the job runner works end to end
	$(PY) scripts/jobs.py run smoke $(FORCE_FLAG)
