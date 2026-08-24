VENV := .venv/bin
LOG_DIR := app/logs
API_PID := $(LOG_DIR)/api.pid
WORKER_PID := $(LOG_DIR)/worker.pid
FRONTEND_PID := $(LOG_DIR)/frontend.pid

# bash everywhere: dash's kill builtin cannot signal process groups
# (`kill -TERM -- -PID` -> "Illegal number"), which orphans vite/celery children.
SHELL := /bin/bash

.PHONY: up api worker frontend stop logs test check-arch

# Start the whole stack detached: API + worker + frontend dev server.
up: api worker frontend

# Start the API in the background; chat turns stay pending until a worker runs too.
# Every service runs as its own process-group leader (setsid), so `stop` can
# take down the entire tree (npm -> vite, celery master -> pool). Logs start
# fresh on every launch.
api:
	@mkdir -p $(LOG_DIR)
	@if [ -f "$(API_PID)" ] && kill -0 $$(cat "$(API_PID)") 2>/dev/null; then \
		echo "API already running (pid $$(cat "$(API_PID)"))"; \
	elif ss -tln 2>/dev/null | grep -q ':8000 '; then \
		echo "port 8000 already in use by another process — not started by make"; \
	else \
		nohup setsid $(VENV)/uvicorn app.main:app --port 8000 > $(LOG_DIR)/api.log 2>&1 & \
		echo $$! > "$(API_PID)"; \
		echo "API started (pid $$!, log: $(LOG_DIR)/api.log)"; \
	fi

# REQUIRED for chat: consumes the Celery queue (Redis broker).
worker:
	@mkdir -p $(LOG_DIR)
	@if [ -f "$(WORKER_PID)" ] && kill -0 $$(cat "$(WORKER_PID)") 2>/dev/null; then \
		echo "Worker already running (pid $$(cat "$(WORKER_PID)"))"; \
	else \
		nohup setsid $(VENV)/celery -A app.worker:celery worker --concurrency=1 -l warning --without-gossip --without-mingle > $(LOG_DIR)/celery.log 2>&1 & \
		echo $$! > "$(WORKER_PID)"; \
		echo "Worker started (pid $$!, log: $(LOG_DIR)/celery.log)"; \
	fi

# React/Vite dev server on :5173 (proxies /v1 and /health to the API).
frontend:
	@mkdir -p $(LOG_DIR)
	@if [ -f "$(FRONTEND_PID)" ] && kill -0 $$(cat "$(FRONTEND_PID)") 2>/dev/null; then \
		echo "Frontend already running (pid $$(cat "$(FRONTEND_PID)"))"; \
	elif ss -tln 2>/dev/null | grep -q ':5173 '; then \
		echo "port 5173 already in use by another process — not started by make"; \
	else \
		nohup setsid bash -c 'cd frontend && exec npm run dev' > $(LOG_DIR)/frontend.log 2>&1 & \
		echo $$! > "$(FRONTEND_PID)"; \
		echo "Frontend started (pid $$!, log: $(LOG_DIR)/frontend.log)"; \
	fi

# Stop the backgrounded API, worker, and frontend — whole process groups, so
# no orphaned children survive holding ports.
stop:
	@for f in "$(API_PID)" "$(WORKER_PID)" "$(FRONTEND_PID)"; do \
		if [ -f "$$f" ]; then \
			pid=$$(cat "$$f"); \
			if kill -0 "$$pid" 2>/dev/null; then \
				kill -TERM -- "-$$pid" 2>/dev/null || kill "$$pid"; \
				echo "stopped pid $$pid ($$f)"; \
			else \
				echo "stale pidfile $$f"; \
			fi; \
			rm -f "$$f"; \
		fi; \
	done

# Follow all service logs at once.
logs:
	@tail -n 10 -F $(LOG_DIR)/api.log $(LOG_DIR)/celery.log $(LOG_DIR)/frontend.log

test:
	$(VENV)/pytest

# Fail on any app -> app.addons or registry -> app import edge.
check-arch:
	$(VENV)/python scripts/check_architecture.py
