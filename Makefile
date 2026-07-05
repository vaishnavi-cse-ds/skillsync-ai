# SkillSync AI — Makefile
# Run all commands from the skillsync-ai/ directory

.PHONY: install playground run test lint clean help

# ── Dependencies ──────────────────────────────────────────────────────────────
install:
	uv sync

# ── Local Development ─────────────────────────────────────────────────────────
# Windows users: run the uv command directly instead (see README.md)
playground:
	uv run adk web app --host 127.0.0.1 --port 18081 --reload_agents

run:
	uv run uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8000 --reload

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	uv run pytest tests/unit/ -v

test-integration:
	uv run pytest tests/integration/ -v

# ── Code Quality ──────────────────────────────────────────────────────────────
lint:
	uv run ruff check app/ tests/
	uv run ruff format --check app/ tests/

format:
	uv run ruff format app/ tests/

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	@echo "SkillSync AI — Available commands:"
	@echo "  make install          Install Python dependencies"
	@echo "  make playground       Start ADK playground UI at http://localhost:18081"
	@echo "  make run              Start FastAPI server at http://localhost:8000"
	@echo "  make test             Run unit tests"
	@echo "  make test-integration Run integration tests"
	@echo "  make lint             Check code style"
	@echo "  make format           Auto-format code"
	@echo "  make clean            Remove cached files"
