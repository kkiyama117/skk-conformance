.PHONY: check validate test

check: validate test

validate:
	python3 -m runner.validate

test:
	python3 -m unittest discover -s runner -t . -p 'test_*.py'
