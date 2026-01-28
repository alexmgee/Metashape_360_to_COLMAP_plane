# Troubleshooting Guide

## 3D Gaussian Splatting Training Failures

### Symptom: Bright Blobs or Undefined Errors in Lichtfeld Studio / Postshot

If your 3DGS training immediately produces bright blobs or crashes with undefined errors despite having:
- Correct camera models (all PINHOLE after undistortion)
- Valid camera poses
- Proper directory structure
- Correctly sized images and masks

**Root Cause:** Corrupted or incomplete point cloud initialization due to COLMAP binary files.

### Understanding COLMAP File Formats

COLMAP stores sparse reconstruction data in two formats:
- **Text files** (`.txt`): Human-readable, used by converter scripts
- **Binary files** (`.bin`): Optimized format, preferred by 3DGS trainers

**Critical:** 3DGS software (Lichtfeld Studio, Postshot) preferentially reads binary files if present, even if text files are correct.

### The Problem: COLMAP Overwrites Metashape Point Cloud

Running COLMAP reconstruction tools (feature extraction, matching, triangulation) on Metashape-exported data will:

1. Create `database.db` with feature tracks
2. Overwrite `points3D.bin` with sparse COLMAP reconstruction
3. Replace the dense Metashape point cloud (150k+ points) with sparse COLMAP output (few thousand points)
4. Result in poor Gaussian initialization and training failure

**Example from real data:**
- Original Metashape cloud: 157,952 points (covering all 339 images)
- After COLMAP triangulation: 3,935 points (covering only 59/339 images)
- Training result: Bright blobs or immediate failure

### Solution: Delete Problematic Binary Files

The correct workflow avoids creating `points3D.bin` and `images.bin` entirely. After running `COLMAP image_undistorter` (which creates binary files), delete these specific files:

```bash
# Navigate to your sparse reconstruction directory
cd test_output_undistorted/sparse/0/

# Delete problematic binary files
rm points3D.bin
rm images.bin

# These binary files can remain (they're safe):
# - cameras.bin
# - frames.bin
# - rigs.bin

# Keep these text files (they contain the correct Metashape data):
# - cameras.txt
# - images.txt
# - points3D.txt
```

PowerShell:
```powershell
Remove-Item 'test_output_undistorted\sparse\0\points3D.bin' -Force
Remove-Item 'test_output_undistorted\sparse\0\images.bin' -Force
Remove-Item 'test_output_undistorted\database.db' -Force
```

After deletion, 3DGS trainers will read the correct text files with the full Metashape point cloud.

### Verification Steps

1. **Check point cloud size:**
```bash
# Count points in text file (should be 100k+)
grep -v "^#" test_output_undistorted/sparse/0/points3D.txt | wc -l
```

2. **Verify no binary files exist:**
```bash
ls test_output_undistorted/sparse/0/*.bin
# Should only show: cameras.bin, frames.bin, rigs.bin
# Should NOT show: points3D.bin, images.bin
```

3. **Check image coverage:**
```python
# Verify all images are listed in images.txt
with open('test_output_undistorted/sparse/0/images.txt') as f:
    images = [l for l in f if not l.startswith('#') and l.strip() and not l.startswith(' ')]
print(f"Total camera poses: {len(images)}")
```

### Prevention: Metashape Workflow Best Practices

**DO:**
- Export cameras.xml and point cloud from Metashape
- Run `metashape_360_to_colmap.py` to convert to COLMAP format
- Run COLMAP's `image_undistorter` to convert OPENCV → PINHOLE (if needed)
- Run `undistort_masks.py` to resize masks (if using masks)
- Train 3DGS directly from the undistorted output

**DO NOT:**
- Run `colmap feature_extractor` on Metashape exports
- Run `colmap exhaustive_matcher` on Metashape exports
- Run `colmap point_triangulator` on Metashape exports
- Run any COLMAP reconstruction commands that write to `database.db`

**Why:** Metashape has already done the SfM reconstruction. The COLMAP format is just an export format for compatibility with 3DGS trainers. Running COLMAP reconstruction again throws away Metashape's work.

### Mixed Sensor Datasets

For datasets combining 360° spherical and pinhole (drone/DSLR) images:

**Expected point visibility:**
- Spherical crops: Variable coverage (some directions may have few points)
- Pinhole images: High coverage (especially if they were primary alignment sources in Metashape)

This is normal. Metashape aligns all cameras in a unified coordinate system even if individual crops have limited direct observations. The point cloud is what matters for 3DGS initialization, not the 2D observation tracks.

### Common Questions

**Q: Do I need 2D observation tracks in images.txt?**
A: No. 3DGS trainers only need camera poses + point cloud + images. The "mean observations per image: 0" warning can be ignored for Metashape exports.

**Q: How do I know if my point cloud is sufficient?**
A: A good Metashape point cloud should have:
- 100k+ points for outdoor scenes
- Points visible from multiple camera positions
- Coverage throughout the scene volume (not just surfaces)
- RGB colors assigned to each point

**Q: Can I use COLMAP to add more points to my Metashape reconstruction?**
A: Not recommended. COLMAP's sparse reconstruction is designed for different workflows. Metashape's dense point cloud is already optimal for 3DGS initialization.

**Q: My training still fails after deleting binary files. What else could be wrong?**
A: Check:
- Image paths in images.txt match actual file locations
- All camera IDs in images.txt exist in cameras.txt
- Image dimensions match camera models
- Masks (if used) match undistorted image dimensions
- GPU memory is sufficient for your dataset size

## COLMAP Undistortion Issues

### Symptom: Undistorted images don't match mask dimensions

**Problem:** COLMAP's `image_undistorter` may change image dimensions slightly when converting OPENCV → PINHOLE.

**Solution:** Run `undistort_masks.py` to resize masks using the same transformation:

```bash
python undistort_masks.py \
  --input test_output \
  --output test_output_undistorted
```

This script:
- Reads original OPENCV camera parameters from `test_output/cameras.txt`
- Reads undistorted PINHOLE parameters from `test_output_undistorted/sparse/0/cameras.txt`
- Applies the same undistortion transformation to masks
- Preserves mask edges with nearest-neighbor interpolation

### Symptom: COLMAP doesn't undistort spherical crops (PINHOLE cameras)

**Expected behavior:** COLMAP only undistorts cameras with distortion parameters (OPENCV, RADIAL).

Spherical crops are already PINHOLE (no distortion), so they are copied as-is.

## GPS/EXIF Privacy Issues

### Symptom: Images contain GPS coordinates

If you need to remove GPS data before sharing:

```bash
python strip_gps_exif.py \
  --input /path/to/images \
  --output /path/to/cleaned_images \
  --preserve-other-exif
```

Options:
- `--preserve-other-exif`: Keep camera settings, remove only GPS
- Without flag: Strip all EXIF data
- `--recursive`: Process subdirectories

## Getting Help

If you encounter issues not covered here:

1. Check that you're using the latest version of all tools
2. Verify your Metashape export is complete (cameras.xml + point cloud PLY)
3. Review the conversion logs for warnings
4. Check the GitHub issues for similar problems
