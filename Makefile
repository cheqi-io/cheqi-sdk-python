ENV ?= test

SPEC_LOCAL_URL := http://localhost:8080/v3/api-docs.yaml
SPEC_TEST_URL := https://test.api.cheqi.io/v3/api-docs.yaml
SPEC_SANDBOX_URL := https://sandbox.api.cheqi.io/v3/api-docs.yaml
SPEC_PROD_URL := https://api.cheqi.io/v3/api-docs.yaml

ifeq ($(ENV),local)
SPEC_URL := $(SPEC_LOCAL_URL)
else ifeq ($(ENV),test)
SPEC_URL := $(SPEC_TEST_URL)
else ifeq ($(ENV),sandbox)
SPEC_URL := $(SPEC_SANDBOX_URL)
else ifeq ($(ENV),prod)
SPEC_URL := $(SPEC_PROD_URL)
else
$(error Unsupported ENV '$(ENV)'. Use one of: local, test, sandbox, prod)
endif

GENERATED_DIR := src/cheqi/models/generated

.PHONY: fetch-spec generate spec-check test lint typecheck

fetch-spec:
	curl -fsSL $(SPEC_URL) -o openapi.yaml
	@echo "Spec updated in openapi.yaml."

generate:
	rm -rf /tmp/cheqi-python-gen
	openapi-generator generate \
		-i openapi.yaml \
		-g python \
		-o /tmp/cheqi-python-gen \
		--global-property models \
		--additional-properties=packageName=cheqi_generated,projectName=cheqi-generated,hideGenerationTimestamp=true
	rm -rf $(GENERATED_DIR)
	mkdir -p $(GENERATED_DIR)
	cp /tmp/cheqi-python-gen/cheqi_generated/models/*.py $(GENERATED_DIR)/
	perl -pi -e 's/from cheqi_generated\.models/from cheqi.models.generated/g' $(GENERATED_DIR)/*.py
	rm -rf /tmp/cheqi-python-gen
	rm -f openapitools.json
	@echo "Generated OpenAPI models in $(GENERATED_DIR)/"

spec-check:
	@curl -fsSL $(SPEC_URL) -o openapi.yaml.tmp
	@if diff -q openapi.yaml openapi.yaml.tmp > /dev/null 2>&1; then \
		echo "Spec is up to date."; \
	else \
		echo "ERROR: Local openapi.yaml differs from $(SPEC_URL)"; \
		echo "Run 'make fetch-spec' to update."; \
		diff openapi.yaml openapi.yaml.tmp || true; \
		rm openapi.yaml.tmp; \
		exit 1; \
	fi
	@rm -f openapi.yaml.tmp

test:
	uv run pytest

lint:
	uv run ruff check src/ tests/

typecheck:
	uv run mypy src/
