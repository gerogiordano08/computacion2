PYTHON ?= python3

.PHONY: run install test clean

run:
	$(PYTHON) src/main.py

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m unittest discover -s tests -v

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
	find . -maxdepth 1 -type f -name 'dump_*.json' -delete
