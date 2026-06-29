# Birds, Bugs & Botanicals – pipeline Makefile
# Requires: uv (https://docs.astral.sh/uv/getting-started/installation/)
# On Windows: run from Git Bash or WSL

.DEFAULT_GOAL := help
.PHONY: help setup run dry-run \
        run-bird run-bug run-botanical \
        auth-tiktok auth-tiktok-save \
        auth-instagram auth-instagram-refresh \
        test test-full \
        eval eval-fast eval-save \
        clean

# uv run automatically uses the .venv created by `make setup`
UV  := uv
RUN := uv run

# ── Setup ──────────────────────────────────────────────────────────────────────

setup:           ## Create .venv and install all dependencies
	$(UV) venv .venv
	$(UV) pip install -r requirements.txt
	$(UV) pip install --dev pytest pytest-timeout
	@echo ""
	@echo "Environment ready. Copy .env.example to .env and fill in your API keys."

# ── Pipeline ───────────────────────────────────────────────────────────────────

dry-run:         ## Generate content for a random species — no posting
	$(RUN) python main.py --dry-run

run:             ## Run the full pipeline — generate + post to Instagram & TikTok
	$(RUN) python main.py

run-bird:        ## Force today's feature to be a bird
	$(RUN) python main.py --category bird

run-bug:         ## Force today's feature to be a bug
	$(RUN) python main.py --category bug

run-botanical:   ## Force today's feature to be a botanical
	$(RUN) python main.py --category botanical

# ── Auth ───────────────────────────────────────────────────────────────────────

auth-tiktok:     ## Run TikTok OAuth login flow and print access token
	$(RUN) python tiktok_auth.py

auth-tiktok-save: ## Run TikTok OAuth login flow and save token to .env
	$(RUN) python tiktok_auth.py --save-env

auth-instagram:  ## Exchange a short-lived IG token for a 60-day long-lived token
	$(RUN) python instagram_auth.py --exchange

auth-instagram-refresh: ## Refresh an existing long-lived IG token (run before 60-day expiry)
	$(RUN) python instagram_auth.py --refresh

# ── Evals ──────────────────────────────────────────────────────────────────────

eval:            ## Generate content + run structural checks + LLM judge
	$(RUN) python evals/run_evals.py

eval-fast:       ## Structural checks only against saved fixture (no API calls)
	$(RUN) python evals/run_evals.py --use-fixture --no-judge

eval-save:       ## Generate content, run evals, and save fixture for pytest
	$(RUN) python evals/run_evals.py --save-fixture

# ── Tests ──────────────────────────────────────────────────────────────────────

test:            ## Fast structural tests using saved fixture (no API calls)
	$(RUN) pytest evals/test_structural.py

test-full:       ## Full test suite including LLM-as-judge quality tests (slow)
	$(RUN) pytest evals/ --llm-judge

# ── Maintenance ────────────────────────────────────────────────────────────────

clean:           ## Remove generated output folders and cached fixture
	rm -rf output/
	rm -f data/eval_fixture.json
	@echo "Cleaned output/ and eval fixture."

# ── Help ───────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "Birds, Bugs & Botanicals – available commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-18s %s\n", $$1, $$2}'
	@echo ""
	@echo "Typical first-time setup:"
	@echo "  1. make setup"
	@echo "  2. cp .env.example .env  (then fill in your API keys)"
	@echo "  3. make dry-run          (test content generation)"
	@echo "  4. make eval-save        (generate + save fixture for fast testing)"
	@echo "  5. make test             (run structural checks against fixture)"
	@echo ""
