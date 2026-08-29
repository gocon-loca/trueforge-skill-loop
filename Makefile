# PEP 668 forbids pip installing into a system Python, so `make deps` builds a venv and
# every target then picks it up automatically. Override with PYTHON=... if you prefer.
VENV ?= .venv
PYTHON ?= $(shell [ -x $(VENV)/bin/python ] && echo $(VENV)/bin/python || echo python3)
.PHONY: deps demo map trueforge-skills verify-skill fixture scrape exercise serve test clean

# The orchestrator needs PyYAML. The pipeline does not need anything.
deps:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --quiet --upgrade pip
	$(VENV)/bin/pip install --quiet -r requirements.txt
	@echo "dependencies installed into $(VENV); every target now uses it automatically"


# Offline, deterministic path. No network, no credentials. This is the exercise gate.
fixture:
	$(PYTHON) -m pipeline.scrape --input fixtures/brightdata-papers.json

# Live acquisition. Requires BRIGHTDATA_* in .env.
scrape:
	@set -a; \
	if [ -f .env ]; then . ./.env; fi; \
	set +a; \
	if [ -z "$$BRIGHTDATA_COLLECTOR_ID" ]; then \
		echo "BRIGHTDATA_COLLECTOR_ID is not set. Copy .env.example to .env and fill it in, or use 'make fixture' for the offline path." >&2; \
		exit 2; \
	fi; \
	$(PYTHON) -m pipeline.scrape --collector-id "$$BRIGHTDATA_COLLECTOR_ID"

# A minted skill is untrusted until it completes one passing offline run.
exercise: test fixture

serve: fixture map
	$(PYTHON) -m http.server 8000

test:
	$(PYTHON) -m unittest discover -s pipeline/tests -t . -v
	$(PYTHON) -m unittest discover -s orchestrator/tests -t . -v

clean:
	rm -f data/papers.db data/papers.json artifacts/raw-scrape.json

# The loop end to end, offline. No credentials, no operator keys.
demo:
	$(PYTHON) -m orchestrator.demo

# One skill's own verification. The only command a minted skill may invoke.
verify-skill:
	@test -n "$(SKILL)" || { echo "SKILL=<name> is required" >&2; exit 2; }
	$(PYTHON) -m orchestrator.verify_skill $(SKILL)

<<<<<<< HEAD
# Register this registry with a running TrueForge instance. No credentials:
# the repository is public, so TrueForge fetches the packs itself.
trueforge-skills:
	$(PYTHON) scripts/register_skills.py
=======
# Build the interconnection graph and render it.
map:
	$(PYTHON) -m pipeline.graph
	@echo "open map/board.html after: make serve"
>>>>>>> 2b411dc (Build the interconnection map, and fix make deps on a clean machine)
