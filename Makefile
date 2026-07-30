.PHONY: test compile verify

PYTHON ?= python3
WORKER_DIR := workflow/skills/worker
POLLER_DIR := workflow/skills/poller

# Canonical worker/poller verification entry point.
test:
	$(PYTHON) -m unittest discover -s $(WORKER_DIR)/tests -p 'test_*.py' -v
	$(PYTHON) -m unittest discover -s $(POLLER_DIR)/tests -p 'test_*.py' -v
	$(PYTHON) -m unittest discover -s workflow/runner/tests -p 'test_*.py' -v

compile:
	$(PYTHON) -m py_compile $(wildcard workflow/scripts/*.py) $(wildcard workflow/runner/*.py) $(wildcard workflow/runner/tests/*.py) $(wildcard $(WORKER_DIR)/scripts/*.py) $(wildcard $(WORKER_DIR)/tests/*.py) $(POLLER_DIR)/poller_policy.py $(wildcard $(POLLER_DIR)/scripts/*.py) $(wildcard $(POLLER_DIR)/tests/*.py)

verify: test compile
	git diff --check
	$(PYTHON) workflow/scripts/verify_installation.py
