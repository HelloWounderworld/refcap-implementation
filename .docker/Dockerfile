FROM nvidia/cuda:12.6.1-devel-ubuntu22.04

ARG USERNAME=user
ARG USERNAME

SHELL ["/bin/bash", "-c"]

ARG DEBIAN_FRONTEND=noninteractive
ENV GIT_SSL_NO_VERIFY=true
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONUTF8=1
ENV PIP_NO_CACHE_DIR=off

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install --assume-yes --no-install-recommends \
    ca-certificates \
    build-essential \
    git \
    unzip \
    nano \
    curl \
    wget \
    gnupg2 \
    lsb-release \
    libssl-dev \
    zlib1g-dev \
    libbz2-dev \
    libreadline-dev \
    libsqlite3-dev \
    llvm \
    libncurses5-dev \
    libncursesw5-dev \
    xz-utils \
    tk-dev \
    libxml2-dev \
    libxmlsec1-dev \
    libffi-dev \
    liblzma-dev \
    python3-openssl \
    libopenblas-base \
    libopenblas-dev \
    logrotate \
    less \
    sudo \
    apt-utils \
    dpkg \
    supervisor \
    mecab \
    libmecab-dev \
    mecab-ipadic \
    cmake \
    ninja-build \
    build-essential \
    ffmpeg \
    gcc \
    g++ \
    && find /etc /usr -name mecabrc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt

ENV PYENV_ROOT /opt/.pyenv
ENV PATH ${PYENV_ROOT}/bin:${PYENV_ROOT}/shims:${PATH}
ARG PYTHON_VERSION=3.10.15

RUN git clone https://github.com/pyenv/pyenv.git ${PYENV_ROOT} \
    && echo 'export PATH="${PYENV_ROOT}/bin:${PYENV_ROOT}/shims:$PATH"' \
    && echo 'eval "$(pyenv init -)"' >> ~/.bashrc \
    && eval "$(pyenv init -)" \
    && source ~/.bashrc \
    && CFLAGS=-I/usr/include LDFLAGS=-L/usr/lib pyenv install -v ${PYTHON_VERSION} \
    && pyenv global ${PYTHON_VERSION} \
    && pyenv rehash

WORKDIR /${USERNAME}

COPY ./../ .

RUN apt-get update \
    && apt-get -y upgrade \
    && echo 'export PATH="/usr/local/cuda/bin${PATH:+:${PATH}}"' \
    && echo 'export LD_LIBRARY_PATH="/usr/local/cuda/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"' \
    && source ~/.bashrc \
    && python -m pip install --upgrade pip

# EXPOSE 8000

CMD ["supervisord", "-c", "supervisord.conf"]
