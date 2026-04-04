import os
import glob
import subprocess
import base64
from flask import Flask, render_template, request, jsonify, send_from_directory
from cache_manager import get_cache_manager

app = Flask(__name__)
cache = get_cache_manager()

BASE_DIR = os.getcwd()
POSTER_DIR = os.path.join(BASE_DIR, 'posters')
THEME_DIR = os.path.join(BASE_DIR, 'themes')
OVERLAY_CACHE_DIR = os.path.join(BASE_DIR, 'overlays_cache')
os.makedirs(POSTER_DIR, exist_ok=True)
os.makedirs(OVERLAY_CACHE_DIR, exist_ok=True)

MAPBOX_TOKEN = os.environ.get('MAPBOX_TOKEN', '')

@app.route('/')
def index():
    themes = []
    # List themes from the cloned directory
    if os.path.exists(THEME_DIR):
        files = glob.glob(os.path.join(THEME_DIR, "*.json"))
        themes = [os.path.basename(f).replace(".json", "") for f in files]
    if not themes:
        themes = ["feature_based", "gradient_roads", "noir", "dark", "light"]
    # Stadium names for autocomplete
    try:
        from stadium_data import list_stadiums
        stadiums = [s['name'] for s in list_stadiums()]
    except Exception:
        stadiums = []
    return render_template('index.html', themes=themes, mapbox_token=MAPBOX_TOKEN, stadiums=stadiums)

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    city = data.get('city', '')
    country = data.get('country', '')
    stadium = data.get('stadium', '')
    theme = data.get('theme')
    radius = str(data.get('radius', 15000))

    if not stadium and (not city or not country):
        return jsonify({'success': False, 'error': 'Provide a stadium name, or both city and country.'})

    # Handle 3D overlay if provided
    overlay_3d = data.get('overlay_3d')
    overlay_size = data.get('overlay_size', 'medium')
    overlay_config = data.get('overlay_config', {})
    overlay_path = None

    if overlay_3d:
        try:
            # Build deterministic cache filename from map view config
            lat = round(float(overlay_config.get('lat', 0)), 5)
            lon = round(float(overlay_config.get('lon', 0)), 5)
            zoom = round(float(overlay_config.get('zoom', 0)), 1)
            pitch = int(overlay_config.get('pitch', 0))
            bearing = int(overlay_config.get('bearing', 0))
            cache_name = f"overlay_{lat}_{lon}_z{zoom}_p{pitch}_b{bearing}.png"
            overlay_path = os.path.join(OVERLAY_CACHE_DIR, cache_name)

            # Only decode and save if not already cached
            if not os.path.exists(overlay_path):
                if ',' in overlay_3d:
                    overlay_3d = overlay_3d.split(',', 1)[1]
                img_bytes = base64.b64decode(overlay_3d)
                with open(overlay_path, 'wb') as f:
                    f.write(img_bytes)
                print(f"3D overlay cached: {cache_name}")
            else:
                print(f"3D overlay cache hit: {cache_name}")
        except Exception as e:
            return jsonify({'success': False, 'error': f'Failed to process 3D overlay: {e}'})

    # Call the original script present in the clone
    cmd = ["python", "create_map_poster.py", "--theme", theme, "--distance", radius]
    if stadium:
        cmd.extend(["--stadium", stadium])
    else:
        cmd.extend(["--city", city, "--country", country])

    if overlay_path:
        cmd.extend(["--overlay-3d", overlay_path, "--overlay-size", overlay_size])
    
    try:
        existing_files = set(glob.glob(os.path.join(POSTER_DIR, "*.png")))
        # 10-minute timeout (600 seconds)
        subprocess.run(cmd, check=True, timeout=600)
        
        current_files = set(glob.glob(os.path.join(POSTER_DIR, "*.png")))
        new_files = list(current_files - existing_files)
        
        if new_files:
            latest_file = max(new_files, key=os.path.getctime)
            return jsonify({
                'success': True, 
                'filename': os.path.basename(latest_file)
            })
        else:
            return jsonify({
                'success': False, 
                'error': 'Script finished but no image file found.'
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/posters/<path:filename>')
def serve_poster(filename):
    return send_from_directory(POSTER_DIR, filename)

# Cache management endpoints
@app.route('/api/cache/stats', methods=['GET'])
def cache_stats():
    """Get cache statistics"""
    try:
        stats = cache.get_cache_stats()
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/cache/clear', methods=['POST'])
def clear_cache_endpoint():
    """Clear cache"""
    try:
        data = request.get_json() or {}
        cache_type = data.get('type', 'all')
        
        if cache_type not in ['all', 'geocoding', 'osm', 'posters']:
            return jsonify({
                'success': False,
                'error': 'Invalid cache type. Use: all, geocoding, osm, or posters'
            }), 400
        
        cache.clear_cache(cache_type)
        
        return jsonify({
            'success': True,
            'message': f'Cleared {cache_type} cache'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/cache/cleanup', methods=['POST'])
def cleanup_cache_endpoint():
    """Remove expired cache files"""
    try:
        removed = cache.cleanup_expired()
        return jsonify({
            'success': True,
            'message': f'Removed {removed} expired files',
            'removed_count': removed
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/health')
def health():
    """Health check with cache info"""
    try:
        stats = cache.get_cache_stats()
        return jsonify({
            'status': 'healthy',
            'cache': {
                'enabled': True,
                'total_size_mb': stats['total_size_mb'],
                'geocoding_count': stats['geocoding']['count'],
                'osm_count': stats['osm_data']['count'],
                'posters_count': stats['posters']['count']
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'degraded',
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5025, debug=False)
