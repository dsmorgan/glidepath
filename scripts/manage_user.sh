#!/bin/bash

# User Management Script
# This script provides a convenient wrapper for the Django manage_user command
# It allows administrators to create and manage internal users securely
# Supports: docker-compose, podman-compose, docker, podman, and Python virtualenv

set -e

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Function to display usage
usage() {
    echo "Usage: $0 --username <username> --email <email> --role <admin|user> [--name <name>]"
    echo ""
    echo "Options:"
    echo "  --username <username>  Username for the user (required)"
    echo "  --email <email>        Email address for the user (required)"
    echo "  --role <admin|user>    Role for the user (required)"
    echo "  --name <name>          Full name for the user (optional)"
    echo ""
    echo "Examples:"
    echo "  # Create a new admin user:"
    echo "  $0 --username admin --email admin@example.com --role admin --name \"Admin User\""
    echo ""
    echo "  # Create a regular user:"
    echo "  $0 --username john --email john@example.com --role user --name \"John Doe\""
    echo ""
    echo "  # Update existing user's password and role:"
    echo "  $0 --username john --email john@example.com --role admin"
    echo ""
    exit 1
}

# Function to find container image name
find_image() {
    local tool=$1
    local project_name=$(basename "$PROJECT_DIR" | tr '[:upper:]' '[:lower:]' | tr -d '_-')

    # Try common image name patterns
    local patterns=(
        "${project_name}-web"
        "${project_name}_web"
        "glidepath-web"
        "glidepath_web"
        "web"
    )

    for pattern in "${patterns[@]}"; do
        if $tool images --format "{{.Repository}}" 2>/dev/null | grep -q "^${pattern}$"; then
            echo "$pattern"
            return 0
        fi
    done

    # Try with latest tag
    for pattern in "${patterns[@]}"; do
        if $tool images --format "{{.Repository}}:{{.Tag}}" 2>/dev/null | grep -q "^${pattern}:latest$"; then
            echo "${pattern}:latest"
            return 0
        fi
    done

    return 1
}

# Function to run with direct container command
run_with_container() {
    local tool=$1
    local image=$2

    echo -e "${BLUE}Using $tool with image: $image${NC}"
    echo ""
    cd "$PROJECT_DIR"

    $tool run --rm -it \
        -v "$(pwd):/app:z" \
        -w /app \
        "$image" \
        python manage.py manage_user $ARGS
}

# Parse arguments
ARGS=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --username)
            ARGS="$ARGS --username \"$2\""
            shift 2
            ;;
        --email)
            ARGS="$ARGS --email \"$2\""
            shift 2
            ;;
        --role)
            ARGS="$ARGS --role \"$2\""
            shift 2
            ;;
        --name)
            ARGS="$ARGS --name \"$2\""
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}Error: Unknown option $1${NC}"
            usage
            ;;
    esac
done

cd "$PROJECT_DIR"

# Try container tools in priority order
# 1. Check for docker-compose
if command -v docker-compose &> /dev/null; then
    echo -e "${YELLOW}Running user management command via docker-compose...${NC}"
    echo ""
    eval "docker-compose run --rm web python manage.py manage_user $ARGS"
    exit 0
fi

# 2. Check for podman-compose
if command -v podman-compose &> /dev/null; then
    echo -e "${YELLOW}Running user management command via podman-compose...${NC}"
    echo ""
    eval "podman-compose run --rm web python manage.py manage_user $ARGS"
    exit 0
fi

# 3. Check for docker (direct)
if command -v docker &> /dev/null; then
    IMAGE=$(find_image "docker")
    if [ -n "$IMAGE" ]; then
        run_with_container "docker" "$IMAGE"
        exit 0
    else
        echo -e "${YELLOW}Docker found but no image available. Building image...${NC}"
        if [ -f "Dockerfile" ]; then
            docker build -t glidepath-web .
            run_with_container "docker" "glidepath-web"
            exit 0
        fi
    fi
fi

# 4. Check for podman (direct)
if command -v podman &> /dev/null; then
    IMAGE=$(find_image "podman")
    if [ -n "$IMAGE" ]; then
        run_with_container "podman" "$IMAGE"
        exit 0
    else
        echo -e "${YELLOW}Podman found but no image available. Building image...${NC}"
        if [ -f "Dockerfile" ]; then
            podman build -t glidepath-web .
            run_with_container "podman" "glidepath-web"
            exit 0
        fi
    fi
fi

# 5. Fall back to Python (with warning)
if command -v python3 &> /dev/null || command -v python &> /dev/null; then
    echo -e "${RED}WARNING: No container runtime found (docker/podman).${NC}"
    echo -e "${RED}Falling back to local Python execution.${NC}"
    echo -e "${RED}This is NOT recommended for production use.${NC}"
    echo ""

    PYTHON_CMD=""
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    fi

    echo -e "${YELLOW}Running user management command with local Python...${NC}"
    echo ""
    eval "$PYTHON_CMD manage.py manage_user $ARGS"
    exit 0
fi

# If we get here, nothing worked
echo -e "${RED}ERROR: No suitable runtime found!${NC}"
echo ""
echo "This script requires one of the following:"
echo "  - docker-compose"
echo "  - podman-compose"
echo "  - docker"
echo "  - podman"
echo "  - python3 (not recommended)"
echo ""
echo "Please install a container runtime or Python to continue."
exit 1
