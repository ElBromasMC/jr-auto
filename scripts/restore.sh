#!/bin/sh

BACKUP_ROOT="${BACKUP_ROOT:-/backup}"

# Validate arguments format
if [ $# -eq 0 ] || [ $(( $# % 2 )) -ne 0 ]; then
    echo "Usage: $0 label1 directory1 [label2 directory2 ...]" >&2
    exit 1
fi

# Process label-directory pairs
while [ $# -gt 0 ]; do
    label="$1"
    restore_dir="$2"
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

    backup_file="${BACKUP_ROOT}/${label}.tar"

    # Check backup exists
    if [ ! -f "$backup_file" ]; then
        echo "Error: Backup file '$backup_file' not found" >&2
        exit 1
    fi

    # Verify target directory exists
    if [ ! -d "$restore_dir" ]; then
        echo "Error: Restore directory '$restore_dir' does not exist" >&2
        exit 1
    fi

    # Check directory is empty
    if [ -n "$(ls -A "$restore_dir" 2>/dev/null)" ]; then
        echo "Error: Restore directory '$restore_dir' is not empty" >&2
        exit 1
    fi

    # Extract backup contents
    echo "Restoring '$label' to '$restore_dir'..."
    if ! tar -xf "$backup_file" -C "$restore_dir"; then
        echo "Error: Failed to restore '$label' to '$restore_dir'" >&2
        exit 1
    fi
done

echo "All restorations completed successfully"
exit 0

