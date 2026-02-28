
#!/bin/bash
# Extract EXIF metadata from all photos

SOURCE_FOLDER="$1"
OUTPUT_FILE=".photobook-temp/metadata/photos_metadata.json"

echo "Extracting metadata from photos in $SOURCE_FOLDER..."

# Use exiftool to extract metadata as JSON
exiftool -json -r \
  -FileName -Directory -FileSize \
  -CreateDate -DateTimeOriginal -ModifyDate \
  -GPSLatitude -GPSLongitude \
  -ImageWidth -ImageHeight \
  -Make -Model \
  "$SOURCE_FOLDER" > "$OUTPUT_FILE"

# Count photos processed
PHOTO_COUNT=$(jq '. | length' "$OUTPUT_FILE")
echo "Processed $PHOTO_COUNT photos"
echo "Metadata saved to $OUTPUT_FILE"


