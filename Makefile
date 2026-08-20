.DEFAULT_GOAL := up

compose        := docker compose -f infra/compose.yml
gpu_compose    := $(compose) -f infra/compose.gpu.yml

# Profile groups
CORE_PROFILES  := --profile core --profile redis-local --profile app --profile worker
DEV_PROFILES   := $(CORE_PROFILES) --profile frontend-dev
PROD_PROFILES  := $(CORE_PROFILES) --profile frontend-prod

# Detect GPU mode
ifeq ($(USE_GPU),1)
  compose_cmd := $(gpu_compose)
else
  compose_cmd := $(compose)
endif

.PHONY: up down clean logs arcadedb up-app up-worker up-full-dev up-full-prod \
        rebuild build-all once-worker

# Core commands
up:
	$(compose_cmd) $(DEV_PROFILES) up -d

down: 
	$(compose) --profile core --profile redis-local --profile app --profile worker --profile frontend-dev --profile frontend-prod down

clean:
	$(compose) down -v

logs:
	$(compose) logs -f

logs-%:
	$(compose) logs -f $*

# Shorthands
arcadedb: ; $(compose) --profile core up -d arcadedb
up-app: ; $(compose) --profile core --profile redis-local --profile app up -d
up-worker: ; $(compose) --profile core --profile redis-local --profile worker up -d

# Full stacks
up-full-dev: ; $(compose_cmd) $(DEV_PROFILES) up -d
up-full-prod: ; $(compose_cmd) $(PROD_PROFILES) up -d

# Rebuilds
rebuild:
	$(compose_cmd) $(DEV_PROFILES) build
	$(compose_cmd) $(DEV_PROFILES) up -d

rebuild-%:
	$(compose_cmd) $(DEV_PROFILES) build $*
	$(compose_cmd) $(DEV_PROFILES) up -d $*

build-all:
	$(compose) $(DEV_PROFILES) $(PROD_PROFILES) build

# Run worker once
once-worker:
	$(compose) run --rm worker uv run -- python -c "from src.worker import run_worker_once; print('processed:', run_worker_once())"
