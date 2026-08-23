.PHONY: install run run-one demo-heal dashboard test

# Prefer uv, which resolves the project venv on its own. Fall back to the
# venv directly, then to python3 for machines with neither.
#
# Note for Arch-based systems (Omarchy): system Python ships PEP 668
# EXTERNALLY-MANAGED, so `pip install` against it is refused. Everything
# here stays inside .venv, and `make install` never touches system Python.
PY := $(shell if command -v uv >/dev/null 2>&1; then echo "uv run python"; \
              elif [ -x .venv/bin/python ]; then echo .venv/bin/python; \
              else echo python3; fi)

install:        ## create .venv and install dependencies
	@if command -v uv >/dev/null 2>&1; then \
	  uv venv --allow-existing && uv pip install -r requirements.txt; \
	else \
	  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt; \
	fi

run:            ## run the full pipeline across all sources
	$(PY) -m radar.pipeline

run-one:        ## run one source: make run-one SOURCE=mlh-hackathons
	$(PY) -m radar.pipeline --source $(SOURCE)

demo-heal:      ## break one source and watch the radar heal it
	$(PY) -m radar.pipeline --source $(SOURCE) --simulate-breakage $(SOURCE)

dashboard:      ## serve the dashboard at http://localhost:8000
	$(PY) -m uvicorn dashboard.app:app --reload

test:
	$(PY) -m pytest -q
