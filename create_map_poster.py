import osmnx as ox
from cache_manager import get_cache_manager

cache = get_cache_manager()
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import matplotlib.colors as mcolors
import numpy as np
from geopy.geocoders import Nominatim
from tqdm import tqdm
import time
import json
import os
from datetime import datetime
import argparse

# Stadium features
from stadium_data import find_stadium, get_stadium_coords, list_stadiums
from image_overlay import add_badge_overlay, add_stadium_marker, add_3d_overlay

THEMES_DIR = "themes"
FONTS_DIR = "fonts"
POSTERS_DIR = "posters"

def load_fonts():
    """
    Load Roboto fonts from the fonts directory.
    Returns dict with font paths for different weights.
    """
    fonts = {
        'bold': os.path.join(FONTS_DIR, 'Roboto-Bold.ttf'),
        'regular': os.path.join(FONTS_DIR, 'Roboto-Regular.ttf'),
        'light': os.path.join(FONTS_DIR, 'Roboto-Light.ttf')
    }
    
    # Verify fonts exist
    for weight, path in fonts.items():
        if not os.path.exists(path):
            print(f"⚠ Font not found: {path}")
            return None
    
    return fonts

FONTS = load_fonts()

def generate_output_filename(city, theme_name, stadium_name=None):
    """
    Generate unique output filename with city/stadium, theme, and datetime.
    """
    if not os.path.exists(POSTERS_DIR):
        os.makedirs(POSTERS_DIR)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if stadium_name:
        # Use stadium name for filename
        name_slug = stadium_name.lower().replace(' ', '_').replace("'", '')
        filename = f"{name_slug}_{theme_name}_{timestamp}.png"
    else:
        # Use city name
        city_slug = city.lower().replace(' ', '_')
        filename = f"{city_slug}_{theme_name}_{timestamp}.png"
    
    return os.path.join(POSTERS_DIR, filename)

def get_available_themes():
    """
    Scans the themes directory and returns a list of available theme names.
    """
    if not os.path.exists(THEMES_DIR):
        os.makedirs(THEMES_DIR)
        return []
    
    themes = []
    for file in sorted(os.listdir(THEMES_DIR)):
        if file.endswith('.json'):
            theme_name = file[:-5]  # Remove .json extension
            themes.append(theme_name)
    return themes

def load_theme(theme_name="feature_based"):
    """
    Load theme from JSON file in themes directory.
    """
    theme_path = os.path.join(THEMES_DIR, f"{theme_name}.json")
    
    if not os.path.exists(theme_path):
        print(f"⚠ Theme '{theme_name}' not found. Using default 'feature_based' theme.")
        theme_path = os.path.join(THEMES_DIR, "feature_based.json")
        
        if not os.path.exists(theme_path):
            print(f"✗ Default theme not found. Please ensure themes exist in {THEMES_DIR}")
            return None
    
    try:
        with open(theme_path, 'r') as f:
            theme_data = json.load(f)
        return theme_data
    except Exception as e:
        print(f"✗ Error loading theme: {e}")
        return None

def get_coordinates(city, country):
    """
    Get coordinates for a city with caching support.
    """
    # Try cache first
    cached_coords = cache.get_geocoding(city, country)
    if cached_coords is not None:
        print(f"✓ Using cached coordinates for {city}, {country}")
        return cached_coords
    
    # Cache miss - fetch from Nominatim
    print(f"⊙ Fetching coordinates for {city}, {country}...")
    geolocator = Nominatim(user_agent="map_poster_generator")
    
    try:
        location = geolocator.geocode(f"{city}, {country}")
        if location:
            coords = (location.latitude, location.longitude)
            # Cache the result
            cache.set_geocoding(city, country, coords[0], coords[1])
            print(f"✓ Cached coordinates for {city}, {country}")
            return coords
        else:
            print(f"✗ Could not find coordinates for {city}, {country}")
            return None
    except Exception as e:
        print(f"✗ Geocoding error: {e}")
        return None

def get_edge_colors_by_type(G, THEME):
    """
    Assign colors to edges based on road type hierarchy.
    """
    edge_colors = []
    
    for u, v, k, data in G.edges(keys=True, data=True):
        highway_type = data.get('highway', 'default')
        
        if isinstance(highway_type, list):
            highway_type = highway_type[0]
        
        if highway_type in ['motorway', 'motorway_link', 'trunk']:
            color = THEME['road_motorway']
        elif highway_type in ['primary', 'primary_link']:
            color = THEME['road_primary']
        elif highway_type in ['secondary', 'secondary_link']:
            color = THEME['road_secondary']
        elif highway_type in ['tertiary', 'tertiary_link']:
            color = THEME['road_tertiary']
        elif highway_type in ['residential', 'living_street']:
            color = THEME['road_residential']
        else:
            color = THEME['road_default']
        
        edge_colors.append(color)
    
    return edge_colors

def get_edge_widths_by_type(G):
    """
    Assign line widths based on road importance.
    """
    edge_widths = []
    
    for u, v, k, data in G.edges(keys=True, data=True):
        highway_type = data.get('highway', 'default')
        
        if isinstance(highway_type, list):
            highway_type = highway_type[0]
        
        if highway_type in ['motorway', 'motorway_link']:
            width = 1.2
        elif highway_type in ['trunk', 'primary']:
            width = 1.0
        elif highway_type in ['secondary']:
            width = 0.8
        elif highway_type in ['tertiary']:
            width = 0.6
        elif highway_type in ['residential', 'living_street']:
            width = 0.4
        else:
            width = 0.5
        
        edge_widths.append(width)
    
    return edge_widths

def create_gradient_fade(ax, THEME, height_fraction=0.15):
    """
    Add gradient fade at top and bottom of the poster.
    """
    gradient = np.linspace(0, 1, 256).reshape(256, 1)
    gradient = np.hstack([gradient] * 100)
    
    bg_color = mcolors.to_rgba(THEME['bg'])
    grad_color = mcolors.to_rgba(THEME.get('gradient_color', THEME['bg']))
    
    cmap_top = mcolors.LinearSegmentedColormap.from_list(
        'fade_top', [grad_color, bg_color]
    )
    cmap_bottom = mcolors.LinearSegmentedColormap.from_list(
        'fade_bottom', [bg_color, grad_color]
    )
    
    # Top fade
    ax.imshow(gradient, extent=[0, 1, 1-height_fraction, 1], 
              aspect='auto', cmap=cmap_top, alpha=0.6,
              transform=ax.transAxes, zorder=10)
    
    # Bottom fade
    ax.imshow(np.flipud(gradient), extent=[0, 1, 0, height_fraction],
              aspect='auto', cmap=cmap_bottom, alpha=0.6,
              transform=ax.transAxes, zorder=10)

def create_poster(city, country, theme_name='feature_based', distance=29000,
                 width=24, height=34, dpi=500, attribution='BlueBearLabs',
                 stadium=None, badge_path=None, coords=None, marker_style='star',
                 overlay_3d=None, overlay_size='medium',
                 overlay_3d_base=None, overlay_3d_mask=None, overlay_tint=False):
    """
    Create a map poster with caching support for OSM data.
    
    Args:
        city: City name
        country: Country name
        theme_name: Theme to use
        distance: Map radius in meters
        width: Poster width in inches (default: 24)
        height: Poster height in inches (default: 34)
        dpi: Resolution (default: 500)
        attribution: Custom attribution text (default: 'BlueBearLabs')
        stadium: Stadium name to center on (optional)
        badge_path: Path to team badge PNG (optional)
        coords: Manual coordinates as (lat, lon) tuple (optional)
        marker_style: Stadium marker style - 'star', 'pin', 'circle', 'crosshair', or None
        overlay_3d: Path to a 3D landmark capture PNG to overlay centered on poster
        overlay_size: Size of the 3D overlay - 'small', 'medium', or 'large'
    """
    stadium_data = None
    display_name = city  # For output filename
    
    print(f"\n{'='*60}")
    
    # Get coordinates (priority: coords > stadium > city)
    if coords:
        # Manual coordinates provided
        latitude, longitude = coords
        print(f"📍 Mode: Manual Coordinates")
        print(f"📍 Coordinates: {latitude:.4f}, {longitude:.4f}")
    elif stadium:
        # Look up stadium
        stadium_data = find_stadium(stadium)
        if stadium_data:
            latitude = stadium_data['lat']
            longitude = stadium_data['lon']
            city = stadium_data['city']  # Override city with stadium city
            country = stadium_data['country']  # Override country
            display_name = stadium_data['name']  # Use stadium name for display
            print(f"🏟️  Mode: Stadium")
            print(f"🏟️  Stadium: {stadium_data['name']}")
            print(f"⚽  Team: {stadium_data['team']}")
            print(f"📍 Location: {city}, {country}")
            print(f"📍 Coordinates: {latitude:.4f}, {longitude:.4f}")
        else:
            print(f"⚠️  Stadium '{stadium}' not found in database.")
            print(f"⚠️  Falling back to city geocoding...")
            coords_result = get_coordinates(city, country)
            if coords_result is None:
                print("✗ Failed to get coordinates. Exiting.")
                return None
            latitude, longitude = coords_result
    else:
        # Standard city geocoding
        print(f"🌆 Mode: City")
        coords_result = get_coordinates(city, country)
        if coords_result is None:
            print("✗ Failed to get coordinates. Exiting.")
            return None
        latitude, longitude = coords_result
    
    print(f"🎨 Theme: {theme_name}")
    print(f"📏 Distance: {distance}m")
    print(f"📐 Size: {width}x{height} inches @ {dpi} DPI")
    print(f"✍️  Attribution: {attribution}")
    if badge_path:
        print(f"🎭 Badge: {os.path.basename(badge_path)}")
    print(f"{'='*60}\n")
    
    # Load theme
    THEME = load_theme(theme_name)
    if THEME is None:
        print("✗ Failed to load theme. Exiting.")
        return None
    
    point = (latitude, longitude)

    # The poster is taller than it is wide (e.g. 24x34): `distance` is the
    # horizontal half-extent, so fetch enough OSM data to also fill the
    # taller vertical extent. The view is cropped to the exact poster
    # aspect after plotting.
    aspect = height / width
    fetch_dist = int(distance * max(1.0, aspect))

    # Check OSM cache first
    print(f"⊙ Checking OSM data cache...")
    cached_osm = cache.get_osm_data(latitude, longitude, fetch_dist, 'all')
    
    if cached_osm is not None:
        print(f"✓ Using cached OSM data")
        G = cached_osm['graph']
        water = cached_osm['water']
        parks = cached_osm['parks']
    else:
        # Cache miss - fetch from OSM (slow!)
        print(f"⊙ Fetching OSM data...")
        print(f"   This may take several minutes for the first time...")
        
        # Fetch graph
        print("   → Fetching street network...")
        try:
            G = ox.graph_from_point(
                point, 
                dist=fetch_dist, 
                dist_type='bbox',
                network_type='all',
                truncate_by_edge=True
            )
            print(f"   ✓ Graph: {len(G.nodes)} nodes, {len(G.edges)} edges")
        except Exception as e:
            print(f"   ✗ Error fetching graph: {e}")
            G = None
        
        # Fetch water features
        print("   → Fetching water features...")
        try:
            water = ox.features_from_point(
                point,
                tags={'natural': 'water'},
                dist=fetch_dist
            )
            if water is not None and not water.empty:
                print(f"   ✓ Water: {len(water)} features")
            else:
                print(f"   ℹ No water features found")
                water = None
        except Exception as e:
            print(f"   ℹ No water features: {e}")
            water = None
        
        # Fetch parks
        print("   → Fetching parks...")
        try:
            parks = ox.features_from_point(
                point,
                tags={'leisure': 'park'},
                dist=fetch_dist
            )
            if parks is not None and not parks.empty:
                print(f"   ✓ Parks: {len(parks)} features")
            else:
                print(f"   ℹ No parks found")
                parks = None
        except Exception as e:
            print(f"   ℹ No parks: {e}")
            parks = None
        
        # Cache the OSM data for next time
        print(f"\n✓ Caching OSM data for future use...")
        cache.set_osm_data(latitude, longitude, fetch_dist, 'all', G, water, parks)
    
    if G is None:
        print("✗ No graph data available. Cannot create poster.")
        return None
    
    # Create figure
    print(f"\n🎨 Rendering poster...")
    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    fig.patch.set_facecolor(THEME['bg'])
    ax.set_facecolor(THEME['bg'])
    # Full-bleed: axes cover the whole figure so the saved PNG is exactly
    # width x height inches at the requested DPI (print shops need the
    # exact aspect ratio; bbox_inches='tight' used to crop it per-poster).
    ax.set_position([0, 0, 1, 1])
    
    # Plot water features (if any)
    if water is not None and not water.empty:
        try:
            water.plot(ax=ax, color=THEME['water'], zorder=1)
        except:
            pass
    
    # Plot parks (if any)
    if parks is not None and not parks.empty:
        try:
            parks.plot(ax=ax, color=THEME['parks'], zorder=2)
        except:
            pass
    
    # Plot street network
    edge_colors = get_edge_colors_by_type(G, THEME)
    edge_widths = get_edge_widths_by_type(G)
    
    ox.plot_graph(
        G, ax=ax,
        node_size=0,
        edge_color=edge_colors,
        edge_linewidth=edge_widths,
        bgcolor=THEME['bg'],
        show=False,
        close=False
    )

    # Crop the view to a ground window matching the poster aspect exactly:
    # `distance` metres of half-width and distance * (height/width) of
    # half-height. With the full-bleed axes above, this gives an
    # undistorted map at a uniform metres-per-inch scale in both axes.
    half_h_m = distance * aspect
    dlat = half_h_m / 111320.0
    dlon = distance / (111320.0 * max(0.01, float(np.cos(np.radians(latitude)))))
    ax.set_xlim(longitude - dlon, longitude + dlon)
    ax.set_ylim(latitude - dlat, latitude + dlat)
    ax.set_aspect('auto')

    # Add badge overlay if provided (BEFORE gradient fades so it's visible)
    if badge_path and os.path.exists(badge_path):
        print(f"🎭 Adding badge overlay...")
        # Position badge at actual stadium/city coordinates (center of map)
        # Using axes fraction (0.5, 0.5) which corresponds to center
        # Since the map is centered on the lat/lon, this aligns with the location
        badge_position = (0.5, 0.5)  # Center of axes = center of map = stadium location
        add_badge_overlay(
            ax, 
            badge_path, 
            position=badge_position,
            size=0.2,  # 20% of plot size
            alpha=0.85,
            glow=False  # No glow - badge is clear enough
        )
    elif badge_path:
        print(f"⚠️  Badge file not found: {badge_path}")
    
    # Add stadium marker if in stadium mode (and marker style specified)
    # Skip marker if a badge or a 3D hero replaces it — the marker's zorder
    # (12) is above the overlay (8), so it would stamp a star on the stadium.
    has_3d_hero = bool(overlay_3d and os.path.exists(overlay_3d))
    if stadium_data and marker_style and not badge_path and not has_3d_hero:
        print(f"📍 Adding {marker_style} marker at stadium location...")
        # Determine marker color based on theme
        marker_color = THEME.get('text', '#FFFFFF')
        add_stadium_marker(
            ax,
            coords=(0.5, 0.5),  # Center of axes = center of map = stadium location
            color=marker_color,
            size=400,
            style=marker_style,
            alpha=0.9
        )
    elif stadium_data and marker_style:
        print(f"ℹ️  Skipping marker - {'badge' if badge_path else '3D hero'} provided instead")

    # Add 3D landmark overlay if provided
    if overlay_3d and os.path.exists(overlay_3d):
        print(f"🏛️  Adding 3D landmark overlay ({overlay_size})...")
        # Optional theme tint: hero picks up the poster palette
        tint = None
        if overlay_tint:
            tint = THEME.get('building_3d', THEME.get('road_primary'))
        add_3d_overlay(ax, overlay_3d, size=overlay_size, alpha=0.95,
                       base_path=overlay_3d_base, mask_path=overlay_3d_mask,
                       tint_color=tint)

    # Add gradient fades
    create_gradient_fade(ax, THEME)
    
    # Add text labels
    if FONTS:
        font_bold = FontProperties(fname=FONTS['bold'])
        font_regular = FontProperties(fname=FONTS['regular'])
        font_light = FontProperties(fname=FONTS['light'])
        
        # Title text (city name or stadium name)
        title_text = display_name.upper()
        if stadium_data:
            # For stadiums, use stadium name
            title_text = stadium_data['name'].upper()
        
        # City/Stadium name (spaced letters)
        title_spaced = '  '.join(title_text)
        ax.text(0.5, 0.14, title_spaced,
                fontproperties=font_bold,
                fontsize=88,
                color=THEME['text'],
                ha='center',
                va='center',
                transform=ax.transAxes,
                zorder=11)
        
        # Decorative line
        ax.plot([0.3, 0.7], [0.125, 0.125],
                color=THEME['text'],
                linewidth=2.7,
                transform=ax.transAxes,
                zorder=11)
        
        # Subtitle (country or team name)
        if stadium_data:
            # For stadiums, show team name
            subtitle = stadium_data['team'].upper()
        else:
            # For cities, show country
            subtitle = country.upper()
        
        ax.text(0.5, 0.10, subtitle,
                fontproperties=font_light,
                fontsize=38,
                color=THEME['text'],
                ha='center',
                va='center',
                transform=ax.transAxes,
                zorder=11)
        
        # Coordinates
        coord_text = (
            f"{abs(latitude):.4f}°{'N' if latitude >= 0 else 'S'}  "
            f"{abs(longitude):.4f}°{'E' if longitude >= 0 else 'W'}"
        )
        ax.text(0.5, 0.07, coord_text,
                fontproperties=font_light,
                fontsize=27,
                color=THEME['text'],
                ha='center',
                va='center',
                transform=ax.transAxes,
                zorder=11)
        
        # Attribution - BlueBearLabs
        ax.text(0.95, 0.02, attribution,
                fontproperties=font_light,
                fontsize=22,
                color=THEME['text'],
                ha='right',
                va='bottom',
                alpha=0.6,
                transform=ax.transAxes,
                zorder=11)
    
    # Remove axes
    ax.set_axis_off()
    ax.margins(0)
    
    # Save
    output_file = generate_output_filename(
        city, 
        theme_name, 
        stadium_name=stadium_data['name'] if stadium_data else None
    )
    print(f"💾 Saving to {output_file}...")
    
    # No bbox_inches='tight' — that cropped the output to the drawn content,
    # so the file was never actually width x height. Full-bleed axes + plain
    # savefig produce exactly (width*dpi) x (height*dpi) pixels.
    plt.savefig(
        output_file,
        dpi=dpi,
        facecolor=THEME['bg'],
        edgecolor='none'
    )
    plt.close()
    
    print(f"\n✅ Poster created successfully!")
    print(f"📁 Saved to: {output_file}")
    print(f"{'='*60}\n")
    
    return output_file

def main():
    parser = argparse.ArgumentParser(
        description='Generate beautiful minimalist map posters (cities & stadiums)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # City poster
  %(prog)s -c "London" -C "UK" -t noir -d 15000
  
  # Stadium poster
  %(prog)s --stadium "Old Trafford" -t noir -d 5000
  
  # Stadium with badge
  %(prog)s --stadium "Old Trafford" --badge /app/badges/manutd.png -t noir -d 5000
  
  # Manual coordinates
  %(prog)s --coords "51.5074,-0.1278" -c "Custom" -C "UK" -t noir -d 10000
  
  # List all stadiums
  %(prog)s --list-stadiums
        """
    )
    
    # Required for city mode, optional for stadium mode
    parser.add_argument('-c', '--city', 
                       help='City name (required for city mode, optional for stadium mode)')
    parser.add_argument('-C', '--country', 
                       help='Country name (required for city mode, optional for stadium mode)')
    
    # Theme and size
    parser.add_argument('-t', '--theme', default='feature_based',
                       help='Theme name (default: feature_based)')
    parser.add_argument('-d', '--distance', type=int, default=29000,
                       help='Map radius in meters (default: 29000)')
    parser.add_argument('--width', type=int, default=24,
                       help='Poster width in inches (default: 24)')
    parser.add_argument('--height', type=int, default=34,
                       help='Poster height in inches (default: 34)')
    parser.add_argument('--dpi', type=int, default=500,
                       help='Resolution in DPI (default: 500)')
    parser.add_argument('--attribution', type=str, 
                       default='BlueBearLabs',
                       help='Attribution text in bottom right corner (default: BlueBearLabs)')
    
    # Stadium-specific arguments
    parser.add_argument('--stadium', type=str,
                       help='Stadium name or key to center on (e.g., "Old Trafford", "old_trafford")')
    parser.add_argument('--badge', type=str,
                       help='Path to team badge/logo PNG file for overlay')
    parser.add_argument('--coords', type=str,
                       help='Manual coordinates as "lat,lon" (e.g., "51.5074,-0.1278")')
    parser.add_argument('--marker', type=str,
                       choices=['star', 'pin', 'circle', 'crosshair', 'none'],
                       default='star',
                       help='Stadium marker style (default: star, use "none" for no marker)')

    # 3D overlay arguments
    parser.add_argument('--overlay-3d', type=str,
                       help='Path to a 3D landmark capture PNG to overlay on the poster')
    parser.add_argument('--overlay-size', type=str,
                       choices=['small', 'medium', 'large'],
                       default='medium',
                       help='Size of the 3D overlay (default: medium)')
    parser.add_argument('--overlay-3d-base', type=str,
                       help='Path to the matching no-3D capture (for stadium isolation)')
    parser.add_argument('--overlay-3d-mask', type=str,
                       help='Path to the magenta footprint-volume capture (for stadium isolation)')
    parser.add_argument('--overlay-tint', action='store_true',
                       help='Tint the 3D overlay toward the theme colour')
    
    # Listing options
    parser.add_argument('--list-themes', action='store_true',
                       help='List all available themes')
    parser.add_argument('--list-stadiums', action='store_true',
                       help='List all available stadiums')
    
    # Cache management arguments
    parser.add_argument('--cache-stats', action='store_true',
                       help='Show cache statistics')
    parser.add_argument('--clear-cache', choices=['all', 'geocoding', 'osm', 'posters'],
                       help='Clear cache')
    parser.add_argument('--cleanup-expired', action='store_true',
                       help='Remove expired cache files')
    
    args = parser.parse_args()
    
    # Handle listing commands
    if args.list_stadiums:
        stadiums = list_stadiums()
        print("\n" + "="*90)
        print("AVAILABLE STADIUMS")
        print("="*90)
        print(f"{'Stadium':<32} {'Team':<30} {'Location':<20} {'Sport':<15}")
        print("-"*90)
        for s in stadiums:
            location = f"{s['city']}, {s['country']}"
            print(f"{s['name']:<32} {s['team']:<30} {location:<20} {s['sport']:<15}")
        print("="*90)
        print(f"\nTotal: {len(stadiums)} stadiums")
        print("\nUsage: --stadium \"Stadium Name\" or --stadium \"stadium_key\"")
        print("="*90 + "\n")
        return
    
    # Handle cache commands
    if args.cache_stats:
        stats = cache.get_cache_stats()
        print("\n" + "="*60)
        print("CACHE STATISTICS")
        print("="*60)
        print(f"Geocoding: {stats['geocoding']['count']:>4} files, {stats['geocoding']['size_mb']:>8.2f} MB")
        print(f"OSM Data:  {stats['osm_data']['count']:>4} files, {stats['osm_data']['size_mb']:>8.2f} MB")
        print(f"Posters:   {stats['posters']['count']:>4} files, {stats['posters']['size_mb']:>8.2f} MB")
        print("-"*60)
        print(f"Total:     {stats['total_size_mb']:>8.2f} MB")
        print("="*60 + "\n")
        return
    
    if args.cleanup_expired:
        removed = cache.cleanup_expired()
        print(f"\n✓ Removed {removed} expired cache files\n")
        return
    
    if args.clear_cache:
        cache.clear_cache(args.clear_cache)
        print(f"\n✓ Cleared {args.clear_cache} cache\n")
        return
    
    # List themes
    if args.list_themes:
        themes = get_available_themes()
        print("\nAvailable themes:")
        print("="*60)
        for theme in themes:
            print(f"  • {theme}")
        print("="*60 + "\n")
        return
    
    # Validate required arguments
    if not args.stadium and not args.coords:
        # City mode - require city and country
        if not args.city or not args.country:
            parser.error("City mode requires -c/--city and -C/--country arguments")
    
    # Set defaults for stadium mode
    city = args.city if args.city else "Unknown"
    country = args.country if args.country else "Unknown"
    
    # Parse coordinates if provided
    coords = None
    if args.coords:
        try:
            lat_str, lon_str = args.coords.split(',')
            coords = (float(lat_str.strip()), float(lon_str.strip()))
        except:
            print(f"✗ Invalid coordinates format. Use: lat,lon (e.g., '51.5074,-0.1278')")
            return
    
    # Parse marker style
    marker_style = args.marker if args.marker != 'none' else None
    
    # Create poster
    create_poster(
        city=city,
        country=country,
        theme_name=args.theme,
        distance=args.distance,
        width=args.width,
        height=args.height,
        dpi=args.dpi,
        attribution=args.attribution,
        stadium=args.stadium,
        badge_path=args.badge,
        coords=coords,
        marker_style=marker_style,
        overlay_3d=args.overlay_3d,
        overlay_size=args.overlay_size,
        overlay_3d_base=args.overlay_3d_base,
        overlay_3d_mask=args.overlay_3d_mask,
        overlay_tint=args.overlay_tint
    )

if __name__ == "__main__":
    main()
