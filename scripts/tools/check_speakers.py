import json
from pathlib import Path

transcripts_dir = Path("data/transcripts")
results = []

for t_path in sorted(transcripts_dir.glob("*_transcript.json")):
    try:
        t = json.load(open(t_path, "r", encoding="utf-8"))
        segs = t.get("segments", [])
        speakers = set(s.get("speaker") for s in segs if s.get("speaker") is not None)
        overlaps = sum(1 for s in segs if s.get("overlap"))
        spk_count = t.get("diarization_speakers_count", len(speakers))
        # Encontrar onde speakers trocam (transições)
        transitions = 0
        prev = None
        for s in segs:
            sp = s.get("speaker")
            if prev is not None and sp != prev:
                transitions += 1
            prev = sp
        results.append(
            {
                "file": t_path.stem,
                "speakers": sorted(speakers),
                "spk_count": spk_count,
                "transitions": transitions,
                "overlaps": overlaps,
                "total_segs": len(segs),
            }
        )
    except Exception as e:
        print(f"Erro em {t_path.name}: {e}")

# Ordenar por numero de transições (maior dialogo primeiro)
results.sort(key=lambda x: x["transitions"], reverse=True)

print(f"{'Arquivo':<35} {'Speakers':>8} {'Transições':>11} {'Overlaps':>9}")
print("-" * 70)
for r in results:
    print(
        f"{r['file']:<35} {str(r['speakers']):>8} {r['transitions']:>11} {r['overlaps']:>9}/{r['total_segs']}"
    )
