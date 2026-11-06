.PHONY: check validate test

export PYTHONDONTWRITEBYTECODE := 1

check: validate test

validate:
	python3 -m runner.validate

test:
	python3 -m unittest discover -s runner -t . -p 'test_*.py'
