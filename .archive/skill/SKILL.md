---
name: photo-book-organizer
description: Intelligently organizes photos from throughout the year into themes and events for creating annual photo books. Uses AI to cluster photos by time and location, rank quality, and provides an interactive interface for curation. Maintains original files while creating a configuration-based workflow.
---

# Photo Book Organizer

This skill helps you curate photos for annual photo books by automatically detecting events, ranking photo quality, and providing an interactive interface for organization. It keeps all originals intact and uses a configuration file to track your selections.

## When to Use This Skill

- You're preparing photos for an annual family photo book
- You have hundreds of photos from various family members' phones
- You want to organize by themes and events rather than just dates
- You need help identifying the best photos from burst shots and similar images
- You want a visual interface to arrange and order your selections
- You're looking to include both event-based and custom theme pages (e.g., "All Judo Tournaments")

## What This Skill Does

1. **Discovers and Analyzes**: Finds all photos in your source folder and extracts metadata
2. **Clusters Events**: Groups photos by time and location to detect distinct events
3. **Ranks Quality**: Uses AI to evaluate photo quality, composition, and variety
4. **Suggests Themes**: Identifies potential custom themes across the year
5. **Interactive Curation**: Provides a visual interface to organize, order, and refine selections
6. **Generates Config**: Creates a YAML configuration file tracking all selections
7. **Exports Finals**: Provides a script to copy selected photos for upload to photo book services

## How to Use

### Initial Setup

From your project directory:

```bash
cd ~/photos-2024
```

Then run Claude Code and ask:

```
Help me organize photos for my 2024 photo book
```

Or more specifically:

```
I want to create a photo book from photos in ./family-photos-2024
```

### During the Process

The skill will guide you through:
- Naming detected events
- Creating custom themes
- Reviewing AI quality rankings
- Organizing photos in a visual interface

## Instructions

### Phase 1: Check Dependencies and Setup

Before starting, verify required tools are available:

```bash
# Check for required tools
command -v rg >/dev/null 2>&1 || echo "Missing: ripgrep (install via: brew install ripgrep)"
command -v exiftool >/dev/null 2>&1 || echo "Missing: exiftool (install via: brew install exiftool)"
command -v convert >/dev/null 2>&1 || echo "Missing: imagemagick (install via: brew install imagemagick)"
command -v jq >/dev/null 2>&1 || echo "Missing: jq (install via: brew install jq)"
```

If any tools are missing, inform the user and provide installation commands for their platform.

Ask the user for:
1. **Source folder path** (relative path containing all photos)
2. **Year** for the photo book (for naming/organization)

Create working directory structure:

```bash
mkdir -p .photobook-temp/{thumbnails,metadata}
mkdir -p photobook-output
```

### Phase 2: Discover and Extract Metadata

Use ripgrep to find all image files:

```bash
# Find all image files
rg --files -g '*.{jpg,jpeg,png,JPG,JPEG,PNG,heic,HEIC}' [source_folder] > .photobook-temp/file_list.txt

# Count total files
wc -l .photobook-temp/file_list.txt
```

Run the metadata extraction script:

```bash
bash scripts/extract_exif.sh [source_folder]
```

This generates `.photobook-temp/metadata/photos_metadata.json` containing:
- Filepath
- DateTime
- GPS coordinates (if available)
- Camera model
- Image dimensions
- File size

### Phase 3: Cluster Photos into Events

Run the clustering script:

```bash
python3 scripts/cluster_photos.py
```

This analyzes temporal and spatial proximity to create initial event clusters. Output is `.photobook-temp/clusters.json`.

Present clusters to the user:

```markdown
# Detected Events

I found [N] potential events based on time and location clustering:

## Cluster 1: [Date Range]
- **Photos**: 47 photos
- **Date range**: June 15-17, 2024
- **Location**: Copenhagen (if GPS available)
- **Sample photos**: [show 3-4 representative filenames]

What should I call this event? (e.g., "Summer Copenhagen Trip")

## Cluster 2: [Date Range]
...

[Continue for all clusters]
```

Allow user to:
- Name each cluster
- Merge clusters (if they're the same event)
- Split clusters (if mixed events)
- Skip clusters (if not for the book)

### Phase 4: Identify Custom Theme Suggestions

Analyze photo metadata and filenames to suggest custom themes:

```bash
python3 scripts/suggest_themes.py
```

This script looks for:
- Repeated activities (multiple photos with similar timestamps across different dates)
- Keyword patterns in filenames (e.g., "judo", "handball", "birthday")
- Regular intervals (e.g., monthly patterns)

Present suggestions:

```markdown
# Suggested Custom Themes

Based on patterns in your photos, you might want these theme pages:

1. **Judo Tournaments** (15 photos across 4 dates)
2. **Handball Matches** (12 photos across 3 dates)
3. **Monthly Portraits** (12 photos, one from each month)

Would you like to:
- Add any of these themes? (yes/no for each)
- Create your own custom theme? (provide theme name)
```

For each custom theme, help the user tag relevant photos by:
- Showing candidate photos matching patterns
- Allowing keyword search in filenames
- Allowing date range selection

### Phase 5: Generate Thumbnails

Create scaled-down versions for the UI:

```bash
bash scripts/generate_thumbnails.sh [source_folder]
```

This creates 400px wide thumbnails in `.photobook-temp/thumbnails/` preserving directory structure.

### Phase 6: AI Quality Ranking

For each event/theme, use the Claude API to rank photos. Prompt yourself with:

```
I have [N] photos from [event_name]. Please analyze and rank them based on:
- Technical quality (sharpness, exposure, composition)
- Emotional impact (captured moments, expressions)
- Variety (avoid too many similar shots)
- People representation (ensure everyone is included)

Here are the photo filenames and basic metadata:
[provide list with timestamps, filenames]

Please respond ONLY in JSON format with this structure:
{
  "rankings": [
    {
      "filename": "IMG_1234.jpg",
      "score": 8.5,
      "reasoning": "Sharp focus, great composition, genuine smiles",
      "category": "keeper",
      "similar_to": ["IMG_1233.jpg", "IMG_1235.jpg"]
    }
  ],
  "recommended_count": 15,
  "duplicate_groups": [
    ["IMG_1233.jpg", "IMG_1234.jpg", "IMG_1235.jpg"]
  ]
}

Categories: "keeper" (top tier), "consider" (good but similar to others), "skip" (blur/bad exposure)
```

For photos, you can include thumbnail image data if helpful for analysis. Process rankings in batches of 50-100 photos to stay within context limits.

Save rankings to `.photobook-temp/rankings/[event_name].json`

### Phase 7: Create Interactive Organization UI

Create an HTML artifact that:

1. **Loads all photos and rankings**:
   - Read thumbnails using `window.fs.readFile`
   - Load all event/theme configurations
   - Display AI rankings and recommendations

2. **Organizes by theme sections**:
   - One section per event/theme
   - Shows thumbnails in grid layout
   - Displays AI scores and notes
   - Color-codes: keeper (green), consider (yellow), skip (gray)

3. **Enables drag-and-drop**:
   - Drag photos between themes
   - Reorder within themes
   - Remove/add back photos
   - Mark favorites

4. **Persists state**:
   - Use `window.storage` to save current organization
   - Auto-save on changes
   - Allow reset to AI recommendations

5. **Theme management**:
   - Add new custom themes
   - Rename themes
   - Delete themes
   - Search photos to add to themes

6. **Export configuration**:
   - Generate YAML config
   - Show summary stats
   - Preview page layout

Example artifact structure:

```javascript
import { useState, useEffect } from 'react';

export default function PhotoBookOrganizer() {
  const [themes, setThemes] = useState([]);
  const [photos, setPhotos] = useState({});
  const [selectedTheme, setSelectedTheme] = useState(null);
  
  // Load photos and rankings
  useEffect(() => {
    loadPhotoData();
  }, []);
  
  async function loadPhotoData() {
    // Load rankings and metadata
    // Create thumbnail image data
    // Initialize themes from clusters
  }
  
  // Drag and drop handlers
  // Theme management functions
  // Export to YAML function
  
  return (
    <div className="flex h-screen">
      {/* Theme sidebar */}
      {/* Photo grid */}
      {/* Export panel */}
    </div>
  );
}
```

The UI should feel like organizing physical photos on a table - intuitive, visual, and tactile.

### Phase 8: Generate Configuration File

Based on the user's final organization in the UI, create `photobook-output/photobook_[YEAR].yaml`:

```yaml
metadata:
  year: 2024
  created: 2024-01-21
  total_photos: 342
  selected_photos: 87
  source_folder: ./family-photos-2024

themes:
  summer_copenhagen_trip:
    type: event
    name: "Summer Copenhagen Trip"
    date_range: "2024-06-15 to 2024-06-17"
    location: "Copenhagen, Denmark"
    photos:
      - path: "2024-06/IMG_1234.jpg"
        order: 1
        notes: "Opening shot - harbor view"
      - path: "2024-06/IMG_1267.jpg"
        order: 2
        notes: "Kids at Tivoli"
    page_count: 4
    
  judo_tournaments:
    type: custom
    name: "Judo Tournaments 2024"
    photos:
      - path: "2024-03/IMG_5678.jpg"
        order: 1
        date: "2024-03-15"
        notes: "First tournament"
      - path: "2024-09/IMG_9012.jpg"
        order: 2
        date: "2024-09-20"
        notes: "Regional championship"
    page_count: 2

  # ... more themes
```

### Phase 9: Export Selected Photos

Provide the user with the export script:

```bash
bash scripts/export_photos.sh photobook-output/photobook_2024.yaml
```

This script:
1. Reads the YAML configuration
2. Creates organized export directory: `photobook-output/finals/`
3. Copies selected photos maintaining theme structure
4. Renames for easy ordering: `01_summer_copenhagen_01.jpg`
5. Generates a manifest file
6. Preserves originals (never modifies source)

Show summary:

```markdown
# Export Complete! 📸

## Summary
- **Total photos selected**: 87
- **Themes**: 8
- **Exported to**: `photobook-output/finals/`

## Next Steps
1. Review exported photos in `photobook-output/finals/`
2. Upload to your photo book service
3. Use the theme folders to organize pages

## File Structure
```
photobook-output/finals/
├── 01_summer_copenhagen_trip/
│   ├── 01.jpg
│   ├── 02.jpg
│   └── ...
├── 02_judo_tournaments/
│   ├── 01.jpg
│   └── 02.jpg
└── manifest.txt
```

Your original photos remain untouched in `[source_folder]`.
Configuration saved in `photobook-output/photobook_2024.yaml`.
```


## Example Workflow

### Example 1: Creating a 2024 Family Photo Book

**User**: "Help me organize photos for my 2024 photo book. Photos are in ./family-photos-2024"

**Process**:

1. **Discovery**: Finds 342 photos across the year
2. **Clustering**: Detects 12 events based on time gaps
3. **Event Naming**:
   - User names: "Summer Copenhagen Trip", "Christmas with Grandparents", "Anna's Birthday", etc.
4. **Custom Themes**:
   - Suggests: "Judo Tournaments" (15 photos), "First Day of School" (8 photos)
   - User adds: "Monthly Portraits"
5. **AI Ranking**: Ranks each event's photos, recommends top selections
6. **Organization**: User arranges 87 selected photos across 8 themes in UI
7. **Export**: Generates config and exports organized photos

### Example 2: Mixed Events and Themes

**User**: "I want separate pages for all handball matches and judo tournaments, plus the regular events"

**Process**:

1. Detects time-based events normally
2. Searches filenames for "handball" and "judo"
3. Creates custom themes with photos from across the year
4. User reviews and adjusts selections
5. Final book has both event pages and activity theme pages

## Pro Tips

1. **Start with Good Source Organization**: Even rough date-based folders help clustering
2. **GPS Data is Gold**: If available, enables location-based clustering
3. **Filename Keywords**: Name files descriptively (e.g., "judo_tournament_march.jpg")
4. **Review AI Rankings**: The AI is good but not perfect - final call is yours
5. **Less is More**: Aim for 80-120 photos for a typical annual book
6. **Theme Variety**: Mix event pages with custom theme pages for visual interest
7. **Save Configurations**: Keep YAML files for future reference or re-exports

## Common Tasks

### Quick Start
```
I have photos in ./photos-2024 that I want to organize for a photo book
```

### Add Custom Theme Mid-Process
```
Add a new theme called "Weekend Hikes" and help me find all hiking photos
```

### Re-rank Event
```
The AI rankings for "Summer Vacation" don't match my preferences. 
Show me all photos again so I can manually select.
```

### Export Subset
```
Only export the first 5 themes, I'll do the rest later
```

### Restart Organization
```
Reset the UI to AI recommendations, I want to start over
```

## Related Use Cases

- Creating quarterly family updates
- Organizing photos for digital frames
- Preparing photo gifts (calendars, albums)
- Year-end family newsletters with photos
- Archiving important moments from the year
