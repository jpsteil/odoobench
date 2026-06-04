"""Docker template strings for OdooBench Docker Export.

All templates use string.Template with $variable substitution.
Shell script variables use $$ to produce literal $ in output.
"""

from string import Template

DOCKER_COMPOSE_TEMPLATE = Template("""\
services:
  db:
    image: postgres:${postgres_version}
    environment:
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: odoo
      POSTGRES_DB: postgres
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U odoo"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

  odoo:
    build:
      context: .
      dockerfile: Dockerfile
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "${odoo_port}:8069"
      - "${longpolling_port}:8072"
    volumes:
      - odoo-filestore:/opt/odoo/filestore
      - ./qlf:/opt/odoo/qlf
      - ./odoo.conf:/opt/odoo/odoo.conf
    environment:
      - DB_HOST=db
      - DB_PORT=5432
      - DB_USER=odoo
      - DB_PASSWORD=odoo
      - DB_NAME=${db_name}
    restart: unless-stopped

  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "${mailpit_http_port}:8025"
    restart: unless-stopped

volumes:
  pgdata:
  odoo-filestore:
""")

DOCKERFILE_TEMPLATE = Template("""\
FROM python:${python_version}-bookworm

# System dependencies for Odoo
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \\
    libpq-dev \\
    libxml2-dev \\
    libxslt1-dev \\
    libldap2-dev \\
    libsasl2-dev \\
    libjpeg-dev \\
    zlib1g-dev \\
    libfreetype6-dev \\
    liblcms2-dev \\
    libffi-dev \\
    postgresql-client \\
    wkhtmltopdf \\
    node-less \\
    npm \\
    && rm -rf /var/lib/apt/lists/*

# Install rtlcss for RTL support
RUN npm install -g rtlcss

# Create odoo user and directories
RUN useradd -m -d /opt/odoo -s /bin/bash odoo \\
    && mkdir -p /opt/odoo/filestore \\
    && mkdir -p /opt/odoo/qlf \\
    && mkdir -p /opt/odoo/init

# Copy Python requirements and install first (better layer caching)
COPY requirements.txt /opt/odoo/requirements.txt
RUN pip install --no-cache-dir -r /opt/odoo/requirements.txt

# Copy source tree
COPY qlf/ /opt/odoo/qlf/

${copy_extra_files}
# Copy configuration and scripts
COPY odoo.conf /opt/odoo/odoo.conf
COPY entrypoint.sh /opt/odoo/entrypoint.sh
COPY neutralize.sql /opt/odoo/neutralize.sql

# Copy init data (database dump)
COPY init/ /opt/odoo/init/

# Copy filestore archive
COPY filestore.tar.gz /opt/odoo/filestore.tar.gz

# Set permissions
RUN chown -R odoo:odoo /opt/odoo \\
    && chmod +x /opt/odoo/entrypoint.sh

USER odoo
WORKDIR /opt/odoo

EXPOSE 8069 8072

ENTRYPOINT ["/opt/odoo/entrypoint.sh"]
""")

# Note: $$ in Template produces a literal $ in the output.
# Shell variables like $DB_HOST become $$DB_HOST in the template.
ENTRYPOINT_TEMPLATE = Template("""\
#!/bin/bash
set -e

INIT_FLAG="/opt/odoo/filestore/.initialized"
DB_NAME="$${DB_NAME:-${db_name}}"
DB_HOST="$${DB_HOST:-db}"
DB_PORT="$${DB_PORT:-5432}"
DB_USER="$${DB_USER:-odoo}"
DB_PASSWORD="$${DB_PASSWORD:-odoo}"

export PGPASSWORD="$$DB_PASSWORD"

# ---- Wait for PostgreSQL ----
echo "Waiting for PostgreSQL at $$DB_HOST:$$DB_PORT..."
until pg_isready -h "$$DB_HOST" -p "$$DB_PORT" -U "$$DB_USER" -q; do
    sleep 1
done
echo "PostgreSQL is ready."

# ---- First-boot initialization ----
if [ ! -f "$$INIT_FLAG" ]; then
    echo "============================================"
    echo "  First-boot initialization"
    echo "============================================"

    # Step 1: Create database if it doesn't exist
    echo "[1/5] Creating database $$DB_NAME..."
    psql -h "$$DB_HOST" -p "$$DB_PORT" -U "$$DB_USER" -d postgres \\
        -tc "SELECT 1 FROM pg_database WHERE datname = '$$DB_NAME'" | grep -q 1 \\
        || createdb -h "$$DB_HOST" -p "$$DB_PORT" -U "$$DB_USER" "$$DB_NAME"

    # Step 2: Restore database dump
    echo "[2/5] Restoring database from dump..."
    gunzip -c /opt/odoo/init/database.sql.gz | \\
        psql -h "$$DB_HOST" -p "$$DB_PORT" -U "$$DB_USER" -d "$$DB_NAME" -q

    # Step 3: Run neutralization SQL (BEFORE filestore - no lag with un-neutralized data)
    echo "[3/5] Neutralizing database..."
    psql -h "$$DB_HOST" -p "$$DB_PORT" -U "$$DB_USER" -d "$$DB_NAME" \\
        -f /opt/odoo/neutralize.sql -q

    # Step 4: Extract filestore
    echo "[4/5] Extracting filestore..."
    mkdir -p "/opt/odoo/filestore/$$DB_NAME"
    tar -xzf /opt/odoo/filestore.tar.gz --strip-components=1 -C "/opt/odoo/filestore/$$DB_NAME"
    rm -f /opt/odoo/filestore.tar.gz
    echo "Removed filestore archive to free disk space."

    # Step 5: Mark as initialized
    touch "$$INIT_FLAG"
    echo "[5/5] Initialization complete."
    echo "============================================"
fi

unset PGPASSWORD

# ---- Ensure addon directories exist ----
ADDONS_PATH=$$(grep -oP '^addons_path\\s*=\\s*\\K.*' /opt/odoo/odoo.conf || true)
IFS=',' read -ra ADDON_DIRS <<< "$$ADDONS_PATH"
for dir in "$${ADDON_DIRS[@]}"; do
    dir=$$(echo "$$dir" | xargs)
    if [ -n "$$dir" ] && [ ! -d "$$dir" ]; then
        echo "Creating missing addon directory: $$dir"
        mkdir -p "$$dir"
    fi
done

# ---- Start Odoo ----
echo "Starting Odoo..."
exec python /opt/odoo/qlf/${odoo_subdir}/odoo-bin \\
    --config=/opt/odoo/odoo.conf \\
    --db_host="$$DB_HOST" \\
    --db_port="$$DB_PORT" \\
    --db_user="$$DB_USER" \\
    --db_password="$$DB_PASSWORD" \\
    "$$@"
""")

START_ODOO_DOCKER_TEMPLATE = Template("""\
#!/bin/bash
set -euo pipefail

# Usage:
#   start_odoo_docker.sh                  # Auto-detect changed modules, start/restart
#   start_odoo_docker.sh --all            # Upgrade all installed repo modules
#   start_odoo_docker.sh --fresh [archive]  # Tear down, extract archive, rebuild
#   start_odoo_docker.sh -u my_module     # Pass-through to odoo-bin

# Paths - adjust DOCKER_DIR/BACKUP_DIR/LOG_DIR for your host environment
DOCKER_DIR="$$HOME/odoo-docker"
BACKUP_DIR="$$HOME/Documents/OdooBackups"
REPO_DIR="$$DOCKER_DIR/qlf/${repo_subdir}"
COMPOSE="docker compose -f $$DOCKER_DIR/docker-compose.yml"
ODOO_CONF="/opt/odoo/odoo.conf"
LOG_DIR="$$HOME/scripts/logs"
LOG_FILE="$$LOG_DIR/odoo-docker.log"

# Read db_name and odoo-bin path from the generated odoo.conf
CONF_FILE="$$DOCKER_DIR/odoo.conf"
if [ ! -f "$$CONF_FILE" ]; then
    echo "Error: $$CONF_FILE not found. Is DOCKER_DIR correct?"
    exit 1
fi
DB_NAME=$$(grep -oP '^db_name\\s*=\\s*\\K.*' "$$CONF_FILE" | xargs)
ODOO_BIN_LOCAL=$$(find "$$DOCKER_DIR/qlf" -name "odoo-bin" -type f | head -1)
if [ -z "$$ODOO_BIN_LOCAL" ]; then
    echo "Error: Could not find odoo-bin in $$DOCKER_DIR/qlf"
    exit 1
fi
ODOO_BIN=$$(echo "$$ODOO_BIN_LOCAL" | sed "s|$$DOCKER_DIR/qlf|/opt/odoo/qlf|")

mkdir -p "$$LOG_DIR"

# Colorize log output
colorize() {
    sed -u \\
        -e "s/\\(.*ERROR.*\\)/\\x1b[31m\\1\\x1b[0m/" \\
        -e "s/\\(.*WARNING.*\\)/\\x1b[33m\\1\\x1b[0m/" \\
        -e "s/\\(.*INFO.*\\)/\\x1b[32m\\1\\x1b[0m/" \\
        -e "s/\\(.*DEBUG.*\\)/\\x1b[36m\\1\\x1b[0m/"
}

# Extract a docker export archive into DOCKER_DIR
extract_archive() {
    local archive="$$1"
    echo "Extracting $$archive to $$DOCKER_DIR..."
    mkdir -p "$$DOCKER_DIR"
    tar xzf "$$archive" -C "$$DOCKER_DIR"
    echo "Extracted successfully."
}

# Clone the git repo if clone.conf exists and the subdir is missing
clone_repo_if_needed() {
    local clone_conf="$$DOCKER_DIR/clone.conf"
    if [ ! -f "$$clone_conf" ]; then
        return
    fi

    # Read clone.conf
    local repo_url subdir
    repo_url=$$(grep '^repo_url=' "$$clone_conf" | cut -d= -f2-)
    subdir=$$(grep '^subdir=' "$$clone_conf" | cut -d= -f2-)

    if [ -z "$$repo_url" ] || [ -z "$$subdir" ]; then
        echo "Warning: clone.conf is incomplete, skipping git clone"
        return
    fi

    local target_dir="$$DOCKER_DIR/qlf/$$subdir"

    if [ -d "$$target_dir" ]; then
        echo "Git repo already exists at $$target_dir"
        return
    fi

    # Ask for branch
    read -rp "Which branch for $$subdir? [main]: " branch
    branch="$${branch:-main}"

    echo "Cloning $$repo_url (branch: $$branch) into $$target_dir..."
    git clone --branch "$$branch" "$$repo_url" "$$target_dir"
    echo "Clone complete."
}

# First-time setup: if DOCKER_DIR doesn't exist, extract latest archive
if [ ! -d "$$DOCKER_DIR" ] || [ ! -f "$$DOCKER_DIR/docker-compose.yml" ]; then
    archive=$$(ls -t "$$BACKUP_DIR"/*_docker.tar.gz 2>/dev/null | head -1 || true)
    if [ -z "$$archive" ]; then
        echo "Error: $$DOCKER_DIR does not exist and no docker export found in $$BACKUP_DIR"
        echo "Run a Docker Export from OdooBench first."
        exit 1
    fi
    echo "First run - no Docker project found at $$DOCKER_DIR"
    extract_archive "$$archive"
    clone_repo_if_needed
fi

# --fresh mode: tear down, optionally extract new archive, rebuild
if [ "$${1:-}" = "--fresh" ]; then
    archive="$${2:-}"
    if [ -z "$$archive" ]; then
        archive=$$(ls -t "$$BACKUP_DIR"/*_docker.tar.gz 2>/dev/null | head -1 || true)
        if [ -z "$$archive" ]; then
            echo "Error: No docker export archive found in $$BACKUP_DIR"
            exit 1
        fi
        echo "No archive specified, using most recent: $$archive"
    fi
    if [ -f "$$DOCKER_DIR/docker-compose.yml" ]; then
        echo "Tearing down existing containers and volumes..."
        $$COMPOSE down -v
    fi
    rm -rf "$$DOCKER_DIR"
    extract_archive "$$archive"
    clone_repo_if_needed
    echo ""
    echo "Starting fresh Docker Compose..."
    COMPOSE="docker compose -f $$DOCKER_DIR/docker-compose.yml"
    $$COMPOSE up -d --build
    echo "Waiting for containers..."
    sleep 3
    echo "Tailing Odoo logs (Ctrl+C to stop)..."
    $$COMPOSE logs -f odoo 2>&1 | tee "$$LOG_FILE" | colorize
    exit 0
fi

# Ensure containers are running
ensure_up() {
    if ! $$COMPOSE ps --status running 2>/dev/null | grep -q odoo; then
        echo "Starting Docker containers..."
        $$COMPOSE up -d --build
        echo "Waiting for Odoo container to be ready..."
        sleep 3
    fi
}

# Helper: restart Odoo with optional flags, stream logs
run_odoo() {
    ensure_up
    if [ $$# -gt 0 ]; then
        echo "Stopping Odoo for upgrade..."
        $$COMPOSE stop odoo
        echo "Running: odoo-bin -c $$ODOO_CONF $$*"
        $$COMPOSE run --rm -T --entrypoint python odoo "$$ODOO_BIN" -c "$$ODOO_CONF" "$$@" 2>&1 | tee "$$LOG_FILE" | colorize
        echo ""
        echo "Upgrade complete. Starting Odoo normally..."
        $$COMPOSE start odoo
    else
        echo "Restarting Odoo..."
        $$COMPOSE restart odoo
    fi
    echo "Log file: $$LOG_FILE"
    echo "Tailing Odoo logs (Ctrl+C to stop)..."
    $$COMPOSE logs -f odoo 2>&1 | tee -a "$$LOG_FILE" | colorize
}

# --all mode: upgrade all installed modules from the repo
if [ "$${1:-}" = "--all" ]; then
    ensure_up
    # Get all module dirs in the repo
    repo_modules=()
    for dir in "$$REPO_DIR"/*/; do
        mod=$$(basename "$$dir")
        if [ -f "$$dir/__manifest__.py" ]; then
            repo_modules+=("$$mod")
        fi
    done

    # Query the Docker PostgreSQL for installed modules
    mod_in=$$(printf "'%s'," "$${repo_modules[@]}" | sed 's/,$$//')
    installed=$$($$COMPOSE exec -T db psql -U odoo -d "$$DB_NAME" -tAc \\
        "SELECT string_agg(name, ',') FROM ir_module_module WHERE state = 'installed' AND name IN ($$mod_in);" 2>/dev/null || echo "")

    if [ -z "$$installed" ]; then
        echo "No installed modules found. Starting Odoo normally."
        run_odoo
        exit 0
    fi

    echo "Upgrading all installed repo modules:"
    echo "$$installed" | tr ',' '\\n' | sed 's/^/  /'
    echo ""
    run_odoo -u "$$installed" --stop-after-init
    exit 0
fi

# Pass-through mode: if any other args given, forward to Odoo
if [ $$# -gt 0 ]; then
    echo "Starting Odoo with: $$*"
    run_odoo "$$@"
    exit 0
fi

# Auto-detect mode: find changed modules in repo
cd "$$REPO_DIR"

# Detect changed files: uncommitted first, then last commit
changed_files=$$(git diff --name-only HEAD 2>/dev/null || true)
diff_source="uncommitted changes"

if [ -z "$$changed_files" ]; then
    changed_files=$$(git diff --name-only HEAD~1 2>/dev/null || true)
    diff_source="last commit"
fi

if [ -z "$$changed_files" ]; then
    echo "No module changes detected. Starting Odoo normally."
    run_odoo
    exit 0
fi

# Extract unique top-level module directories that have a __manifest__.py
changed_modules=()
while IFS= read -r dir; do
    if [ -f "$$REPO_DIR/$$dir/__manifest__.py" ]; then
        changed_modules+=("$$dir")
    fi
done < <(echo "$$changed_files" | cut -d'/' -f1 | sort -u)

if [ $${#changed_modules[@]} -eq 0 ]; then
    echo "Changed files found but no Odoo modules affected. Starting Odoo normally."
    run_odoo
    exit 0
fi

echo "Detected changes ($$diff_source) in $${#changed_modules[@]} module(s):"
echo ""

ensure_up

# Query database for installed modules
upgrade_modules=()
install_modules=()

for mod in "$${changed_modules[@]}"; do
    state=$$($$COMPOSE exec -T db psql -U odoo -d "$$DB_NAME" -tAc \\
        "SELECT state FROM ir_module_module WHERE name = '$$mod';" 2>/dev/null || echo "")

    if [ "$$state" = "installed" ]; then
        echo "  [upgrade] $$mod"
        upgrade_modules+=("$$mod")
    else
        read -rp "  [new]     $$mod - Install? (y/n) " answer
        if [[ "$$answer" =~ ^[Yy] ]]; then
            install_modules+=("$$mod")
        else
            echo "            Skipped."
        fi
    fi
done

# Build flags
flags=()
if [ $${#upgrade_modules[@]} -gt 0 ]; then
    upgrade_list=$$(IFS=,; echo "$${upgrade_modules[*]}")
    flags+=("-u" "$$upgrade_list")
fi
if [ $${#install_modules[@]} -gt 0 ]; then
    install_list=$$(IFS=,; echo "$${install_modules[*]}")
    flags+=("-i" "$$install_list")
fi

echo ""
if [ $${#flags[@]} -gt 0 ]; then
    flags+=("--stop-after-init")
    echo "Running upgrade: $${flags[*]}"
else
    echo "No modules selected. Starting Odoo normally."
fi

run_odoo "$${flags[@]}"
""")

ODOO_CONF_TEMPLATE = Template("""\
[options]
addons_path = ${addons_path}
data_dir = /opt/odoo
db_host = db
db_port = 5432
db_user = odoo
db_password = odoo
db_name = ${db_name}
admin_passwd = admin
xmlrpc_port = 8069
proxy_mode = False
without_demo = all
smtp_server = mailpit
smtp_port = 1025
email_from = test@example.com
list_db = True
log_level = info
environment_name = Odoo DOCKER
environment_color = black
""")
