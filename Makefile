.PHONY: help venv install lint test run clean

PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
PIP := $(BIN)/pip
PY := $(BIN)/python
ANCHOR := $(BIN)/anchor

help:
	@printf '%s\n' "Targets:" \
		"  make venv     - create local .venv" \
		"  make install  - install project in editable mode with dev tools" \
		"  make lint     - run hard lint checks" \
		"  make test     - run unit tests" \
		"  make run      - run anchor from the local venv" \
		"  make clean    - remove virtualenv and cache artifacts"

venv:
	$(PYTHON) -m venv $(VENV)

install: venv
	$(PIP) install -e ".[dev]"

lint: install
	$(BIN)/ruff check src tests

test: install
	PYTHONPATH=$(PWD)/src $(PY) -m unittest discover -s tests -v

run: install
	$(ANCHOR) --help

clean:
	rm -rf $(VENV) build dist *.egg-info
