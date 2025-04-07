#!/bin/sh

BACKUP_ROOT="${BACKUP_ROOT:-/backup}"

# Check if backup directory exists
if [ ! -d "$BACKUP_ROOT" ]; then
    echo "Error: Backup directory $BACKUP_DIR doesn't exists." >&2
    exit 1
fi

# Validate arguments format
if [ $# -eq 0 ] || [ $(( $# % 2 )) -ne 0 ]; then
    echo "Usage: $0 label1 directory1 [label2 directory2 ...]" >&2
    exit 1
fi

# Process label-directory pairs
while [ $# -gt 0 ]; do
    label="$1"
    directory="$2"
    shift 2

    # Validate label format
    case $label in
        -*)
            echo "Error: Label '$label' cannot start with a hyphen" >&2
            exit 1
            ;;
        *[!a-zA-Z0-9_-]*)
            echo "Error: Invalid label '$label' - allowed characters: a-z, A-Z, 0-9, _, -" >&2
            exit 1
            ;;
    esac

    # Validate directory existence
    if [ ! -d "$directory" ]; then
        echo "Error: Directory '$directory' not found" >&2
        exit 1
    fi

    # Create backup with label-based filename
    backup_path="${BACKUP_ROOT}/${label}.tar"
    echo "Backing up '$directory' as '$label'..."
    
    if ! tar -cf "$backup_path" -C "$directory" ./; then
        echo "Error: Failed to create backup for '$directory'" >&2
        exit 1
    fi
done

echo "All backups completed successfully to $BACKUP_ROOT"
exit 0

