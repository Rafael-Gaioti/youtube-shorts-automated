import json

t = json.load(
    open("data/transcripts/y9hwhoB9XTI_transcript.json", "r", encoding="utf-8")
)
segs = t["segments"]
print("GPU speakers count:", t.get("diarization_speakers_count"))
spks = set(s.get("speaker") for s in segs)
print("Speaker IDs unicos:", spks)
overlaps = sum(1 for s in segs if s.get("overlap"))
print("Segmentos com overlap:", overlaps, "/", len(segs))
print()
for s in segs[:12]:
    ov = "[OVERLAP]" if s.get("overlap") else ""
    print(
        f"[{s['start']:.1f}-{s['end']:.1f}] S{s.get('speaker', '?')} {ov} | {s['text'][:55]}"
    )
