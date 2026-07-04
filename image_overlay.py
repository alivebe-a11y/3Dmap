"""
Image overlay module for MapToPoster
Handles badge/logo placement on maps
"""
import os
from PIL import Image, ImageDraw
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
import numpy as np


def add_badge_overlay(ax, badge_path, position, size=0.15, alpha=0.9, glow=True):
    """
    Add a team badge overlay to the map
    
    Args:
        ax: Matplotlib axes object
        badge_path: Path to badge PNG file
        position: (lat, lon) tuple OR (x, y) in axes coordinates
        size: Size as fraction of plot (0.0-1.0)
        alpha: Transparency (0.0-1.0)
        glow: Add glow effect around badge
        
    Returns:
        AnnotationBbox object
    """
    if not os.path.exists(badge_path):
        print(f"⚠️  Badge file not found: {badge_path}")
        return None
    
    try:
        # Load badge image
        badge_img = Image.open(badge_path)
        
        # Ensure RGBA mode
        if badge_img.mode != 'RGBA':
            badge_img = badge_img.convert('RGBA')
        
        # Target size in real output pixels: `size` is the fraction of
        # poster width the badge should occupy. The old base of
        # `size * 1000` px bore no relation to the output canvas
        # (a 200px badge on a 12000px poster).
        fig = ax.get_figure()
        poster_width_px = fig.get_figwidth() * fig.dpi
        target_w = max(1, int(size * poster_width_px))
        aspect_ratio = badge_img.width / badge_img.height
        target_h = max(1, int(target_w / aspect_ratio))

        # Only ever downscale the source; if the badge file is smaller than
        # the target, the zoom factor upscales at draw time (source-limited).
        if badge_img.width > target_w:
            badge_img = badge_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

        # Apply alpha
        if alpha < 1.0:
            badge_array = np.array(badge_img)
            badge_array[:, :, 3] = (badge_array[:, :, 3] * alpha).astype(np.uint8)
            badge_img = Image.fromarray(badge_array)

        # dpi_cor=False: rendered canvas px = image px × zoom (see add_3d_overlay)
        zoom = target_w / badge_img.width
        imagebox = OffsetImage(badge_img, zoom=zoom, dpi_cor=False)
        
        # Create annotation
        # If position is (lat, lon), convert to data coordinates
        # If position is already in axes coords (0-1), use directly
        if isinstance(position, tuple) and len(position) == 2:
            # Assume axes coordinates (0-1 range)
            xy = position
            xycoords = 'axes fraction'
        else:
            xy = position
            xycoords = 'data'
        
        ab = AnnotationBbox(
            imagebox, 
            xy,
            xycoords=xycoords,
            frameon=False,
            box_alignment=(0.5, 0.5)
        )
        
        # Add glow effect if requested
        if glow:
            # Create a white circle behind the badge
            circle = patches.Circle(
                xy, 
                size * 0.08,  # Slightly larger than badge
                transform=ax.transAxes,
                facecolor='white',
                edgecolor='none',
                alpha=0.3,
                zorder=9
            )
            ax.add_patch(circle)
        
        # Add badge
        ax.add_artist(ab)
        
        return ab
        
    except Exception as e:
        print(f"✗ Error adding badge overlay: {e}")
        return None


def add_stadium_marker(ax, coords, color='red', size=200, alpha=0.8, style='star'):
    """
    Add a marker at stadium location
    
    Args:
        ax: Matplotlib axes object
        coords: (lat, lon) tuple in axes coordinates (0-1)
        color: Marker color
        size: Marker size
        alpha: Transparency
        style: 'star', 'circle', 'pin', or 'crosshair'
    """
    x, y = coords
    
    if style == 'star':
        ax.scatter(x, y, 
                  marker='*', 
                  s=size, 
                  c=color, 
                  alpha=alpha,
                  edgecolors='white',
                  linewidths=2,
                  transform=ax.transAxes,
                  zorder=12)
    elif style == 'circle':
        circle = patches.Circle(
            (x, y),
            0.02,  # Radius in axes coordinates
            transform=ax.transAxes,
            facecolor=color,
            edgecolor='white',
            linewidth=2,
            alpha=alpha,
            zorder=12
        )
        ax.add_patch(circle)
    elif style == 'pin':
        # Map pin shape (triangle pointing down with circle on top)
        ax.scatter(x, y, 
                  marker='v',  # Triangle down
                  s=size, 
                  c=color, 
                  alpha=alpha,
                  edgecolors='white',
                  linewidths=2,
                  transform=ax.transAxes,
                  zorder=12)
        ax.scatter(x, y + 0.015,  # Circle above
                  marker='o', 
                  s=size * 0.4, 
                  c=color, 
                  alpha=alpha,
                  edgecolors='white',
                  linewidths=2,
                  transform=ax.transAxes,
                  zorder=12)
    elif style == 'crosshair':
        # Crosshair
        line_length = 0.03
        ax.plot([x - line_length, x + line_length], [y, y],
               color=color, linewidth=3, alpha=alpha,
               transform=ax.transAxes, zorder=12)
        ax.plot([x, x], [y - line_length, y + line_length],
               color=color, linewidth=3, alpha=alpha,
               transform=ax.transAxes, zorder=12)
        # Center dot
        ax.scatter(x, y, 
                  marker='o', 
                  s=size * 0.3, 
                  c=color, 
                  alpha=alpha,
                  edgecolors='white',
                  linewidths=2,
                  transform=ax.transAxes,
                  zorder=12)


def calculate_axes_position(lat, lon, map_bounds):
    """
    Convert lat/lon to axes coordinates (0-1 range)
    
    Args:
        lat: Latitude
        lon: Longitude
        map_bounds: (min_lat, max_lat, min_lon, max_lon) tuple
        
    Returns:
        (x, y) in axes coordinates
    """
    min_lat, max_lat, min_lon, max_lon = map_bounds
    
    # Normalize to 0-1 range
    x = (lon - min_lon) / (max_lon - min_lon) if max_lon != min_lon else 0.5
    y = (lat - min_lat) / (max_lat - min_lat) if max_lat != min_lat else 0.5
    
    return (x, y)


def _chroma_key_dark_background(img, bg_value=5, t0=8, t1=35):
    """
    Deterministic background removal for captures rendered on a known
    near-black background (#050505).

    Computes each pixel's Chebyshev distance from the background value and
    maps it through a soft ramp: fully transparent at distance <= t0, fully
    opaque at distance >= t1. Anti-aliased edges between the landmark and
    the background land inside the ramp and get smooth partial alpha.

    Replaces the earlier rembg/SAM approach, which required a model
    download + GPU and silently failed when no point prompt was supplied.
    """
    arr = np.asarray(img.convert('RGB'), dtype=np.int16)
    dist = np.abs(arr - bg_value).max(axis=2)
    ramp = np.clip((dist - t0) / float(t1 - t0), 0.0, 1.0)
    alpha = (ramp * 255).astype(np.uint8)
    rgba = np.dstack([arr.astype(np.uint8), alpha])
    return Image.fromarray(rgba, 'RGBA')


def _radial_vignette_mask(size_px, inner_fraction=0.80):
    """
    Circular vignette alpha mask as a numpy array (0-255): opaque inside
    inner_fraction of the radius, fading smoothly to transparent at the edge.
    Computed analytically — the previous 1px ellipse-outline loop produced
    visible banding at print resolution.
    """
    yy, xx = np.ogrid[:size_px, :size_px]
    c = (size_px - 1) / 2.0
    r = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / c
    fade = np.clip((1.0 - r) / (1.0 - inner_fraction), 0.0, 1.0)
    return (fade * 255).astype(np.uint8)


def add_3d_overlay(ax, overlay_path, size='medium', alpha=0.95):
    """
    Add a 3D landmark capture as a centered overlay on the poster.

    The capture is rendered by the browser on a guaranteed #050505
    background; the background is removed with a deterministic chroma key
    and a circular vignette softens the edges.

    Sizing is derived from the actual output canvas (figure size × DPI) so
    the rendered overlay really is the advertised fraction of poster width
    at full print resolution.

    Args:
        ax: Matplotlib axes object
        overlay_path: Path to the 3D capture PNG file
        size: 'small' (20%), 'medium' (35%), or 'large' (50%) of poster width
        alpha: Overall transparency (0.0-1.0)

    Returns:
        AnnotationBbox object or None
    """
    if not os.path.exists(overlay_path):
        print(f"⚠️  3D overlay file not found: {overlay_path}")
        return None

    size_map = {'small': 0.20, 'medium': 0.35, 'large': 0.50}
    size_fraction = size_map.get(size, 0.35)

    try:
        img = Image.open(overlay_path).convert('RGBA')

        # Remove the #050505 capture background
        img = _chroma_key_dark_background(img)

        # Crop to square from center
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        img = img.crop((left, top, left + side, top + side))

        # Target size in real output pixels (poster width in px × fraction)
        fig = ax.get_figure()
        poster_width_px = fig.get_figwidth() * fig.dpi
        target_px = max(1, int(size_fraction * poster_width_px))

        # Only ever downscale — upscaling past the capture's native
        # resolution is done by the (small) zoom factor at draw time.
        if img.size[0] > target_px:
            img = img.resize((target_px, target_px), Image.Resampling.LANCZOS)

        # Circular vignette, combined with the chroma-key alpha
        mask = _radial_vignette_mask(img.size[0])
        img_array = np.array(img)
        img_array[:, :, 3] = np.minimum(
            img_array[:, :, 3],
            (mask.astype(np.float32) * alpha).astype(np.uint8)
        )
        img = Image.fromarray(img_array)

        # dpi_cor=False: rendered size in canvas px = image px × zoom,
        # independent of DPI. (With the default dpi_cor=True the zoom is
        # scaled by dpi/72, which at 500 DPI blew images up ~7× past their
        # pixel data — the old code shipped a 350px image stretched to ~20%
        # of a 12000px poster.)
        zoom = target_px / img.size[0]
        imagebox = OffsetImage(img, zoom=zoom, dpi_cor=False)
        ab = AnnotationBbox(
            imagebox,
            (0.5, 0.55),  # Slightly above center for visual balance
            xycoords='axes fraction',
            frameon=False,
            box_alignment=(0.5, 0.5),
            zorder=8  # Below text (11) and gradient (10), above streets
        )
        ax.add_artist(ab)

        return ab

    except Exception as e:
        print(f"✗ Error adding 3D overlay: {e}")
        return None


def create_circular_badge_mask(image_path, output_path=None):
    """
    Create a circular mask for a badge image
    
    Args:
        image_path: Path to input image
        output_path: Path to save masked image (optional)
        
    Returns:
        PIL Image object
    """
    img = Image.open(image_path).convert('RGBA')
    
    # Create circular mask
    size = min(img.size)
    mask = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    
    # Crop to square
    if img.size[0] != img.size[1]:
        # Center crop to square
        left = (img.size[0] - size) // 2
        top = (img.size[1] - size) // 2
        img = img.crop((left, top, left + size, top + size))
    
    # Apply mask
    output = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    output.paste(img, (0, 0))
    output.putalpha(mask)
    
    if output_path:
        output.save(output_path)
    
    return output
