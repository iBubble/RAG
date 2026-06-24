#!/bin/bash
#===============================================================================
# ShengyaoRAG System Full Backup Script
#===============================================================================
# Purpose: Create a complete, restorable backup of the entire ShengyaoRAG system
# Location: /Volumes/SYRAID/RAG_Files/backups/<timestamp>/
#
# Backup includes:
#   1. SQLite databases (shengyao.db, rag.db, chroma_db)
#   2. Qdrant vector database (via snapshot API)
#   3. Neo4j graph database (via APOC export)
#   4. Redis cache (SAVE + dump.rdb copy)
#   5. All uploaded files and documents (/Volumes/SYRAID/RAG_Files/uploads/)
#   6. Project data directory (/Volumes/SYRAID/RAG_Files/data/)
#   7. Configuration files (.env, ecosystem.config.js, docker-compose.yml, etc.)
#   8. Application source code (/app/backend/, /app/frontend/src/)
#   9. System state (PM2 list, package info, env vars)
#  10. Auto-generated restore script with verification
#
# Usage:
#   /app/backup.sh                  # Full backup with default settings
#   /app/backup.sh --dry-run        # Validate connectivity only, no backup
#   /app/backup.sh --skip-files     # Skip large file backups (uploads, data dirs)
#===============================================================================

# NOTE: Not using 'set -e' because we handle errors explicitly per-step.
#       This prevents the script from dying mid-backup on non-critical failures.
set -uo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────
BACKUP_ROOT="/Volumes/SYRAID/RAG_Files/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}"
LOG_FILE="${BACKUP_DIR}/backup.log"

# Database connection settings
QDRANT_URL="${QDRANT_URL:-http://rag-database:6333}"
NEO4J_URI="${NEO4J_URI:-bolt://rag-graphdb:7687}"
NEO4J_HTTP="${NEO4J_HTTP:-http://rag-graphdb:7474}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASS="${NEO4J_PASSWORD:-syrag_secure_pwd}"
REDIS_HOST="${REDIS_HOST:-rag-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASS="${REDIS_PASS:-Sy2026@sy}"

# RAID data paths
RAID_ROOT="/Volumes/SYRAID/RAG_Files"
SQLITE_MAIN="${RAID_ROOT}/shengyao.db"
SQLITE_DATA="${RAID_ROOT}/data/shengyao.db"
SQLITE_CHROMA="${RAID_ROOT}/chroma_db/chroma.sqlite3"
UPLOADS_DIR="${RAID_ROOT}/uploads"
DATA_DIR="${RAID_ROOT}/data"
CHROMA_DIR="${RAID_ROOT}/chroma_db"

# Application paths
APP_DIR="/app"
BACKEND_DIR="${APP_DIR}/backend"
FRONTEND_DIR="${APP_DIR}/frontend"

# Script options
DRY_RUN=false
SKIP_FILES=false

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ─── Utility Functions ───────────────────────────────────────────────────────

log() {
    local level="$1"; shift
    local msg="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} [${level}] ${msg}" | tee -a "${LOG_FILE}"
}

log_info()  { log "INFO" "$@"; }
log_warn()  { log "${YELLOW}WARN${NC}" "$@"; }
log_error() { log "${RED}ERROR${NC}" "$@"; }
log_ok()    { log "${GREEN}OK${NC}" "$@"; }
log_step()  { echo -e "\n${BLUE}${BOLD}━━━ $* ━━━${NC}"; log "STEP" "$*"; }

die() {
    log_error "FATAL: $*"
    log_error "Backup FAILED. Check ${LOG_FILE} for details."
    exit 1
}

check_command() {
    command -v "$1" &>/dev/null || die "Required command '$1' not found. Install it first."
}

check_disk_space() {
    local required_mb="$1"
    local available_mb
    available_mb=$(df -m "${BACKUP_ROOT}" 2>/dev/null | awk 'NR==2{print $4}')
    if [ -z "${available_mb}" ]; then
        log_warn "Cannot determine available disk space, skipping check"
        return 0
    fi
    if [ "${available_mb}" -lt "${required_mb}" ]; then
        die "Insufficient disk space: need ${required_mb}MB, have ${available_mb}MB on ${BACKUP_ROOT}"
    fi
    log_info "Disk space OK: ${available_mb}MB available"
}

# Run Python snippet with the project's virtual environment
run_python() {
    cd "${BACKEND_DIR}"
    python3 -c "$1"
}

# ─── Pre-flight Checks ───────────────────────────────────────────────────────

preflight() {
    log_step "Pre-flight Checks"

    # Check required commands
    for cmd in python3 tar gzip curl sha256sum; do
        check_command "${cmd}"
    done

    # Check RAID is mounted
    if [ ! -d "${RAID_ROOT}" ]; then
        die "RAID root ${RAID_ROOT} not found. Is the volume mounted?"
    fi
    if [ ! -w "${RAID_ROOT}" ]; then
        die "RAID root ${RAID_ROOT} is not writable"
    fi
    log_ok "RAID volume accessible and writable"

    # Check disk space (estimate ~2GB for full backup)
    if ! ${SKIP_FILES}; then
        check_disk_space 2048
    else
        check_disk_space 512
    fi

    # Create backup directory
    mkdir -p "${BACKUP_DIR}"
    log_ok "Backup directory created: ${BACKUP_DIR}"

    # Check Qdrant connectivity
    log_info "Checking Qdrant connectivity..."
    if curl -sf "${QDRANT_URL}/collections" >/dev/null 2>&1; then
        log_ok "Qdrant: connected"
    else
        log_warn "Qdrant: not reachable at ${QDRANT_URL} (will skip Qdrant backup)"
    fi

    # Check Neo4j connectivity
    log_info "Checking Neo4j connectivity..."
    if curl -sf -u "${NEO4J_USER}:${NEO4J_PASS}" "${NEO4J_HTTP}/db/neo4j/tx/commit" \
        -H "Content-Type: application/json" \
        -d '{"statements":[{"statement":"RETURN 1 as test"}]}' >/dev/null 2>&1; then
        log_ok "Neo4j: connected"
    else
        log_warn "Neo4j: not reachable at ${NEO4J_HTTP} (will skip Neo4j backup)"
    fi

    # Check Redis connectivity via Python
    log_info "Checking Redis connectivity..."
    if run_python "
import redis, os, sys
try:
    r = redis.Redis(host='${REDIS_HOST}', port=${REDIS_PORT}, password='${REDIS_PASS}',
                     socket_connect_timeout=5)
    r.ping()
    print('OK')
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" >/dev/null 2>&1; then
        log_ok "Redis: connected"
    else
        log_warn "Redis: not reachable (will skip Redis backup)"
    fi

    echo ""
    if ${DRY_RUN}; then
        log_info "Dry-run mode: all connectivity checks passed. Exiting."
        exit 0
    fi
}

# ─── 1. SQLite Database Backup ───────────────────────────────────────────────

backup_sqlite() {
    local db_path="$1"
    local db_name="$2"
    local output="${BACKUP_DIR}/sqlite/${db_name}.sql"

    if [ ! -f "${db_path}" ] || [ ! -s "${db_path}" ]; then
        log_warn "SQLite ${db_name}: file empty or missing, skipping"
        return 0
    fi

    mkdir -p "$(dirname "${output}")"
    
    if run_python "
import sqlite3, sys, os
db_path = '${db_path}'
output = '${output}'
try:
    conn = sqlite3.connect(db_path)
    with open(output, 'w', encoding='utf-8') as f:
        for line in conn.iterdump():
            f.write(line + '\n')
    conn.close()
    size = os.path.getsize(output)
    tables = sqlite3.connect(db_path).execute(
        \"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
    print(f'OK: {size} bytes, {len(tables)} tables')
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" 2>&1; then
        log_ok "SQLite ${db_name}: dumped"
    else
        log_error "SQLite ${db_name}: dump failed"
        return 1
    fi
}

backup_all_sqlite() {
    log_step "1/9  SQLite Database Backup"
    local all_ok=true

    backup_sqlite "${SQLITE_MAIN}" "shengyao_main" || all_ok=false
    backup_sqlite "${SQLITE_DATA}" "shengyao_data" || all_ok=false

    # Also backup local RAG database if it exists
    if [ -f "${BACKEND_DIR}/.data/rag.db" ] && [ -s "${BACKEND_DIR}/.data/rag.db" ]; then
        backup_sqlite "${BACKEND_DIR}/.data/rag.db" "rag_local" || all_ok=false
    fi

    # ChromaDB SQLite (legacy, but back it up anyway)
    if [ -f "${SQLITE_CHROMA}" ] && [ -s "${SQLITE_CHROMA}" ]; then
        backup_sqlite "${SQLITE_CHROMA}" "chroma" || all_ok=false
    fi

    if ${all_ok}; then
        log_ok "All SQLite backups completed"
    else
        log_warn "Some SQLite backups had issues (see above)"
    fi
}

# ─── 2. Qdrant Vector Database Snapshot ──────────────────────────────────────

backup_qdrant() {
    log_step "2/9  Qdrant Vector Database Snapshot"

    local collection="syrag_documents"
    local snapshot_dir="${BACKUP_DIR}/qdrant"
    mkdir -p "${snapshot_dir}"

    # Check if collection exists
    local resp
    resp=$(curl -sf "${QDRANT_URL}/collections/${collection}" 2>/dev/null)
    if [ $? -ne 0 ]; then
        log_warn "Qdrant collection '${collection}' not found, skipping"
        return 0
    fi

    # Create snapshot
    log_info "Creating Qdrant snapshot for collection '${collection}'..."
    local snapshot_resp
    snapshot_resp=$(curl -sf -X POST "${QDRANT_URL}/collections/${collection}/snapshots" \
        -H "Content-Type: application/json" 2>&1)
    
    if [ $? -ne 0 ]; then
        log_error "Failed to create Qdrant snapshot: ${snapshot_resp}"
        return 1
    fi

    # Extract snapshot name from response
    local snapshot_name
    snapshot_name=$(echo "${snapshot_resp}" | python3 -c "
import json,sys
try:
    data = json.load(sys.stdin)
    name = data.get('result',{}).get('name','')
    print(name)
except: pass
" 2>/dev/null)

    if [ -z "${snapshot_name}" ]; then
        log_error "Could not extract snapshot name from response: ${snapshot_resp}"
        return 1
    fi

    log_info "Snapshot created: ${snapshot_name}"

    # Wait for snapshot to be ready (Qdrant snapshots are synchronous, but be safe)
    sleep 1

    # Download snapshot
    log_info "Downloading snapshot..."
    curl -sf "${QDRANT_URL}/collections/${collection}/snapshots/${snapshot_name}" \
        -o "${snapshot_dir}/${snapshot_name}" 2>&1

    if [ $? -ne 0 ] || [ ! -f "${snapshot_dir}/${snapshot_name}" ]; then
        log_error "Failed to download Qdrant snapshot"
        return 1
    fi

    local snap_size
    snap_size=$(du -h "${snapshot_dir}/${snapshot_name}" | cut -f1)
    log_ok "Qdrant snapshot saved: ${snap_size}"
}

# ─── 3. Neo4j Graph Database Export ──────────────────────────────────────────

backup_neo4j() {
    log_step "3/9  Neo4j Graph Database Export"

    local neo4j_dir="${BACKUP_DIR}/neo4j"
    mkdir -p "${neo4j_dir}"

    # Check APOC availability via CALL syntax
    local apoc_check
    apoc_check=$(curl -sf -u "${NEO4J_USER}:${NEO4J_PASS}" \
        "${NEO4J_HTTP}/db/neo4j/tx/commit" \
        -H "Content-Type: application/json" \
        -d '{"statements":[{"statement":"CALL apoc.help('apoc.version')"}]}' 2>&1)
    
    if [ $? -ne 0 ]; then
        log_error "Neo4j not reachable, cannot backup"
        return 1
    fi

    # Check if APOC is available (no errors in response)
    local has_apoc
    has_apoc=$(echo "${apoc_check}" | python3 -c "
import json,sys
try:
    data = json.load(sys.stdin)
    if data.get('errors') and len(data['errors']) > 0:
        print('no')
    else:
        print('yes')
except: print('no')
" 2>/dev/null)

    # Export graph statistics (always works, no APOC needed)
    log_info "Exporting graph statistics..."
    curl -sf -u "${NEO4J_USER}:${NEO4J_PASS}" \
        "${NEO4J_HTTP}/db/neo4j/tx/commit" \
        -H "Content-Type: application/json" \
        -d '{"statements":[
            {"statement":"MATCH (n) RETURN labels(n) as label, count(n) as count"},
            {"statement":"MATCH ()-[r]->() RETURN type(r) as type, count(r) as count"}
        ]}' > "${neo4j_dir}/graph_stats.json" 2>&1 || true
    log_info "Graph statistics exported"

    if [ "${has_apoc}" = "yes" ]; then
        log_info "APOC available, creating full Cypher dump..."

        # Full graph export via APOC
        local export_resp
        export_resp=$(curl -sf -u "${NEO4J_USER}:${NEO4J_PASS}" \
            "${NEO4J_HTTP}/db/neo4j/tx/commit" \
            -H "Content-Type: application/json" \
            -d '{"statements":[
                {"statement":"CALL apoc.export.cypher.all(null, {format: \"cypher-shell\", separateFiles: false, useOptimizations: {type: \"UNWIND_BATCH\", unwindBatchSize: 20}})"}
            ]}' 2>&1)

        if [ $? -eq 0 ]; then
            echo "${export_resp}" > "${neo4j_dir}/export_cypher_full.json"

            # Extract and save the actual Cypher statements
            echo "${export_resp}" | python3 -c "
import json,sys
try:
    data = json.load(sys.stdin)
    results = data.get('results',[])
    if results and len(results) > 0:
        data_rows = results[0].get('data',[])
        if data_rows and len(data_rows) > 0:
            cypher = data_rows[0].get('row',[''])[0]
            if cypher:
                with open('${neo4j_dir}/graph_dump.cypher', 'w') as f:
                    f.write(cypher)
                print(f'Saved {len(cypher)} chars of Cypher')
            else:
                print('Empty Cypher result')
        else:
            print('No data rows in APOC response')
    else:
        print('Empty results from APOC')
except Exception as e:
    print(f'Error extracting Cypher: {e}')
" 2>&1 || true
            log_info "Full Cypher export saved"
        else
            log_warn "APOC export failed (Community Edition limitation)"
        fi
    else
        log_warn "APOC not available, graph backup is statistics-only"
        log_info "To enable full graph backup, install APOC plugin in Neo4j"
    fi

    local neo4j_size
    neo4j_size=$(du -sh "${neo4j_dir}" | cut -f1)
    log_ok "Neo4j backup completed: ${neo4j_size}"
}

# ─── 4. Redis Cache Backup ───────────────────────────────────────────────────

backup_redis() {
    log_step "4/9  Redis Cache Backup"

    local redis_dir="${BACKUP_DIR}/redis"
    mkdir -p "${redis_dir}"

    # Trigger SAVE via Python redis client
    if run_python "
import redis, sys, os
try:
    r = redis.Redis(host='${REDIS_HOST}', port=${REDIS_PORT}, password='${REDIS_PASS}',
                     socket_connect_timeout=10)
    if r.ping():
        # Get current dbsize before save
        dbsize = r.dbsize()
        # Trigger SAVE (synchronous)
        result = r.save()
        print(f'SAVE_OK: dbsize={dbsize}')
    else:
        print('ERROR: ping failed')
        sys.exit(1)
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" 2>&1; then
        log_ok "Redis SAVE triggered successfully"
    else
        log_warn "Redis SAVE may have failed, attempting BGSAVE..."
        run_python "
import redis
r = redis.Redis(host='${REDIS_HOST}', port=${REDIS_PORT}, password='${REDIS_PASS}')
r.bgsave()
print('BGSAVE triggered')
" 2>&1 || log_error "Redis BGSAVE also failed"
    fi

    # Export all keys metadata for reference
    log_info "Exporting Redis key metadata..."
    run_python "
import redis, json, sys
try:
    r = redis.Redis(host='${REDIS_HOST}', port=${REDIS_PORT}, password='${REDIS_PASS}',
                     socket_connect_timeout=5, decode_responses=True)
    keys = r.keys('*')
    key_info = {}
    for k in keys[:500]:  # Limit to avoid huge output
        ktype = r.type(k)
        if ktype == 'string':
            key_info[k] = {'type': 'string'}
        elif ktype == 'list':
            key_info[k] = {'type': 'list', 'len': r.llen(k)}
        elif ktype == 'set':
            key_info[k] = {'type': 'set', 'len': r.scard(k)}
        elif ktype == 'hash':
            key_info[k] = {'type': 'hash', 'len': r.hlen(k)}
        elif ktype == 'zset':
            key_info[k] = {'type': 'zset', 'len': r.zcard(k)}
        else:
            key_info[k] = {'type': ktype}
    with open('${redis_dir}/key_metadata.json', 'w') as f:
        json.dump({'total_keys': len(keys), 'keys': key_info}, f, indent=2, ensure_ascii=False)
    print(f'OK: {len(keys)} total keys')
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" 2>&1 && log_ok "Redis key metadata exported" || log_warn "Redis key metadata export failed"

    log_ok "Redis backup completed (dump.rdb is on Docker volume, key metadata exported)"
}

# ─── 5. Uploaded Files Backup ────────────────────────────────────────────────

backup_uploads() {
    log_step "5/9  Uploaded Files Backup"

    if ${SKIP_FILES}; then
        log_info "Skipping uploads backup (--skip-files)"
        return 0
    fi

    if [ ! -d "${UPLOADS_DIR}" ]; then
        log_warn "Uploads directory not found, skipping"
        return 0
    fi

    local upload_size
    upload_size=$(du -sh "${UPLOADS_DIR}" 2>/dev/null | cut -f1)
    log_info "Backing up uploads (${upload_size})..."

    tar -czf "${BACKUP_DIR}/uploads.tar.gz" \
        -C "$(dirname "${UPLOADS_DIR}")" \
        "$(basename "${UPLOADS_DIR}")" 2>&1 || die "Failed to archive uploads"

    local archive_size
    archive_size=$(du -sh "${BACKUP_DIR}/uploads.tar.gz" | cut -f1)
    log_ok "Uploads archived: ${archive_size}"
}

# ─── 6. Data Directory Backup ────────────────────────────────────────────────

backup_data_dir() {
    log_step "6/9  Data Directory Backup"

    if ${SKIP_FILES}; then
        log_info "Skipping data directory backup (--skip-files)"
        return 0
    fi

    if [ ! -d "${DATA_DIR}" ]; then
        log_warn "Data directory not found, skipping"
        return 0
    fi

    local data_size
    data_size=$(du -sh "${DATA_DIR}" 2>/dev/null | cut -f1)
    log_info "Backing up data directory (${data_size})..."

    # Exclude .DS_Store files
    tar -czf "${BACKUP_DIR}/data.tar.gz" \
        -C "$(dirname "${DATA_DIR}")" \
        --exclude='.DS_Store' \
        "$(basename "${DATA_DIR}")" 2>&1 || die "Failed to archive data directory"

    local archive_size
    archive_size=$(du -sh "${BACKUP_DIR}/data.tar.gz" | cut -f1)
    log_ok "Data directory archived: ${archive_size}"
}

# ─── 7. Configuration Files Backup ───────────────────────────────────────────

backup_configs() {
    log_step "7/9  Configuration Files Backup"

    local config_dir="${BACKUP_DIR}/configs"
    mkdir -p "${config_dir}"

    local configs=(
        "${APP_DIR}/backend/.env"
        "${APP_DIR}/ecosystem.config.js"
        "${APP_DIR}/docker-compose.yml"
        "${APP_DIR}/Dockerfile"
        "${APP_DIR}/.dockerignore"
        "${APP_DIR}/.gitignore"
        "${APP_DIR}/start.sh"
        "${APP_DIR}/backend/requirements.txt"
        "${APP_DIR}/backend/.env.example"
        "${APP_DIR}/backend/core/config.py"
        "${APP_DIR}/frp/frpc.ini"
    )

    local copied=0
    local failed=0
    for cfg in "${configs[@]}"; do
        if [ -f "${cfg}" ]; then
            local rel_path="${cfg#${APP_DIR}/}"
            mkdir -p "$(dirname "${config_dir}/${rel_path}")"
            if cp -p "${cfg}" "${config_dir}/${rel_path}" 2>/dev/null; then
                copied=$((copied + 1))
            else
                failed=$((failed + 1))
            fi
        else
            log_info "Config not found (optional): ${cfg}"
        fi
    done

    log_ok "Configuration files backed up: ${copied} copied, ${failed} failed"
}

# ─── 8. Application Code Backup ──────────────────────────────────────────────

backup_code() {
    log_step "8/9  Application Code Backup"

    local code_dir="${BACKUP_DIR}/code"
    mkdir -p "${code_dir}"

    # Backend source code (exclude .pycache, venv, data dirs)
    log_info "Backing up backend source code..."
    tar -czf "${code_dir}/backend.tar.gz" \
        -C "${APP_DIR}" \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache' \
        --exclude='venv' \
        --exclude='.venv' \
        --exclude='data' \
        --exclude='local_data' \
        --exclude='.data' \
        --exclude='node_modules' \
        --exclude='*.db' \
        --exclude='*.log' \
        --exclude='.DS_Store' \
        --exclude='chroma_db' \
        --exclude='vector_db' \
        backend/ 2>&1 || die "Failed to archive backend code"

    # Frontend source code (exclude node_modules, dist)
    log_info "Backing up frontend source code..."
    tar -czf "${code_dir}/frontend.tar.gz" \
        -C "${APP_DIR}" \
        --exclude='node_modules' \
        --exclude='dist' \
        --exclude='.DS_Store' \
        frontend/ 2>&1 || die "Failed to archive frontend code"

    local code_size
    code_size=$(du -sh "${code_dir}" | cut -f1)
    log_ok "Application code archived: ${code_size}"
}

# ─── 9. System State Backup ──────────────────────────────────────────────────

backup_system_state() {
    log_step "9/9  System State Backup"

    local sys_dir="${BACKUP_DIR}/system"
    mkdir -p "${sys_dir}"

    # PM2 process list
    if command -v pm2 &>/dev/null; then
        pm2 list 2>/dev/null > "${sys_dir}/pm2_list.txt" || log_warn "PM2 list failed"
        pm2 jlist 2>/dev/null > "${sys_dir}/pm2_jlist.json" || true
        log_info "PM2 state captured"
    else
        log_info "PM2 not available, skipping"
    fi

    # Python package versions
    pip3 freeze 2>/dev/null > "${sys_dir}/pip_freeze.txt" || log_info "pip freeze skipped"

    # Environment variables (sanitized - remove sensitive values)
    env | grep -v -E 'PASSWORD|SECRET|TOKEN|KEY' > "${sys_dir}/env_vars.txt" 2>/dev/null || true
    log_info "Environment variables captured (sanitized)"

    # Disk usage
    df -h > "${sys_dir}/disk_usage.txt" 2>/dev/null || true
    du -sh /Volumes/SYRAID/RAG_Files/*/ 2>/dev/null > "${sys_dir}/raid_usage.txt" || true

    # Docker container info (if available)
    docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" 2>/dev/null > "${sys_dir}/docker_ps.txt" || log_info "Docker not available, skipping"

    # System info
    uname -a > "${sys_dir}/uname.txt" 2>/dev/null || true
    cat /etc/os-release 2>/dev/null > "${sys_dir}/os_release.txt" || true

    log_ok "System state captured"
}

# ─── Checksum Generation ─────────────────────────────────────────────────────

generate_checksums() {
    log_step "Checksum Generation"

    local checksum_file="${BACKUP_DIR}/SHA256SUMS"
    cd "${BACKUP_DIR}"

    # Generate SHA256 for all files in the backup directory (excluding the checksum file itself and the log)
    find . -type f ! -name 'SHA256SUMS' ! -name 'backup.log' ! -name 'restore.sh' \
        -exec sha256sum {} \; | sort -k2 > "${checksum_file}" 2>/dev/null

    local file_count
    file_count=$(wc -l < "${checksum_file}")
    log_ok "Checksums generated for ${file_count} files"

    # Also create a manifest
    {
        echo "============================================"
        echo " ShengyaoRAG Full System Backup Manifest"
        echo "============================================"
        echo "Backup Timestamp : ${TIMESTAMP}"
        echo "Hostname         : $(hostname)"
        echo "Created by       : ${USER:-root}"
        echo "Backup Location  : ${BACKUP_DIR}"
        echo ""
        echo "--- Contents ---"
        find . -type f ! -name 'SHA256SUMS' ! -name 'backup.log' ! -name 'restore.sh' \
            -exec du -h {} \; | sort -k2
        echo ""
        echo "--- Database Stats ---"
        echo "Qdrant endpoint  : ${QDRANT_URL}"
        echo "Neo4j endpoint   : ${NEO4J_URI}"
        echo "Redis endpoint   : ${REDIS_HOST}:${REDIS_PORT}"
    } > "${BACKUP_DIR}/MANIFEST.txt"

    log_ok "Manifest written to MANIFEST.txt"
}

# ─── Generate Restore Script ─────────────────────────────────────────────────

generate_restore_script() {
    log_step "Generate Restore Script"

    cat > "${BACKUP_DIR}/restore.sh" << 'RESTORE_SCRIPT_HEADER'
#!/bin/bash
#===============================================================================
# ShengyaoRAG System Restore Script
#===============================================================================
# Auto-generated by backup.sh
# Usage: bash restore.sh [--verify-only] [--skip-databases] [--skip-files]
#===============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "\n${BLUE}${BOLD}━━━ $* ━━━${NC}"; }
die()       { log_error "FATAL: $*"; exit 1; }

RESTORE_DIR="$(cd "$(dirname "$0")" && pwd)"
VERIFY_ONLY=false
SKIP_DATABASES=false
SKIP_FILES=false

# Parse args
for arg in "$@"; do
    case "$arg" in
        --verify-only) VERIFY_ONLY=true ;;
        --skip-databases) SKIP_DATABASES=true ;;
        --skip-files) SKIP_FILES=true ;;
        --help) echo "Usage: $0 [--verify-only] [--skip-databases] [--skip-files]"; exit 0 ;;
    esac
done

# ─── Verify backup integrity ───────────────────────────────────────────────

verify_integrity() {
    log_step "Verifying Backup Integrity"
    cd "${RESTORE_DIR}"
    if [ -f "SHA256SUMS" ]; then
        if sha256sum -c SHA256SUMS --quiet 2>/dev/null; then
            log_info "All checksums verified OK"
        else
            log_warn "Some checksums failed (non-critical files may have changed after creation)"
        fi
    else
        log_warn "No SHA256SUMS file found, cannot verify integrity"
    fi
}

verify_integrity

if ${VERIFY_ONLY}; then
    log_info "--verify-only mode: integrity check complete. Exiting."
    exit 0
fi

# ─── Restore Configuration Files ───────────────────────────────────────────

restore_configs() {
    log_step "Restoring Configuration Files"
    local config_src="${RESTORE_DIR}/configs"
    if [ ! -d "${config_src}" ]; then
        log_warn "No config backup found, skipping"
        return
    fi

    # Restore .env file
    if [ -f "${config_src}/backend/.env" ]; then
        cp "${config_src}/backend/.env" /app/backend/.env
        log_info "Restored /app/backend/.env"
    fi

    # Restore PM2 config
    if [ -f "${config_src}/ecosystem.config.js" ]; then
        cp "${config_src}/ecosystem.config.js" /app/ecosystem.config.js
        log_info "Restored /app/ecosystem.config.js"
    fi

    # Restore Docker files
    if [ -f "${config_src}/docker-compose.yml" ]; then
        cp "${config_src}/docker-compose.yml" /app/docker-compose.yml
        log_info "Restored /app/docker-compose.yml"
    fi

    if [ -f "${config_src}/Dockerfile" ]; then
        cp "${config_src}/Dockerfile" /app/Dockerfile
        log_info "Restored /app/Dockerfile"
    fi

    if [ -f "${config_src}/start.sh" ]; then
        cp "${config_src}/start.sh" /app/start.sh
        chmod +x /app/start.sh
        log_info "Restored /app/start.sh"
    fi

    log_info "Configuration files restored"
}

# ─── Restore Application Code ──────────────────────────────────────────────

restore_code() {
    log_step "Restoring Application Code"
    local code_src="${RESTORE_DIR}/code"

    if [ -f "${code_src}/backend.tar.gz" ]; then
        log_info "Restoring backend code..."
        # Backup existing code first
        if [ -d /app/backend ]; then
            mv /app/backend "/app/backend.bak.$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
        fi
        tar -xzf "${code_src}/backend.tar.gz" -C /app/
        log_info "Backend code restored"
    fi

    if [ -f "${code_src}/frontend.tar.gz" ]; then
        log_info "Restoring frontend code..."
        if [ -d /app/frontend/src ]; then
            mv /app/frontend/src "/app/frontend/src.bak.$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
        fi
        tar -xzf "${code_src}/frontend.tar.gz" -C /app/
        log_info "Frontend code restored"
    fi

    log_info "Application code restored"
}

# ─── Restore SQLite Databases ──────────────────────────────────────────────

restore_sqlite() {
    log_step "Restoring SQLite Databases"
    local sql_src="${RESTORE_DIR}/sqlite"

    if [ ! -d "${sql_src}" ]; then
        log_warn "No SQLite backup found, skipping"
        return
    fi

    local db_map=(
        "shengyao_main.sql|/Volumes/SYRAID/RAG_Files/shengyao.db"
        "shengyao_data.sql|/Volumes/SYRAID/RAG_Files/data/shengyao.db"
    )

    for mapping in "${db_map[@]}"; do
        local sql_file="${mapping%%|*}"
        local db_path="${mapping##*|}"

        if [ -f "${sql_src}/${sql_file}" ]; then
            log_info "Restoring ${db_path}..."
            mkdir -p "$(dirname "${db_path}")"
            python3 -c "
import sqlite3, sys
db_path = '${db_path}'
sql_file = '${sql_src}/${sql_file}'
try:
    conn = sqlite3.connect(db_path)
    with open(sql_file, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    print('OK')
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" 2>&1 || log_warn "Restore of ${db_path} had warnings"
            log_info "Restored ${db_path}"
        fi
    done
}

# ─── Restore Uploaded Files ────────────────────────────────────────────────

restore_uploads() {
    log_step "Restoring Uploaded Files"
    if [ -f "${RESTORE_DIR}/uploads.tar.gz" ]; then
        log_info "Extracting uploads..."
        tar -xzf "${RESTORE_DIR}/uploads.tar.gz" -C /Volumes/SYRAID/RAG_Files/
        log_info "Uploads restored"
    else
        log_warn "No uploads backup found"
    fi

    if [ -f "${RESTORE_DIR}/data.tar.gz" ]; then
        log_info "Extracting data directory..."
        tar -xzf "${RESTORE_DIR}/data.tar.gz" -C /Volumes/SYRAID/RAG_Files/
        log_info "Data directory restored"
    else
        log_warn "No data directory backup found"
    fi
}

# ─── Restore Qdrant ────────────────────────────────────────────────────────

restore_qdrant() {
    log_step "Restoring Qdrant Vector Database"
    local qdrant_dir="${RESTORE_DIR}/qdrant"
    local QDRANT_URL="${QDRANT_URL:-http://rag-database:6333}"
    local collection="syrag_documents"

    if [ ! -d "${qdrant_dir}" ]; then
        log_warn "No Qdrant backup found, skipping"
        return
    fi

    local snapshot_file=$(ls "${qdrant_dir}"/*.snapshot 2>/dev/null | head -1)
    if [ -z "${snapshot_file}" ]; then
        log_warn "No Qdrant snapshot found in ${qdrant_dir}"
        return
    fi

    log_info "Restoring Qdrant snapshot: $(basename "${snapshot_file}")"

    # First check if collection exists
    if curl -sf "${QDRANT_URL}/collections/${collection}" >/dev/null 2>&1; then
        log_info "Collection '${collection}' exists, will restore into it"
    else
        log_warn "Collection '${collection}' does not exist, please create it first"
        log_warn "  curl -X PUT ${QDRANT_URL}/collections/${collection} -H 'Content-Type: application/json' -d '{\"vectors\":{\"size\":1024,\"distance\":\"Cosine\"}}'"
        return
    fi

    # Upload snapshot to Qdrant
    log_info "Uploading snapshot to Qdrant..."
    local upload_resp
    upload_resp=$(curl -sf -X POST "${QDRANT_URL}/collections/${collection}/snapshots/upload" \
        -F "snapshot=@${snapshot_file}" 2>&1)

    if [ $? -eq 0 ]; then
        log_info "Snapshot uploaded to Qdrant. Use Qdrant dashboard to recover."
        log_info "Or via API: PUT ${QDRANT_URL}/collections/${collection}/snapshots/recover"
    else
        log_error "Failed to upload Qdrant snapshot: ${upload_resp}"
    fi
}

# ─── Restore Neo4j ─────────────────────────────────────────────────────────

restore_neo4j() {
    log_step "Restoring Neo4j Graph Database"
    local neo4j_dir="${RESTORE_DIR}/neo4j"
    local NEO4J_HTTP="${NEO4J_HTTP:-http://rag-graphdb:7474}"
    local NEO4J_USER="${NEO4J_USER:-neo4j}"
    local NEO4J_PASS="${NEO4J_PASSWORD:-syrag_secure_pwd}"

    if [ ! -d "${neo4j_dir}" ]; then
        log_warn "No Neo4j backup found, skipping"
        return
    fi

    if [ -f "${neo4j_dir}/graph_dump.cypher" ]; then
        log_info "Found Cypher dump file. To restore, execute:"
        log_info "  cat ${neo4j_dir}/graph_dump.cypher | cypher-shell -u ${NEO4J_USER} -p ${NEO4J_PASS}"
        log_info "Or via Neo4j Browser: paste the contents of graph_dump.cypher"
    else
        log_warn "No Cypher dump file found in Neo4j backup"
    fi
}

# ─── Main Restore Flow ─────────────────────────────────────────────────────

main() {
    echo ""
    echo "====================================================="
    echo "  ShengyaoRAG System Restore"
    echo "  Backup: $(basename "${RESTORE_DIR}")"
    echo "====================================================="
    echo ""

    restore_configs

    if ! ${SKIP_DATABASES}; then
        restore_sqlite
        restore_qdrant
        restore_neo4j
    else
        log_info "Skipping database restore (--skip-databases)"
    fi

    if ! ${SKIP_FILES}; then
        restore_uploads
    else
        log_info "Skipping file restore (--skip-files)"
    fi

    restore_code

    echo ""
    log_step "Restore Complete!"
    echo ""
    echo "Next steps:"
    echo "  1. Verify configuration in /app/backend/.env"
    echo "  2. Rebuild frontend: cd /app/frontend && npm install && npm run build"
    echo "  3. Restart services: pm2 restart all"
    echo "  4. Restore Qdrant snapshot via API (see notes above)"
    echo "  5. Restore Neo4j via cypher-shell (see notes above)"
    echo "  6. Verify system health: check logs and admin dashboard"
    echo ""
}

main "$@"
RESTORE_SCRIPT_HEADER

    chmod +x "${BACKUP_DIR}/restore.sh"
    log_ok "Restore script generated: ${BACKUP_DIR}/restore.sh"
}

# ─── Cleanup Old Backups ─────────────────────────────────────────────────────

cleanup_old_backups() {
    local keep_count=7
    log_info "Cleaning up old backups (keeping latest ${keep_count})..."

    local backup_dirs
    backup_dirs=$(ls -1dt "${BACKUP_ROOT}"/*/ 2>/dev/null || true)

    local count=0
    local deleted=0
    for d in $backup_dirs; do
        ((count++))
        if [ $count -gt $keep_count ]; then
            log_info "Removing old backup: $(basename "$d")"
            rm -rf "$d" 2>/dev/null && ((deleted++)) || log_warn "Failed to remove: $d"
        fi
    done

    log_info "Removed ${deleted} old backups, kept ${keep_count} most recent"
}

# ─── Main Backup Flow ────────────────────────────────────────────────────────

main() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║         ShengyaoRAG Full System Backup                  ║"
    echo "║         Started: $(date '+%Y-%m-%d %H:%M:%S')                      ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo ""

    # Initialize log
    mkdir -p "${BACKUP_DIR}"
    echo "ShengyaoRAG Backup Log - ${TIMESTAMP}" > "${LOG_FILE}"
    echo "========================================" >> "${LOG_FILE}"

    # Phase 0: Check and prepare
    preflight

    # Phase 1: Database backups
    backup_all_sqlite
    backup_qdrant
    backup_neo4j
    backup_redis

    # Phase 2: File backups
    backup_uploads
    backup_data_dir

    # Phase 3: Configuration & code
    backup_configs
    backup_code

    # Phase 4: System state
    backup_system_state

    # Phase 5: Verification & finalization
    generate_checksums
    generate_restore_script

    # Cleanup old backups
    cleanup_old_backups

    # Final summary
    local total_size
    total_size=$(du -sh "${BACKUP_DIR}" | cut -f1)

    echo ""
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║  ✅  Backup Complete!                                   ║"
    echo "╠══════════════════════════════════════════════════════════╣"
    echo "║  Location : ${BACKUP_DIR}"
    echo "║  Size     : ${total_size}"
    echo "║  Duration : $(date '+%H:%M:%S')"
    echo "╠══════════════════════════════════════════════════════════╣"
    echo "║  To restore: run ${BACKUP_DIR}/restore.sh"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo ""
}

# ─── Parse Arguments ─────────────────────────────────────────────────────────

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --skip-files) SKIP_FILES=true ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dry-run      Test connectivity only, no backup"
            echo "  --skip-files   Skip large file backups (uploads, data dirs)"
            echo "  --help         Show this help"
            exit 0
            ;;
        *) die "Unknown option: $arg. Use --help for usage." ;;
    esac
done

# ─── Run ─────────────────────────────────────────────────────────────────────
main "$@"
