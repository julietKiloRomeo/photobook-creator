#!/bin/bash
# Generate thumbnails for all photos

SOURCE_FOLDER="$1"
THUMB_DIR=".photobook-temp/thumbnails"
THUMB_WIDTH=400

echo "Generating thumbnails (${THUMB_WIDTH}px wide)..."

# Read file list
while IFS= read -r filepath; do
    # Get relative path from source folder
    rel_path="${filepath#$SOURCE_FOLDER/}"

    # Create output directory structure
    thumb_path="$THUMB_DIR/$rel_path"
    mkdir -p "$(dirname "$thumb_path")"

    # Generate thumbnail (only if doesn't exist or source is newer)
    if [ ! -f "$thumb_path" ] || [ "$filepath" -nt "$thumb_path" ]; then
        convert "$filepath" -resize "${THUMB_WIDTH}x" -quality 85 "$thumb_path" 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "Created: $thumb_path"
        else
            echo "Failed: $filepath"
        fi
    fi
done < .photobook-temp/file_list.txt

echo "Thumbnail generation complete"

