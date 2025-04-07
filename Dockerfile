FROM ubuntu:oracular

RUN apt-get update \
    && apt-get install -y \
    python3 \
    python3-venv \
    curl \
    && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    gpg \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN wget -qO - \
    https://download.opensuse.org/repositories/home:/npreining:/debian-ubuntu-onedrive/xUbuntu_24.10/Release.key \
    | gpg --dearmor \
    | tee /usr/share/keyrings/obs-onedrive.gpg \
    > /dev/null \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/obs-onedrive.gpg] https://download.opensuse.org/repositories/home:/npreining:/debian-ubuntu-onedrive/xUbuntu_24.10/ ./" \
    | tee /etc/apt/sources.list.d/onedrive.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends --no-install-suggests \
    onedrive

# Use venv to install Playwright dependencies
WORKDIR /playwright

RUN python3 -m venv venv \
    && . venv/bin/activate \
    && pip install playwright \
    && playwright install-deps chromium-headless-shell \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /playwright

# Create and change to non-root user
RUN useradd -m runner
USER runner

# Create required folders
RUN mkdir /home/runner/src \
    && mkdir -p /home/runner/.config/onedrive \
    && mkdir /home/runner/data

WORKDIR /home/runner/src

# Install dependencies
RUN python3 -m venv venv \
    && . venv/bin/activate \
    && pip install playwright \
    pandas \
    xlrd \
    openpyxl \
    && playwright install --only-shell chromium-headless-shell

# Copy source files
COPY --chown=runner:runner main.py .

COPY --chown=runner:runner ./scripts/docker-run-prod.sh /home/runner/
COPY --chown=runner:runner ./scripts/docker-authenticate-prod.sh /home/runner/

ENTRYPOINT ["/home/runner/docker-run-prod.sh"]

