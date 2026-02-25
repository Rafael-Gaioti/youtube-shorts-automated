import json
from pathlib import Path

analysis_path = Path("data/analysis/y9hwhoB9XTI_analysis.json")
with open(analysis_path, "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"Video ID: {data['video_id']}")
for i, cut in enumerate(data["cuts"]):
    print(f"Cut {i + 1}:")
    print(f"  Start: {cut['start']}s")
    print(f"  End: {cut['end']}s")
    print(f"  Hook: {cut.get('thumbnail_hook')}")
    print(f"  Title: {cut.get('youtube_title')}")
    print(f"  Headline: {cut.get('on_screen_text')}")
