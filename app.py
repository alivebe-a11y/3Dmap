import os
import glob
import subprocess
import base64
import uuid
from flask import Flask, render_template, request, jsonify, send_from_directory
from cache_manager import get_cache_manager

app = Flask(__name__)
cache = get_cache_manager()

BASE_DIR = os.getcwd()
POSTER_DIR = os.path.join(BASE_DIR, 'posters')
THEME_DIR = os.path.join(BASE_DIR, 'themes')
TEMP_DIR = os.path.join(BASE_DIR, 'temp_overlays')
os.makedirs(POSTER_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

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
    return render_template('index.html', themes=themes, mapbox_token=MAPBOX_TOKEN)

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    city = data.get('city')
    country = data.get('country')
    theme = data.get('theme')
    radius = str(data.get('radius', 15000))
    
    if not city or not country:
        return jsonify({'success': False, 'error': 'City and Country required.'})

    # Handle 3D overlay if provided
    overlay_3d = data.get('overlay_3d')
    overlay_size = data.get('overlay_size', 'medium')
    overlay_path = None

    if overlay_3d:
        try:
            # Strip data URL prefix
            if ',' in overlay_3d:
                overlay_3d = overlay_3d.split(',', 1)[1]
            img_bytes = base64.b64decode(overlay_3d)
            overlay_path = os.path.join(TEMP_DIR, f"3d_{uuid.uuid4().hex}.png")
            with open(overlay_path, 'wb') as f:
                f.write(img_bytes)
        except Exception as e:
            return jsonify({'success': False, 'error': f'Failed to process 3D overlay: {e}'})

    # Call the original script present in the clone
    cmd = [
        "python", "create_map_poster.py",
        "--city", city,
        "--country", country,
        "--distance", radius,
        "--theme", theme
    ]

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
    finally:
        # Clean up temp overlay file
        if overlay_path and os.path.exists(overlay_path):
            try:
                os.remove(overlay_path)
            except OSError:
                pass

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
