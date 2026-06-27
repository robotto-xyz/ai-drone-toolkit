.PHONY: sample-log test check clean-test-artifacts

SAMPLE_LOG_URL := https://raw.githubusercontent.com/PX4/pyulog/main/test/sample.ulg
SAMPLE_LOG := tests/sample.ulg

sample-log:
	curl -sL "$(SAMPLE_LOG_URL)" -o "$(SAMPLE_LOG)"

test:
	uv run pytest

check: sample-log test

clean-test-artifacts:
	rm -f "$(SAMPLE_LOG)"
