# Maintainer shortcuts. The only target today is the release helper
# (docs/RELEASING.md → Release helper); everything else uses bun/uv directly.

.PHONY: release release-dry release-publish

release: ## Cut a release: asks stable/beta, draft/publish, then confirms
	uv run python scripts/release.py

release-dry: ## Show the release plan, change nothing
	uv run python scripts/release.py --dry-run

release-publish: ## Publish an existing draft: make release-publish TAG=v0.5.8
	@test -n "$(TAG)" || { echo "usage: make release-publish TAG=vX.Y.Z[-beta.N]"; exit 2; }
	uv run python scripts/release.py --publish $(TAG)
