#!/bin/bash

# User Management Script
# This script provides a convenient wrapper for the Django manage_user command
# It allows administrators to create and manage internal users securely

set -e

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
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

# Check if docker-compose is available
if command -v docker-compose &> /dev/null; then
    echo -e "${YELLOW}Running user management command via Docker...${NC}"
    echo ""
    cd "$PROJECT_DIR"
    eval "docker-compose run --rm web python manage.py manage_user $ARGS"
else
    # Fall back to local execution
    echo -e "${YELLOW}Running user management command locally...${NC}"
    echo ""
    cd "$PROJECT_DIR"
    eval "python manage.py manage_user $ARGS"
fi
