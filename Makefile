.PHONY: install run run-one demo-heal dashboard test

# Pick an interpreter that actually has the deps, in order of preference:
# the project venv, then `uv run`, then whatever python3 is on PATH.
# Everything is invoked as `$(PY) -m <tool>` so nothing needs to be on PATH.
PY := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; \
              elif command -v uv >/dev/null 2>&1; then echo "uv run python"; \
              else echo python3; fi)

install:        ## create .venv and install deps (uses uv when available)
	@if command -v uv >/dev/null 2>&1; then \
	  uv venv --allow-existing && uv pip install -r requirements.txt; \
	else \
	  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt; \
	fi

run:            ## run the full pipeline across all sources
	$(PY) -m radar.pipeline

run-one:        ## run one source: make run-one SOURCE=mlh-hackathons
	$(PY) -m radar.pipeline --source $(SOURCE)

demo-heal:      ## simulate a site redesign and watch the radar heal itself
	$(PY) -m radar.pipeline --simulate-breakage $(SOURCE)

dashboard:      ## serve the dashboard at http://localhost:8000
	$(PY) -m uvicorn dashboard.app:app --reload

test:
	$(PY) -m pytest -q
