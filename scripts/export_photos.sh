#!/bin/bash
# Export selected photos based on YAML configuration

CONFIG_FILE="$1"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Config file not found: $CONFIG_FILE"
    exit 1
fi

OUTPUT_DIR="photobook-output/finals"
mkdir -p "$OUTPUT_DIR"

echo "Exporting photos from configuration: $CONFIG_FILE"

# Parse YAML and copy files
# This is a simplified version - you'll need a YAML parser for production
# For now, we'll create a Python script to handle this

python3 - <<EOF
import yaml
import os
import shutil
from pathlib import Path

with open('$CONFIG_FILE', 'r') as f:
    config = yaml.safe_load(f)

source_folder = config['metadata']['source_folder']
output_dir = '$OUTPUT_DIR'

manifest_lines = []
total_copied = 0

for theme_id, theme_data in config['themes'].items():
    theme_name = theme_data['name']
    theme_dir = os.path.join(output_dir, f"{len(manifest_lines)+1:02d}_{theme_id}")
    os.makedirs(theme_dir, exist_ok=True)

    print(f"\nProcessing theme: {theme_name}")

    for i, photo_data in enumerate(theme_data['photos'], 1):
        src_path = os.path.join(source_folder, photo_data['path'])
        ext = Path(src_path).suffix
        dst_filename = f"{i:02d}{ext}"
        dst_path = os.path.join(theme_dir, dst_filename)

        if os.path.exists(src_path):
            shutil.copy2(src_path, dst_path)
            manifest_lines.append(f"{theme_name}/{dst_filename} <- {photo_data['path']}")
            total_copied += 1
            print(f"  Copied: {dst_filename}")
        else:
            print(f"  WARNING: Source not found: {src_path}")

# Write manifest
manifest_path = os.path.join(output_dir, 'manifest.txt')
with open(manifest_path, 'w') as f:
    f.write('\n'.join(manifest_lines))

print(f"\n✓ Export complete!")
print(f"  Total photos copied: {total_copied}")
print(f"  Output directory: {output_dir}")
print(f"  Manifest: {manifest_path}")
EOF
