#!/usr/bin/env python3
"""
Strip GPS and other location EXIF data from images while preserving camera calibration data.

Usage:
    python strip_gps_exif.py --input ./images --output ./images_no_gps
    python strip_gps_exif.py --input ./images --in-place  # Overwrites originals (USE WITH CAUTION)
"""

import argparse
from pathlib import Path
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import shutil
from typing import Optional

# GPS-related EXIF tags to remove
GPS_TAGS = {
    'GPSInfo',
    'GPSVersionID',
    'GPSLatitudeRef',
    'GPSLatitude',
    'GPSLongitudeRef',
    'GPSLongitude',
    'GPSAltitudeRef',
    'GPSAltitude',
    'GPSTimeStamp',
    'GPSSatellites',
    'GPSStatus',
    'GPSMeasureMode',
    'GPSDOP',
    'GPSSpeedRef',
    'GPSSpeed',
    'GPSTrackRef',
    'GPSTrack',
    'GPSImgDirectionRef',
    'GPSImgDirection',
    'GPSMapDatum',
    'GPSDestLatitudeRef',
    'GPSDestLatitude',
    'GPSDestLongitudeRef',
    'GPSDestLongitude',
    'GPSDestBearingRef',
    'GPSDestBearing',
    'GPSDestDistanceRef',
    'GPSDestDistance',
    'GPSProcessingMethod',
    'GPSAreaInformation',
    'GPSDateStamp',
    'GPSDifferential',
}

# Build reverse lookup for tag IDs
TAG_ID_TO_NAME = {v: k for k, v in TAGS.items()}
TAG_NAME_TO_ID = {k: v for k, v in TAGS.items()}


def strip_gps_from_image(
    input_path: Path,
    output_path: Optional[Path] = None,
    preserve_other_exif: bool = True,
) -> bool:
    """
    Remove GPS EXIF data from an image.

    Args:
        input_path: Path to input image
        output_path: Path to output image (if None, overwrites input)
        preserve_other_exif: If True, keep non-GPS EXIF data

    Returns:
        True if successful, False otherwise
    """
    try:
        img = Image.open(input_path)

        # Get EXIF data
        exif = img.getexif()
        if exif is None or len(exif) == 0:
            # No EXIF data, just copy the image
            if output_path and output_path != input_path:
                shutil.copy2(input_path, output_path)
            return True

        if preserve_other_exif:
            # Remove GPSInfo tag (tag ID 34853) directly from the exif object
            gps_ifd_tag = 34853
            if gps_ifd_tag in exif:
                del exif[gps_ifd_tag]

            # Also remove individual GPS tags if they somehow exist at root level
            for tag_name in GPS_TAGS:
                tag_id = TAG_NAME_TO_ID.get(tag_name)
                if tag_id and tag_id in exif:
                    del exif[tag_id]

            # Save with cleaned EXIF
            save_path = output_path if output_path else input_path
            img.save(save_path, exif=exif, quality=98)
        else:
            # Strip all EXIF data
            save_path = output_path if output_path else input_path
            data = list(img.getdata())
            image_without_exif = Image.new(img.mode, img.size)
            image_without_exif.putdata(data)
            image_without_exif.save(save_path, quality=98)

        return True

    except Exception as e:
        print(f"Error processing {input_path}: {e}")
        return False


def process_directory(
    input_dir: Path,
    output_dir: Optional[Path] = None,
    in_place: bool = False,
    preserve_other_exif: bool = True,
    verbose: bool = True,
) -> dict:
    """
    Process all images in a directory.

    Args:
        input_dir: Input directory containing images
        output_dir: Output directory (required if not in_place)
        in_place: If True, overwrite original files
        preserve_other_exif: If True, keep non-GPS EXIF data
        verbose: Print progress

    Returns:
        Dictionary with processing statistics
    """
    if not in_place and output_dir is None:
        raise ValueError("Must specify output_dir or use --in-place")

    if output_dir and not in_place:
        output_dir.mkdir(parents=True, exist_ok=True)

    # Supported image extensions
    image_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.webp', '.JPG', '.JPEG'}

    image_files = []
    for ext in image_extensions:
        image_files.extend(input_dir.glob(f'*{ext}'))

    stats = {
        'total': len(image_files),
        'success': 0,
        'failed': 0,
        'skipped': 0,
    }

    if verbose:
        print(f"Found {len(image_files)} images in {input_dir}")
        print(f"GPS EXIF data will be removed, other EXIF {'preserved' if preserve_other_exif else 'removed'}")
        if in_place:
            print("WARNING: Operating in-place mode, original files will be overwritten!")

    for i, img_path in enumerate(image_files, 1):
        if verbose:
            print(f"[{i}/{len(image_files)}] Processing {img_path.name}...", end=' ')

        if in_place:
            output_path = img_path
        else:
            output_path = output_dir / img_path.name

        success = strip_gps_from_image(img_path, output_path, preserve_other_exif)

        if success:
            stats['success'] += 1
            if verbose:
                print("✓")
        else:
            stats['failed'] += 1
            if verbose:
                print("✗")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Strip GPS EXIF data from images while preserving camera calibration",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '--input',
        type=Path,
        required=True,
        help="Input directory containing images"
    )
    parser.add_argument(
        '--output',
        type=Path,
        help="Output directory for processed images (required unless --in-place)"
    )
    parser.add_argument(
        '--in-place',
        action='store_true',
        help="Overwrite original files (WARNING: cannot be undone!)"
    )
    parser.add_argument(
        '--strip-all-exif',
        action='store_true',
        help="Remove ALL EXIF data, not just GPS (may affect Metashape calibration)"
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help="Suppress progress output"
    )

    args = parser.parse_args()

    if not args.input.is_dir():
        print(f"Error: Input directory not found: {args.input}")
        return 1

    if not args.in_place and not args.output:
        print("Error: Must specify --output or use --in-place")
        return 1

    if args.in_place and args.output:
        print("Error: Cannot use both --output and --in-place")
        return 1

    # Confirm in-place operation
    if args.in_place and not args.quiet:
        print("\n⚠️  WARNING: You are about to modify files IN-PLACE!")
        print(f"   All images in {args.input} will be overwritten.")
        response = input("   Type 'yes' to continue: ")
        if response.lower() != 'yes':
            print("Cancelled.")
            return 0

    stats = process_directory(
        input_dir=args.input,
        output_dir=args.output,
        in_place=args.in_place,
        preserve_other_exif=not args.strip_all_exif,
        verbose=not args.quiet,
    )

    if not args.quiet:
        print("\nProcessing complete:")
        print(f"  Total: {stats['total']}")
        print(f"  Success: {stats['success']}")
        print(f"  Failed: {stats['failed']}")

    return 0 if stats['failed'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
