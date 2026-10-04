.PHONY: validate security kind-bootstrap kind-health

validate:
	python3 scripts/security/native-validators.py
	python3 -m py_compile $$(find . -name '*.py' -not -path './.venv/*' -not -path './.git/*')

security:
	SECURITY_DRY_RUN=1 scripts/security/trivy.sh
	SECURITY_DRY_RUN=1 scripts/security/checkov.sh
	SECURITY_DRY_RUN=1 scripts/security/gitleaks.sh

kind-bootstrap:
	scripts/kind-up.sh
	scripts/kind-health.sh
	kubectl apply -f argocd/app-of-apps.yaml

kind-health:
	scripts/kind-health.sh
