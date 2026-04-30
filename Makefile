.PHONY: guardrail-db smoke-contract smoke-http smoke-verify

guardrail-db:
	python3 scripts/guardrails/scan_db_direct_access.py > .ci/db_direct_access_baseline.json
	python3 scripts/guardrails/check_db_direct_access_guardrail.py
	python3 scripts/guardrails/classify_bff_db_direct_access.py

smoke-contract:
	bash scripts/check_web_app_smoke_scripts.sh
	python3 -m py_compile scripts/verify_web_app_http_smoke.py

smoke-http:
	bash scripts/run_web_app_http_smoke.sh

smoke-verify:
	python3 scripts/verify_web_app_http_smoke.py
