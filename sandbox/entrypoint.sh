#!/bin/bash
# octopOS Sandbox Entrypoint
# Handles setup and execution for ephemeral worker containers

set -euo pipefail

# Configuration
WORKSPACE_DIR="${WORKSPACE_DIR:-/workspace}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-300}"
MAX_OUTPUT_SIZE="${MAX_OUTPUT_SIZE:-1048576}"  # 1MB
SECURITY_CONF="${SECURITY_CONF:-/etc/octopos/security.conf}"
LIMITS_CONF="${LIMITS_CONF:-/etc/octopos/limits.conf}"

# Colors for output (if terminal)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    NC=''
fi

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Signal handlers
cleanup() {
    log_info "Cleaning up..."
    # Remove temporary files
    rm -rf /tmp/* 2>/dev/null || true
    log_info "Cleanup complete"
}

trap cleanup EXIT

# Load configuration
load_config() {
    if [ -f "$SECURITY_CONF" ]; then
        log_info "Loading security configuration"
        # shellcheck source=/dev/null
        source "$SECURITY_CONF"
    fi
    
    if [ -f "$LIMITS_CONF" ]; then
        log_info "Loading resource limits"
        # shellcheck source=/dev/null
        source "$LIMITS_CONF"
    fi
}

# Validate environment
validate_environment() {
    log_info "Validating sandbox environment"
    
    # Check if running as expected user
    if [ "$(id -u)" = "0" ]; then
        log_error "Container should not run as root"
        exit 1
    fi
    
    # Check workspace exists and is writable
    if [ ! -d "$WORKSPACE_DIR" ]; then
        log_error "Workspace directory does not exist: $WORKSPACE_DIR"
        exit 1
    fi
    
    if [ ! -w "$WORKSPACE_DIR" ]; then
        log_error "Workspace directory is not writable: $WORKSPACE_DIR"
        exit 1
    fi
    
    # Check resource limits are set
    if [ -z "${MAX_MEMORY_MB:-}" ]; then
        log_warn "MAX_MEMORY_MB not set, using default"
        MAX_MEMORY_MB=512
    fi
    
    if [ -z "${MAX_CPU_CORES:-}" ]; then
        log_warn "MAX_CPU_CORES not set, using default"
        MAX_CPU_CORES=1
    fi
    
    log_info "Environment validation passed"
}

# Setup workspace
setup_workspace() {
    log_info "Setting up workspace"
    
    # Create subdirectories
    mkdir -p "$WORKSPACE_DIR"/{input,output,temp,logs}
    
    # Set permissions
    chmod 755 "$WORKSPACE_DIR"/{input,output,temp,logs}
    
    # Create task metadata file
    cat > "$WORKSPACE_DIR/task_info.json" <<EOF
{
    "container_id": "$(hostname)",
    "started_at": "$(date -Iseconds)",
    "user_id": "$(id -un)",
    "uid": $(id -u),
    "gid": $(id -g),
    "workspace": "$WORKSPACE_DIR",
    "timeout_seconds": $TIMEOUT_SECONDS
}
EOF
    
    log_info "Workspace ready at $WORKSPACE_DIR"
}

# Execute command with timeout and monitoring
execute_command() {
    local cmd="$1"
    local start_time end_time duration
    
    log_info "Executing: $cmd"
    log_info "Timeout: ${TIMEOUT_SECONDS}s"
    
    start_time=$(date +%s)
    
    # Create output log
    local output_log="$WORKSPACE_DIR/logs/execution.log"
    
    # Execute with timeout
    if timeout "$TIMEOUT_SECONDS" bash -c "$cmd" 2>&1 | tee "$output_log"; then
        exit_code=$?
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        
        log_info "Command completed in ${duration}s"
        
        # Write execution result
        cat > "$WORKSPACE_DIR/execution_result.json" <<EOF
{
    "success": true,
    "exit_code": $exit_code,
    "duration_seconds": $duration,
    "completed_at": "$(date -Iseconds)",
    "output_size": $(stat -c%s "$output_log" 2>/dev/null || echo 0)
}
EOF
        
        return 0
    else
        exit_code=$?
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        
        if [ $exit_code -eq 124 ]; then
            log_error "Command timed out after ${TIMEOUT_SECONDS}s"
        else
            log_error "Command failed with exit code $exit_code"
        fi
        
        # Write execution result
        cat > "$WORKSPACE_DIR/execution_result.json" <<EOF
{
    "success": false,
    "exit_code": $exit_code,
    "duration_seconds": $duration,
    "completed_at": "$(date -Iseconds)",
    "error": $([ $exit_code -eq 124 ] && echo '"timeout"' || echo '"execution_failed"')
}
EOF
        
        return $exit_code
    fi
}

# Handle input files if provided
handle_input() {
    if [ -f "$WORKSPACE_DIR/input/task.json" ]; then
        log_info "Task configuration found"
        
        # Extract command from task.json if present
        if command -v jq >/dev/null 2>&1; then
            cmd=$(jq -r '.command // empty' "$WORKSPACE_DIR/input/task.json")
            if [ -n "$cmd" ] && [ "$cmd" != "null" ]; then
                log_info "Command extracted from task configuration"
                TASK_COMMAND="$cmd"
            fi
        fi
    fi
}

# Main execution
main() {
    log_info "octopOS Sandbox Starting"
    log_info "Container ID: $(hostname)"
    log_info "User: $(id -un) ($(id -u):$(id -g))"
    
    # Load configuration
    load_config
    
    # Validate environment
    validate_environment
    
    # Setup workspace
    setup_workspace
    
    # Handle input files
    handle_input
    
    # Execute command or start shell
    if [ $# -eq 0 ]; then
        # No command provided, check for task file
        if [ -n "${TASK_COMMAND:-}" ]; then
            execute_command "$TASK_COMMAND"
        else
            log_info "No command specified, starting interactive shell"
            exec /bin/bash
        fi
    else
        # Execute provided command
        execute_command "$*"
    fi
    
    log_info "Sandbox execution complete"
}

# Run main
main "$@"
