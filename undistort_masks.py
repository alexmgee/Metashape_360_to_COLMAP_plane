#!/usr/bin/env python3
"""
Undistort masks for OPENCV cameras to match the undistorted images from COLMAP.

Usage:
    python undistort_masks.py --input test_output --output test_output_undistorted
"""

import argparse
from pathlib import Path
import numpy as np
import cv2
from PIL import Image


def parse_cameras_txt(cameras_txt_path: Path) -> dict:
    """Parse cameras.txt to get camera models and parameters."""
    cameras = {}
    with open(cameras_txt_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or not line:
                continue
            parts = line.split()
            cam_id = int(parts[0])
            model = parts[1]
            width = int(parts[2])
            height = int(parts[3])
            params = [float(p) for p in parts[4:]]
            cameras[cam_id] = {
                'model': model,
                'width': width,
                'height': height,
                'params': params
            }
    return cameras


def parse_images_txt(images_txt_path: Path) -> dict:
    """Parse images.txt to get image-to-camera mapping."""
    image_to_camera = {}
    with open(images_txt_path, 'r') as f:
        lines = f.readlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('#') or not line:
                i += 1
                continue
            # Image line: IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME
            parts = line.split()
            if len(parts) >= 10:
                image_name = parts[9]
                camera_id = int(parts[8])
                image_to_camera[image_name] = camera_id
                i += 2  # Skip the points line
            else:
                i += 1
    return image_to_camera


def undistort_mask_opencv(mask_img: np.ndarray, camera_params_src: dict, camera_params_dst: dict) -> np.ndarray:
    """Undistort a mask using OpenCV camera parameters."""
    # Source camera (OPENCV with distortion)
    fx_src = camera_params_src['params'][0]
    fy_src = camera_params_src['params'][1]
    cx_src = camera_params_src['params'][2]
    cy_src = camera_params_src['params'][3]
    k1 = camera_params_src['params'][4]
    k2 = camera_params_src['params'][5]
    p1 = camera_params_src['params'][6]
    p2 = camera_params_src['params'][7]

    K_src = np.array([
        [fx_src, 0, cx_src],
        [0, fy_src, cy_src],
        [0, 0, 1]
    ])

    dist_coeffs = np.array([k1, k2, p1, p2])

    # Destination camera (PINHOLE, no distortion)
    w_dst = camera_params_dst['width']
    h_dst = camera_params_dst['height']
    fx_dst = camera_params_dst['params'][0]
    fy_dst = camera_params_dst['params'][1]
    cx_dst = camera_params_dst['params'][2]
    cy_dst = camera_params_dst['params'][3]

    K_dst = np.array([
        [fx_dst, 0, cx_dst],
        [0, fy_dst, cy_dst],
        [0, 0, 1]
    ])

    # Get optimal new camera matrix and undistort
    # Use getOptimalNewCameraMatrix to match COLMAP's undistortion behavior
    map1, map2 = cv2.initUndistortRectifyMap(
        K_src, dist_coeffs, None, K_dst,
        (w_dst, h_dst), cv2.CV_32FC1
    )

    # Remap with nearest-neighbor to preserve mask edges
    undistorted = cv2.remap(
        mask_img, map1, map2,
        interpolation=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0
    )

    return undistorted


def main():
    parser = argparse.ArgumentParser(
        description="Undistort masks for OPENCV cameras to match COLMAP undistorted images",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--input', type=Path, required=True, help="Input directory (original test_output)")
    parser.add_argument('--output', type=Path, required=True, help="Output directory (test_output_undistorted)")

    args = parser.parse_args()

    input_masks_dir = args.input / "masks"
    output_masks_dir = args.output / "masks"
    output_masks_dir.mkdir(parents=True, exist_ok=True)

    # Parse cameras from both original and undistorted
    cameras_src = parse_cameras_txt(args.input / "cameras.txt")
    cameras_dst = parse_cameras_txt(args.output / "sparse" / "cameras.txt")

    # Parse images to get camera mapping
    image_to_camera_src = parse_images_txt(args.input / "images.txt")
    image_to_camera_dst = parse_images_txt(args.output / "sparse" / "images.txt")

    print(f"Found {len(cameras_src)} source cameras")
    print(f"Found {len(cameras_dst)} destination cameras")

    # Find all mask files
    mask_files = list(input_masks_dir.rglob("*.png"))
    print(f"Found {len(mask_files)} mask files")

    processed = 0
    skipped = 0

    for mask_path in mask_files:
        mask_name = mask_path.stem + ".jpg"  # Corresponding image name

        # Check if this mask corresponds to an OPENCV camera
        if mask_name not in image_to_camera_src:
            # Try with .png extension
            mask_name = mask_path.stem + ".png"

        if mask_name not in image_to_camera_src:
            print(f"  Warning: Could not find camera for mask {mask_path.name}")
            skipped += 1
            continue

        camera_id_src = image_to_camera_src[mask_name]
        camera_src = cameras_src[camera_id_src]

        # Only undistort masks for OPENCV cameras
        if camera_src['model'] != 'OPENCV':
            # Copy PINHOLE masks as-is (cubemap masks)
            output_mask_path = output_masks_dir / mask_path.name
            output_mask_path.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(mask_path, output_mask_path)
            processed += 1
            continue

        # Get corresponding destination camera
        if mask_name not in image_to_camera_dst:
            print(f"  Warning: Could not find destination camera for {mask_name}")
            skipped += 1
            continue

        camera_id_dst = image_to_camera_dst[mask_name]
        camera_dst = cameras_dst[camera_id_dst]

        # Load and undistort mask
        mask_img = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask_img is None:
            print(f"  Error: Failed to load mask {mask_path}")
            skipped += 1
            continue

        # Undistort
        undistorted_mask = undistort_mask_opencv(mask_img, camera_src, camera_dst)

        # Save undistorted mask
        output_mask_path = output_masks_dir / mask_path.name
        output_mask_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_mask_path), undistorted_mask)

        processed += 1
        if processed % 50 == 0:
            print(f"  Processed {processed}/{len(mask_files)} masks...")

    print(f"\nMask undistortion complete:")
    print(f"  Processed: {processed}")
    print(f"  Skipped: {skipped}")
    print(f"  Output: {output_masks_dir}")


if __name__ == "__main__":
    main()
