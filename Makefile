.PHONY: install run run-one demo-heal dashboard test

install:
	pip install -r requirements.txt

run:            ## run the full pipeline across all sources
	python -m radar.pipeline

run-one:        ## run one source: make run-one SOURCE=devpost-hackathons
	python -m radar.pipeline --source $(SOURCE)

demo-heal:      ## simulate a site redesign and watch the radar heal itself
	python -m radar.pipeline --simulate-breakage $(SOURCE)

dashboard:      ## serve the dashboard at http://localhost:8000
	uvicorn dashboard.app:app --reload

test:
	pytest -q
