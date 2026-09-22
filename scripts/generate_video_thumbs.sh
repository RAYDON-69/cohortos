#!/usr/bin/env bash
# Generate Plyr previewThumbnails VTT + sprite from a video (requires ffmpeg).
# Usage: ./scripts/generate_video_thumbs.sh input.mp4 out_dir
set -euo pipefail
IN="${1:?input video}"
OUT="${2:-./thumbs}"
mkdir -p "$OUT"
# one frame every 5s → sprite row
ffmpeg -y -i "$IN" -vf "fps=1/5,scale=160:-1" "$OUT/thumb-%04d.jpg"
# Build simple VTT (paths relative to VTT)
{
  echo "WEBVTT"
  echo ""
  i=0
  t=0
  for f in "$OUT"/thumb-*.jpg; do
    i=$((i+1))
    start=$(printf "%02d:%02d:%02d.000" $((t/3600)) $(((t%3600)/60)) $((t%60)))
    t=$((t+5))
    end=$(printf "%02d:%02d:%02d.000" $((t/3600)) $(((t%3600)/60)) $((t%60)))
    echo "$i"
    echo "$start --> $end"
    echo "$(basename "$f")"
    echo ""
  done
} > "$OUT/thumbs.vtt"
echo "Wrote $OUT/thumbs.vtt — pass as Plyr previewThumbnails.src"
