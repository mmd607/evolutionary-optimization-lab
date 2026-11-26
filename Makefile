# Developer shortcuts. Every target is a thin wrapper around a documented command, so the same
# checks can be run on Windows without make (see README "Development").
PYTHON ?= python
CONSTRAINTS := requirements/constraints-py312.txt

.PHONY: help install lint format format-check typecheck test coverage validate-configs smoke hpo-smoke data schema check lock

help:
	@echo "install          install package + dev tools with pinned constraints"
	@echo "lint             ruff check"
	@echo "format           ruff format (rewrites files)"
	@echo "format-check     ruff format --check"
	@echo "typecheck        mypy (strict)"
	@echo "test             pytest"
	@echo "coverage         pytest with coverage report"
	@echo "validate-configs validate configs/*.yaml and configs/studies/*.yaml"
	@echo "smoke            run the smoke study end-to-end into build/smoke (gitignored)"
	@echo "hpo-smoke        run the HPO smoke study (bundled data) end-to-end into build/hpo-smoke"
	@echo "data             download and verify the HPO datasets into data/raw (gitignored)"
	@echo "schema           regenerate docs/schemas/run_metadata.schema.json"
	@echo "check            lint + format-check + typecheck + coverage + validate-configs"
	@echo "lock             regenerate $(CONSTRAINTS) from the current environment"

install:
	$(PYTHON) -m pip install --upgrade "pip>=25.1"
	$(PYTHON) -m pip install -c $(CONSTRAINTS) -e . --group dev

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format .

format-check:
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest

coverage:
	$(PYTHON) -m pytest --cov --cov-report=term-missing

validate-configs:
	$(PYTHON) -m evooptlab validate-config configs/*.yaml configs/studies/*.yaml

smoke:
	$(PYTHON) -m evooptlab plan configs/studies/smoke.yaml
	$(PYTHON) -m evooptlab run configs/studies/smoke.yaml --root build/smoke --resume
	$(PYTHON) -m evooptlab diagnose configs/studies/smoke.yaml --root build/smoke
	$(PYTHON) -m evooptlab aggregate configs/studies/smoke.yaml --root build/smoke

hpo-smoke:
	$(PYTHON) -m evooptlab run configs/studies/hpo_smoke.yaml --root build/hpo-smoke --resume
	$(PYTHON) -m evooptlab test-eval configs/studies/hpo_smoke.yaml --root build/hpo-smoke
	$(PYTHON) -m evooptlab diagnose configs/studies/hpo_smoke.yaml --root build/hpo-smoke
	$(PYTHON) -m evooptlab aggregate configs/studies/hpo_smoke.yaml --root build/hpo-smoke

data:
	$(PYTHON) -m evooptlab data fetch bank_marketing california_housing wine_quality --data-dir data

schema:
	$(PYTHON) -m evooptlab schema run-metadata > docs/schemas/run_metadata.schema.json

check: lint format-check typecheck coverage validate-configs

lock:
	@head -n 3 $(CONSTRAINTS) > $(CONSTRAINTS).new
	$(PYTHON) -m pip freeze --exclude-editable >> $(CONSTRAINTS).new
	mv $(CONSTRAINTS).new $(CONSTRAINTS)
