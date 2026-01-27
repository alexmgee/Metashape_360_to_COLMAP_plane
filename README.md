# Metashape to COLMAP Converter

English | 日本語

## Overview / 概要
Convert Agisoft Metashape camera exports (spherical + frame sensors) into COLMAP text format for 3D Gaussian Splatting training.

**Supported sensors:**
- **Spherical (360°)**: Each equirectangular frame generates 6 rectilinear 90° crops (top/front/right/back/left/bottom)
- **Frame (pinhole)**: Images copied as-is with full calibration (focal length, distortion coefficients)
- **Mixed datasets**: Can process both sensor types in one export

Designed for Lichtfeld Studio, Postshot, and other 3DGS trainers that accept COLMAP format.

## Features / 特長
- Mixed sensor support: 360° spherical + drone/DSLR pinhole cameras in one dataset
- Equirectangular → Cubemap, 6 rectilinear 90° crops per frame (top/front/right/back/left/bottom)
- Preserves frame camera calibration (OPENCV/RADIAL distortion models)
- Writes COLMAP cameras.txt, images.txt, points3D.txt
- Optional mask processing (cropped for spherical, copied for frame)
- Optional PLY transform/export (needs Open3D)
- Adjustable FoV and crop size; vertical flip for sampling equirect
- Multi-process parallel cropping
- Utility scripts for undistortion and EXIF cleaning

## Requirements / 必要環境
- Metashape Standard or Pro (https://www.agisoft.com/)
- Python 3.9+
- pip: numpy, pillow, opencv-python
- Optional: open3d (for PLY → points3D)
- Optional: COLMAP (for undistorting OPENCV cameras to PINHOLE)

## Quick Start / クイックスタート

### 1. Prepare Metashape Export
For spherical cameras:
- [Tools] -> [Camera Calibration] -> [Camera type] -> [Spherical]

For mixed datasets (360° + drone/DSLR):
- Metashape automatically detects sensor types
- No special calibration needed

Export:
- [File] -> [Export Cameras...] -> select XML format
- [File] -> [Export Point Cloud...] -> select PLY format

### 2. Convert to COLMAP Format
```bash
# Install dependencies
pip install numpy pillow opencv-python
pip install open3d  # optional, for PLY point cloud

# Run conversion (searches recursively in --images directory)
python metashape_360_to_colmap.py \
  --images /path/to/all_images_root \
  --xml /path/to/metashape_cameras.xml \
  --output /path/to/output_colmap \
  --ply /path/to/pointcloud.ply \
  --masks /path/to/masks_root \
  --crop-size 1920 \
  --fov-deg 90 \
  --num-workers 8

# Quick test with limited images
python metashape_360_to_colmap.py \
  --images ./frames \
  --xml ./cameras.xml \
  --output ./out \
  --max-images 5
```

### 3. Undistort OPENCV Cameras (if needed)
If your dataset includes frame cameras with distortion (OPENCV/RADIAL models):

```bash
# Use COLMAP to convert all cameras to PINHOLE
colmap image_undistorter \
  --image_path output_colmap/images \
  --input_path output_colmap \
  --output_path output_undistorted \
  --output_type COLMAP

# Undistort masks to match
python undistort_masks.py \
  --input output_colmap \
  --output output_undistorted
```

### 4. Train 3D Gaussian Splats
Use the output with Lichtfeld Studio, Postshot, or other 3DGS trainers that accept COLMAP format.

## Command Reference / コマンドリファレンス

### metashape_360_to_colmap.py
Main conversion script. Key options:

- --images (required): Root directory containing all images (searched recursively)
- --xml (required): Metashape XML export (cameras)
- --output (required): Output folder (COLMAP format)
- --ply: Optional PLY to export points3D.txt
- --masks: Optional masks directory (auto-detects if not specified)
- --crop-size: Crop resolution for spherical images (square). Default 1920.
- --fov-deg: Horizontal FoV of rectilinear crops. Default 90.
- --max-images: Limit number of source images for quick tests (default 10000)
- --num-workers: Parallel workers for image cropping (default 4)
- --skip-bottom: Skip bottom view (may contain self-reflections)
- --preserve-structure: Preserve directory structure and use symlinks for frame images

### undistort_masks.py
Undistort masks to match COLMAP's undistorted images.

```bash
python undistort_masks.py \
  --input test_output \
  --output test_output_undistorted
```

- --input: Original COLMAP output (with OPENCV cameras)
- --output: Undistorted COLMAP output (with PINHOLE cameras)

### strip_gps_exif.py
Remove GPS data from images for privacy.

```bash
python strip_gps_exif.py \
  --input /path/to/images \
  --output /path/to/cleaned_images \
  --preserve-other-exif \
  --recursive
```

- --preserve-other-exif: Keep camera settings, remove only GPS
- --recursive: Process subdirectories

## Output Structure / 出力構造

### After metashape_360_to_colmap.py
```
output/
├── images/
│   ├── frame001_top.jpg      (spherical crops)
│   ├── frame001_front.jpg
│   ├── frame001_right.jpg
│   ├── frame001_back.jpg
│   ├── frame001_left.jpg
│   ├── frame001_bottom.jpg
│   ├── drone_001.jpg         (frame images, copied as-is)
│   └── ...
├── masks/                     (if --masks specified)
│   ├── frame001_top.png
│   ├── drone_001.png
│   └── ...
├── cameras.txt                (multiple camera models)
├── images.txt                 (camera poses)
└── points3D.txt              (Metashape point cloud)
```

### After COLMAP image_undistorter
```
output_undistorted/
├── images/                    (all images undistorted to PINHOLE)
├── masks/                     (before running undistort_masks.py - wrong sizes!)
└── sparse/
    └── 0/
        ├── cameras.txt        (all PINHOLE models)
        ├── images.txt
        └── points3D.txt
```

### After undistort_masks.py
```
output_undistorted/
└── masks/                     (masks now match undistorted image sizes)
```

## Important Notes / 重要事項

### ⚠️ COLMAP Binary Files Warning
**Do not run COLMAP reconstruction tools** (feature extraction, matching, triangulation) on Metashape-exported data. This will overwrite the Metashape point cloud with a sparse COLMAP reconstruction and cause 3DGS training failures.

If you accidentally ran COLMAP reconstruction, delete the corrupted binary files:
```bash
rm test_output_undistorted/sparse/0/points3D.bin
rm test_output_undistorted/sparse/0/images.bin
rm test_output_undistorted/database.db
```

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for details.

### Workflow
The correct workflow is:
1. Metashape SfM reconstruction → Export XML + PLY
2. This converter → COLMAP format
3. COLMAP image_undistorter → Remove distortion (optional, only if needed)
4. undistort_masks.py → Resize masks (if using masks)
5. 3DGS training → Lichtfeld Studio / Postshot

### Tested Platforms
- Lichtfeld Studio (dev and master builds)
- Postshot
- Other COLMAP-compatible 3DGS trainers

### Technical Details
- Spherical crops use PINHOLE model with fx=fy=(w/2)/tan(fov/2), cx=cy=w/2
- Frame cameras preserve original calibration (OPENCV/RADIAL with distortion coefficients)
- Component transforms applied when present
- Coordinate system: COLMAP world-to-camera quaternion (w,x,y,z) + translation
- Point cloud from Metashape PLY is transformed and exported to points3D.txt

## Troubleshooting / トラブルシューティング

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for detailed solutions to common issues:
- 3DGS training failures (bright blobs, undefined errors)
- COLMAP binary file corruption
- Mask dimension mismatches
- Mixed sensor dataset handling

## License / ライセンス
MIT
