# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

- **Metashape**: Pro 2.1.3 build 18670 (64-bit)
- **OS**: Windows 11
- **GPU**: NVIDIA RTX 3090 Ti
- **RAM**: 128GB
- **CPU**: Intel Core i9-13900K
- **Camera**: DJI Osmo 360
- **Goal**: Photogrammetry models and Gaussian splatting from 360° footage
- **Gaussian Splat Training**: Lichtfeld Studio
  - Dev build: `C:\Users\alexm\LichtFeld-Studio-dev\build`
  - Master build: `C:\Users\alexm\LichtFeld-Studio-master\build`

## Purpose

This tool bridges Metashape's mixed-sensor workflow with Lichtfeld Studio's expected COLMAP input format. The pipeline is:

```
Mixed dataset (360° + pinhole) → Metashape (mixed SfM) → This converter → Lichtfeld Studio (3DGS training)
```

## Project Overview

Single-file Python utility that converts Agisoft Metashape camera exports (spherical + frame sensors) into COLMAP text format.

**Supported sensors:**
- **Spherical (360°)**: Each equirectangular frame generates 6 rectilinear 90° crops (top/front/right/back/left/bottom)
- **Frame (pinhole)**: Images copied as-is with full calibration (focal length, distortion coefficients)
- **Mixed datasets**: Can process both sensor types in one export

## Commands

```bash
# Install dependencies
pip install numpy pillow opencv-python
pip install open3d  # optional, for PLY point cloud conversion

# Run conversion (searches recursively in --images directory)
python metashape_360_to_colmap.py \
  --images /path/to/all_images_root \
  --xml /path/to/metashape_cameras.xml \
  --output /path/to/output_colmap \
  --ply /path/to/pointcloud.ply \
  --masks /path/to/all_masks_root \
  --crop-size 1920 \
  --fov-deg 90 \
  --num-workers 8

# Example folder structure (images stay in original locations):
# /path/to/all_images_root/
#   ├── 360_frames/
#   │   ├── Kearney_frame_00060.jpg
#   │   └── ...
#   ├── drone_video/
#   │   ├── DJI_video_frame_001.jpg
#   │   └── ...
#   └── mavic_photos/
#       ├── DJI_20250915091348_0033_D.JPG
#       └── ...

# Quick test with limited images
python metashape_360_to_colmap.py --images ./frames --xml ./cameras.xml --output ./out --max-images 5
```

## Architecture

### Processing Pipeline

```
Metashape XML + Equirectangular Images + Optional PLY
                    ↓
            parse_metashape_xml()
         Extract sensors, components, camera transforms
                    ↓
            For each camera/frame:
                    ↓
            crop_direction() × 4 directions
         Equirectangular → Rectilinear via cv2.remap
                    ↓
            Compute extrinsics per crop
         Apply direction rotation + component transform
         Convert camera-to-world → world-to-camera
         Rotation matrix → quaternion
                    ↓
            Write COLMAP files
         cameras.txt (PINHOLE model)
         images.txt (quaternion + translation per crop)
         points3D.txt (transformed point cloud)
```

### Key Functions

| Function | Purpose |
|----------|---------|
| `parse_metashape_xml()` | Parses XML, returns sensor calibration dict, component transforms, and camera iterator |
| `crop_direction()` | Uses `cv2.remap` to extract rectilinear crop from equirectangular image at specified yaw |
| `get_direction_rotation_matrix()` | Returns 3×3 yaw rotation for front(0°)/right(-90°)/back(180°)/left(90°) |
| `quaternion_from_matrix()` | Converts 3×3 rotation to (x,y,z,w) quaternion for COLMAP |
| `convert_metashape_to_colmap()` | Main orchestrator: loads images, processes crops, writes output |

### Coordinate Transforms

The critical transformation chain for each cropped image:

1. **Camera transform from XML**: 4×4 camera-to-world matrix (`c2w`)
2. **Component transform**: If present, applied as `component @ camera_transform`
3. **Direction rotation**: `R_c2w_dir = R_c2w @ R_direction` where R_direction rotates for the crop's yaw
4. **Invert for COLMAP**: `R_w2c = R_c2w_dir.T`, `t_w2c = -R_w2c @ t_c2w`
5. **Quaternion**: COLMAP uses (qw, qx, qy, qz) ordering in images.txt

### COLMAP Output Format

- `cameras.txt`: Single PINHOLE camera with `fx = fy = (crop_size/2) / tan(fov/2)`
- `images.txt`: One entry per crop with quaternion (w,x,y,z) + translation + image filename
- `points3D.txt`: Transformed point cloud with RGB colors (requires Open3D)

### Supported Input

- **Sensors**:
  - Spherical (equirectangular) - generates cubemap crops
  - Frame (pinhole) - preserved with full calibration
  - Fisheye - preserved with full calibration
- **Images**: Recursively searched from root directory
  - Formats: jpg, jpeg, png, tiff, tif, webp (case-insensitive)
  - Organized in subdirectories (structure preserved in source, flattened in output)
- **Masks**: Optional, recursively searched, matched by filename stem
  - Spherical masks: Cropped for each direction (6 per frame)
  - Frame masks: Copied as-is
- **Point cloud**: PLY format (optional, requires open3d)

### COLMAP Output for Mixed Datasets

**Multiple camera models:**
- Camera 1: PINHOLE for spherical crops (computed from FOV)
- Camera 2+: OPENCV/RADIAL for each frame sensor (with distortion coefficients)

**Images output:**
- Spherical: `basename_top.jpg`, `basename_front.jpg`, etc.
- Frame: `basename.jpg` (original filename preserved)
