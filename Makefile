.PHONY: install dev run test lint format clean build docker-build docker-run

# デフォルトターゲット
all: install

# uvを使った依存関係のインストール
install:
	uv sync

# 開発環境のセットアップ
dev:
	uv sync --dev
	uv run pre-commit install

# アプリケーションの実行
run:
	uv run claude-remote

# テストの実行
test:
	uv run pytest

# リンターの実行
lint:
	uv run flake8 claude_remote
	uv run mypy claude_remote

# コードフォーマット
format:
	uv run black claude_remote
	uv run black tests

# クリーンアップ
clean:
	find . -type d -name "__pycache__" -delete
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/
	rm -rf dist/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/

# パッケージのビルド
build:
	uv build

# Dockerイメージのビルド
docker-build:
	docker build -f docker/Dockerfile -t claude-remote .
	docker network create claude-remote-net || true

# Dockerでの実行
docker-run: docker-build
	docker-compose -f docker/docker-compose.yml up -d

# Dockerの停止
docker-stop:
	docker-compose -f docker/docker-compose.yml down

# ログの確認
logs:
	docker-compose -f docker/docker-compose.yml logs -f

# 環境設定ファイルの作成
setup-env:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env file from .env.example"; \
		echo "Please edit .env file to configure your settings"; \
	else \
		echo ".env file already exists"; \
	fi

# 完全セットアップ
setup: setup-env install

# ヘルプ
help:
	@echo "Claude Remote - 利用可能なコマンド:"
	@echo ""
	@echo "  install     - 依存関係をインストール"
	@echo "  dev         - 開発環境をセットアップ"
	@echo "  run         - アプリケーションを実行"
	@echo "  test        - テストを実行"
	@echo "  lint        - リンターを実行"
	@echo "  format      - コードをフォーマット"
	@echo "  clean       - 一時ファイルを削除"
	@echo "  build       - パッケージをビルド"
	@echo "  docker-build - Dockerイメージをビルド"
	@echo "  docker-run  - Dockerで実行"
	@echo "  docker-stop - Dockerを停止"
	@echo "  logs        - Dockerログを表示"
	@echo "  setup-env   - .envファイルを作成"
	@echo "  setup       - 完全セットアップ"
	@echo "  help        - このヘルプを表示"