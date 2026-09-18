.PHONY: test run build-site clean

PYTHON ?= python3
CONFIG ?= targeting.yaml
DB ?= data/tracker.db
OUTPUT ?= public
ENV_FILE ?= .env

# Load .env (gitignored) into the environment so local runs see ANTHROPIC_API_KEY.
# Nothing in the Python code reads .env on its own. GitHub Actions has no .env and
# supplies the key as a repository secret instead, so the missing-file case is normal.
LOAD_ENV = set -a; if [ -f ./$(ENV_FILE) ]; then . ./$(ENV_FILE); fi; set +a;

test:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s tests

run:
	$(LOAD_ENV) $(PYTHON) pipeline/run.py --config $(CONFIG) --db $(DB)

build-site:
	$(LOAD_ENV) $(PYTHON) site/build.py --config $(CONFIG) --db $(DB) --output $(OUTPUT)

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
