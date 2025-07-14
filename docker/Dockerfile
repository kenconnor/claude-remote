FROM ubuntu:22.04

# 基本パッケージのインストール
RUN apt-get update && apt-get install -y \
    curl \
    git \
    python3 \
    python3-pip \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Node.js 18.xのインストール
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs

# Claude CLIのインストール（最新版）
RUN npm install -g @anthropic-ai/claude-code@latest

# 作業ディレクトリ
WORKDIR /workspace

# 非rootユーザーの作成（rootのままにする）
RUN useradd -m -u 1000 claude && \
    chown -R claude:claude /workspace

# USER claude  # コメントアウト - rootで実行

# エントリポイント
ENTRYPOINT ["claude"]