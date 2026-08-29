PYTHON ?= python3
.PHONY: deps fixture scrape exercise serve test clean

# The orchestrator needs PyYAML. The pipeline does not need anything.
deps:
	$(PYTHON) -m pip install -r requirements.txt


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

serve: fixture
	$(PYTHON) -m http.server 8000

test:
	$(PYTHON) -m unittest discover -s pipeline/tests -t . -v
	$(PYTHON) -m unittest discover -s orchestrator/tests -t . -v

clean:
	rm -f data/papers.db data/papers.json artifacts/raw-scrape.json
