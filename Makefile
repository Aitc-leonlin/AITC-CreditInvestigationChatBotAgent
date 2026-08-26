PYTHON := python3
VENV := venv
VENV_PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: setup run start test-regression

$(VENV_PYTHON):
	$(PYTHON) -m venv $(VENV)

setup: $(VENV_PYTHON)
	$(PIP) install -r requirements.txt

run: $(VENV_PYTHON)
	$(VENV_PYTHON) app.py

start: setup
	$(VENV_PYTHON) app.py

test-regression: $(VENV_PYTHON)
	$(VENV_PYTHON) scripts/run_regression_tests.py
