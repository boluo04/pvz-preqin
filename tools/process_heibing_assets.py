from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class AlignResult:
    out_size: tuple[int, int]
    baseline_y: int


def _alpha_bbox(img: Image.Image) -> tuple[int, int, int, int] | None:
    """Return bbox (l, t, r, b) of non-transparent pixels, or None."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    alpha = img.getchannel("A")
    bbox = alpha.getbbox()
    return bbox


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _paste_with_offset(
    src: Image.Image, out_size: tuple[int, int], dx: int, dy: int
) -> Image.Image:
    canvas = Image.new("RGBA", out_size, (255, 255, 255, 0))
    canvas.alpha_composite(src, dest=(dx, dy))
    return canvas


def align_frames_to_baseline(
    in_paths: list[Path],
    out_dir: Path,
    *,
    out_size: tuple[int, int] | None = None,
    baseline_y: int | None = None,
) -> AlignResult:
    """
    Make all frames the same canvas size and align their non-transparent bottom
    to a shared baseline_y (pixel coord in output canvas).
    """
    imgs = []
    bboxes = []
    max_w = 0
    max_h = 0
    bottoms = []

    for p in in_paths:
        img = Image.open(p).convert("RGBA")
        bbox = _alpha_bbox(img)
        if bbox is None:
            bbox = (0, 0, 0, 0)
        l, t, r, b = bbox
        imgs.append((p, img))
        bboxes.append(bbox)
        max_w = max(max_w, img.width)
        max_h = max(max_h, img.height)
        bottoms.append(b)

    if out_size is None:
        out_size = (max_w, max_h)

    if baseline_y is None:
        # Choose the maximum bottom among frames so nothing gets clipped.
        # Clamp within output height.
        baseline_y = min(max(bottoms), out_size[1])

    _ensure_dir(out_dir)

    for (p, img), bbox in zip(imgs, bboxes, strict=True):
        l, t, r, b = bbox
        # Align bottom b to baseline_y.
        dy = baseline_y - b
        # Center horizontally by default.
        dx = (out_size[0] - img.width) // 2
        out = _paste_with_offset(img, out_size, dx, dy)
        out.save(out_dir / p.name)

    return AlignResult(out_size=out_size, baseline_y=baseline_y)


def normalize_bullet_to_target(
    src_path: Path,
    out_path: Path,
    *,
    target_size: tuple[int, int],
    max_fill: float,
) -> None:
    """
    Resize bullet so that its alpha bbox fits within target canvas at max_fill.
    Then center it on the target canvas.
    """
    img = Image.open(src_path).convert("RGBA")
    bbox = _alpha_bbox(img)
    if bbox is None:
        out = Image.new("RGBA", target_size, (255, 255, 255, 0))
        _ensure_dir(out_path.parent)
        out.save(out_path)
        return

    l, t, r, b = bbox
    crop = img.crop((l, t, r, b))
    bw, bh = crop.size
    tw, th = target_size

    # Scale so bbox fits within max_fill portion of target.
    # Keep aspect ratio.
    max_w = int(tw * max_fill)
    max_h = int(th * max_fill)
    scale = min(max_w / max(bw, 1), max_h / max(bh, 1))
    new_w = max(1, int(round(bw * scale)))
    new_h = max(1, int(round(bh * scale)))
    resized = crop.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)

    out = Image.new("RGBA", target_size, (255, 255, 255, 0))
    dx = (tw - new_w) // 2
    dy = (th - new_h) // 2
    out.alpha_composite(resized, dest=(dx, dy))
    _ensure_dir(out_path.parent)
    out.save(out_path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stump-dir", type=Path, required=True)
    ap.add_argument("--bullet-dir", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument(
        "--target-fly-size",
        type=str,
        default="56x34",
        help="e.g. 56x34",
    )
    ap.add_argument(
        "--target-explode-size",
        type=str,
        default="52x46",
        help="e.g. 52x46",
    )
    ap.add_argument(
        "--bullet-fill",
        type=float,
        default=0.72,
        help="max bbox fill ratio inside target canvas",
    )
    args = ap.parse_args()

    fwt, fht = args.target_fly_size.lower().split("x")
    target_fly_size = (int(fwt), int(fht))
    ewt, eht = args.target_explode_size.lower().split("x")
    target_explode_size = (int(ewt), int(eht))

    stump_dir: Path = args.stump_dir
    bullet_dir: Path = args.bullet_dir
    out_dir: Path = args.out_dir

    stump_frames = sorted(
        [
            p
            for p in stump_dir.glob("*.png")
            if p.name.lower() != "card.png"
        ],
        key=lambda p: p.name,
    )
    stump_out = out_dir / "stump_frames"
    res = align_frames_to_baseline(stump_frames, stump_out)

    # Process all bullets in bullet_dir (png only).
    # Heuristic: filenames containing "爆炸" or "Explode" are treated as explode frames.
    bullet_out = out_dir / "bullets"
    for p in sorted(bullet_dir.glob("*.png")):
        is_explode = ("爆炸" in p.stem) or ("Explode" in p.stem)
        normalize_bullet_to_target(
            p,
            bullet_out / p.name,
            target_size=target_explode_size if is_explode else target_fly_size,
            max_fill=args.bullet_fill,
        )

    print("stump_frames:", len(stump_frames))
    print("stump_out_size:", res.out_size, "baseline_y:", res.baseline_y)
    print(
        "bullet_fly_size:",
        target_fly_size,
        "explode_size:",
        target_explode_size,
        "fill:",
        args.bullet_fill,
    )


if __name__ == "__main__":
    main()

