import json
import os
import sys


def create_visualization(
    transcript_path, analysis_path=None, output_html="caption_flow.html"
):
    print(f"Visualizing: {transcript_path}")

    with open(transcript_path, "r", encoding="utf-8") as f:
        t_data = json.load(f)

    segments = t_data["segments"]

    # If analysis provided, filter by cuts? For now just show full line.
    # Actually, let's focus on the segments in the cut if possible.

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body { background: #1e1e1e; color: #fff; fontFamily: sans-serif; padding: 20px; }
            .timeline { position: relative; width: 100%; height: 200px; border: 1px solid #444; overflow-x: auto; white-space: nowrap; margin-bottom: 50px;}
            .segment { position: absolute; height: 100%; border-left: 1px solid #555; opacity: 0.5; }
            .word { position: absolute; height: 60%; top: 20%; background: #444; border-radius: 4px; padding: 2px 5px; font-size: 12px; display: flex; align-items: center; justify-content: center; overflow: hidden; color: #000; font-weight: bold;}
            .speaker-1 { background-color: #ffd700; } /* Yellow */
            .speaker-2 { background-color: #00ffff; } /* Cyan */
            .ruler { position: absolute; bottom: 0; width: 100%; height: 20px; background: #333; }
            .tick { position: absolute; bottom: 0; height: 10px; border-left: 1px solid #777; font-size: 10px; padding-left: 2px; }
        </style>
    </head>
    <body>
        <h1>Caption Flow Visualizer</h1>
        <p>Yellow: Speaker 1 (Default) | Cyan: Speaker 2</p>
    """

    # Check bounds
    min_time = min(s["start"] for s in segments)
    max_time = max(s["end"] for s in segments)

    # Filter for the cut 60-90s if it exists (since that's what we tested)
    target_start = 60
    target_end = 90

    filtered_segs = [
        s for s in segments if s["end"] > target_start and s["start"] < target_end
    ]
    if not filtered_segs:
        filtered_segs = segments  # Fallback to all
        target_start = min_time
        target_end = max_time

    html += f"<h2>Range: {target_start}s - {target_end}s</h2>"
    html += '<div class="timeline">'

    scale = 100  # Pixels per second

    for seg in filtered_segs:
        # Draw words
        words = seg.get("words", [])
        speaker_id = seg.get("speaker", 1)

        for w in words:
            start = w["start"]
            end = w["end"]

            if end < target_start or start > target_end:
                continue

            left = (start - target_start) * scale
            width = (end - start) * scale
            text = w["word"]

            # Identify individual word speaker if available, else segment speaker
            w_spk = w.get("speaker", speaker_id)
            color_class = "speaker-1"
            if str(w_spk) in ["2", "SPEAKER_01", "SPEAKER_02"]:
                color_class = "speaker-2"

            html += f'<div class="word {color_class}" style="left: {left}px; width: {width}px;" title="{text} ({start}-{end})">{text}</div>'

    # Ruler
    for t in range(int(target_start), int(target_end) + 1):
        left = (t - target_start) * scale
        html += f'<div class="tick" style="left: {left}px;">{t}s</div>'

    html += "</div></body></html>"

    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated: {output_html}")
    return output_html


if __name__ == "__main__":
    create_visualization("data/transcripts/_-u91Wejc8A_transcript.json")
