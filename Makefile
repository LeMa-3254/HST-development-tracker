.PHONY: test run build-site clean

PYTHON ?= python3
CONFIG ?= targeting.yaml
DB ?= data/tracker.db
OUTPUT ?= public

test:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s tests

run:
	$(PYTHON) pipeline/run.py --config $(CONFIG) --db $(DB)

build-site:
	$(PYTHON) site/build.py --config $(CONFIG) --db $(DB) --output $(OUTPUT)

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
