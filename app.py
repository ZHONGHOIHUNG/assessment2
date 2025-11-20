"""Flask application for AI Product Search"""
from flask import Flask, render_template, jsonify, request, Response, stream_with_context, send_from_directory
from flask_cors import CORS
import json
import os
from config import Config
import httpx
from urllib.parse import unquote
import os
from product_indexer import ProductIndexer
from search_engine import SearchEngine

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

from db import db
from epd_api import epd_bp

# Initialize configuration
Config.init_app()

# Init extensions
CORS(app, resources={r"/api/*": {"origins": ["http://localhost:5173", "http://127.0.0.1:5173", "*"]}})
db.init_app(app)

with app.app_context():
    db.create_all()

# Register blueprints
app.register_blueprint(epd_bp)

# Lightweight JSON assessment endpoint (accepts arbitrary product dicts)
@app.post('/api/assess-products')
def assess_products():
    try:
        from rule_engine import evaluate_product
        data = request.get_json() or {}
        products = data.get('products', [])
        assessed = []
        for p in products:
            risk, reasons, advisories = evaluate_product(p)
            has_epd = bool((p.get('epd_url') or '').strip())
            assessed.append({
                'product_id': p.get('id') or p.get('product_id'),
                'product_name': p.get('product_name') or p.get('name'),
                'manufacturer': p.get('manufacturer_name') or p.get('manufacturer'),
                'has_epd': has_epd,
                'epd_url': p.get('epd_url'),
                'has_issue_date': bool((p.get('epd_issue_date') or '').strip()),
                'risk_level': risk.lower(),
                'risk_reason': '；'.join(reasons) if reasons else ''
            })

        # Default sorting: risk(red,yellow,green) -> no EPD first -> name
        risk_order = {'red': 0, 'yellow': 1, 'green': 2}
        assessed.sort(key=lambda x: (
            risk_order.get(x['risk_level'], 3),
            (not x['has_epd']) is False,  # False (no EPD) should come first => key False before True
            (x.get('product_name') or '').lower()
        ))

        return jsonify({
            'success': True,
            'products': assessed,
            'summary': {
                'total': len(assessed),
                'red': sum(1 for a in assessed if a['risk_level'] == 'red'),
                'yellow': sum(1 for a in assessed if a['risk_level'] == 'yellow'),
                'green': sum(1 for a in assessed if a['risk_level'] == 'green')
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Global variables for indexer and search engine
indexer = None
search_engine = None


def init_search_system():
    """Initialize the product indexer and search engine"""
    global indexer, search_engine
    
    if indexer is None:
        print("Initializing search system...")
        indexer = ProductIndexer(api_key=Config.OPENAI_API_KEY)
        indexer.load_products()
        
        # Generate embeddings (will use cache if available)
        try:
            indexer.generate_embeddings()
        except Exception as e:
            print(f"Warning: Could not generate embeddings: {e}")
            print("Search functionality will be limited without embeddings.")
        
        search_engine = SearchEngine(indexer, api_key=Config.OPENAI_API_KEY)
        print("Search system initialized!")


@app.route('/')
def index():
    """Main dashboard page"""
    init_search_system()
    return render_template('dashboard.html')


@app.route('/api/products')
def get_all_products():
    """
    Get all products with optional filtering (no search query needed).
    
    Query parameters:
        categories: comma-separated category names
        manufacturers: comma-separated manufacturer names
        has_certifications: true/false
        has_carbon_data: true/false
        limit: max number of products (default: 100)
    
    Returns:
        {
            "success": true,
            "results": [...products...],
            "count": number of results,
            "total": total products in database
        }
    """
    try:
        init_search_system()
        
        # Get filter parameters
        filters = {}
        
        categories = request.args.get('categories')
        if categories:
            filters['categories'] = categories.split(',')
        
        manufacturers = request.args.get('manufacturers')
        if manufacturers:
            filters['manufacturers'] = manufacturers.split(',')
        
        if request.args.get('has_certifications') == 'true':
            filters['has_certifications'] = True
        
        if request.args.get('has_carbon_data') == 'true':
            filters['has_carbon_data'] = True
        
        limit = int(request.args.get('limit', 100))
        
        # Get filtered products
        all_products = indexer.products
        filtered_products = []
        
        for product in all_products:
            if search_engine._passes_filters(product, filters):
                filtered_products.append(product)
                if len(filtered_products) >= limit:
                    break
        
        return jsonify({
            'success': True,
            'results': filtered_products,
            'count': len(filtered_products),
            'total': len(indexer.products)
        })
    
    except Exception as e:
        print(f"Products fetch error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/search', methods=['POST'])
def search():
    """
    Search endpoint using hybrid AI search with optional filtering and pagination.
    
    Request body:
        {
            "query": "search query",  // optional - if empty, returns filtered products
            "filters": {
                "categories": ["category1", "category2"],
                "manufacturers": ["manufacturer1"],
                "has_certifications": true,
                "has_carbon_data": true
            },
            "use_llm_refinement": true,
            "page": 1,  // page number (1-indexed)
            "per_page": 50  // products per page
        }
    
    Returns:
        {
            "success": true,
            "query": "original query",
            "results": [...products...],
            "count": number of results on this page,
            "total": total matching products,
            "page": current page,
            "per_page": products per page,
            "total_pages": total number of pages
        }
    """
    try:
        init_search_system()
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        query = data.get('query', '').strip()
        filters = data.get('filters')
        use_llm = data.get('use_llm_refinement', True)
        page = max(1, data.get('page', 1))
        per_page = min(100, max(10, data.get('per_page', 50)))  # Between 10-100
        
        # If no query, just return filtered products
        if not query:
            all_products = indexer.products
            filtered_products = []
            
            for product in all_products:
                if filters and not search_engine._passes_filters(product, filters):
                    continue
                filtered_products.append(product)
            
            # Paginate
            total = len(filtered_products)
            total_pages = (total + per_page - 1) // per_page
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            paginated_products = filtered_products[start_idx:end_idx]
            
            return jsonify({
                'success': True,
                'query': '',
                'results': paginated_products,
                'count': len(paginated_products),
                'total': total,
                'page': page,
                'per_page': per_page,
                'total_pages': total_pages
            })
        
        # Perform AI search if query provided
        results = search_engine.search(query, filters=filters, use_llm_refinement=use_llm)
        
        # Note: AI search returns limited results (TOP_K_FINAL), so pagination is less relevant
        # But we can still paginate if needed
        total = len(results)
        total_pages = (total + per_page - 1) // per_page
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_results = results[start_idx:end_idx]
        
        return jsonify({
            'success': True,
            'query': query,
            'results': paginated_results,
            'count': len(paginated_results),
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages
        })
    
    except Exception as e:
        print(f"Search error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/products/<int:product_id>')
def get_product(product_id):
    """
    Get detailed information for a specific product.
    
    Returns:
        Product object with all details
    """
    try:
        init_search_system()
        
        product = indexer.get_product_by_id(product_id)
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        return jsonify(product)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.get('/api/product')
def get_product_flexible():
    """
    Get product details by a flexible identifier.
    Accepts query param 'id' which can be a numeric id or other known id fields.
    """
    try:
        init_search_system()
        raw_id = (request.args.get('id') or '').strip()
        if not raw_id:
            return jsonify({'error': 'Missing id'}), 400

        # Try numeric id first
        product = None
        try:
            num_id = int(raw_id)
            product = indexer.get_product_by_id(num_id)
        except Exception:
            product = None

        # Fallback: match against common id-like fields
        if not product:
            for p in indexer.products:
                candidates = [
                    str(p.get('id')) if p.get('id') is not None else '',
                    str(p.get('product_id') or ''),
                    str(p.get('sku') or ''),
                    str(p.get('code') or ''),
                ]
                if raw_id in candidates:
                    product = p
                    break

        if not product:
            return jsonify({'error': 'Product not found'}), 404

        return jsonify(product)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/filters')
def get_filters():
    """
    Get available filter options for the UI.
    
    Returns:
        {
            "categories": [{name, count}, ...],
            "manufacturers": [{name, count}, ...],
            "certifications": [...]
        }
    """
    try:
        init_search_system()
        
        filter_options = indexer.get_filter_options()
        return jsonify(filter_options)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/certifications')
def get_certification_types():
    """List distinct certification names present in dataset."""
    try:
        init_search_system()
        # indexer.filter_indexes['certifications'] is a set of names
        names = sorted(list(indexer.filter_indexes.get('certifications', [])))
        return jsonify({'count': len(names), 'names': names})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats')
def get_stats():
    """
    Get product database statistics for dashboard.
    
    Returns:
        Statistics about products, categories, manufacturers, etc.
    """
    try:
        init_search_system()
        
        stats = indexer.get_statistics()
        return jsonify(stats)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Conversational AI for product recommendations (streaming).
    
    Request body:
        {
            "query": "user question",
            "history": [{"role": "user/assistant", "content": "..."}]
        }
    
    Returns:
        Server-Sent Events stream with AI response
    """
    try:
        init_search_system()
        
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({'error': 'No query provided'}), 400
        
        query = data['query']
        history = data.get('history', [])
        
        def generate():
            """Generate streaming response"""
            try:
                # Send start event
                yield f"data: {json.dumps({'type': 'start'})}\n\n"
                
                # Stream AI response
                for chunk in search_engine.stream_chat(query, history):
                    yield f"data: {json.dumps({'type': 'content', 'text': chunk})}\n\n"
                
                # Send done event
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        
        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/similar/<int:product_id>')
def get_similar_products(product_id):
    """
    Find products similar to a given product.
    
    Returns:
        List of similar products
    """
    try:
        init_search_system()
        
        product = indexer.get_product_by_id(product_id)
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        # Create a search query from the product
        query = f"{product.get('product_name', '')} {product.get('product_description', '')}"
        
        # Search for similar products
        results = search_engine.semantic_search(query, top_k=11)
        
        # Filter out the original product
        similar = [r for r in results if r['id'] != product_id][:10]
        
        return jsonify({
            'product_id': product_id,
            'similar_products': similar,
            'count': len(similar)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    try:
        init_search_system()
        
        return jsonify({
            'status': 'healthy',
            'products_loaded': len(indexer.products),
            'embeddings_ready': indexer.embeddings is not None,
            'api_configured': Config.OPENAI_API_KEY is not None
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


@app.get('/api/proxy-image')
def proxy_image():
    """Proxy relative image paths to public storage so the UI can render images.

    Query:
      - path: relative path like "/products/Brand/file.jpg"
    Tries known bases and returns the first successful image response.
    """
    rel_path = request.args.get('path') or ''
    rel_path = rel_path.strip()
    if not rel_path:
        return jsonify({'error': 'Missing path'}), 400

    # Only allow a safe subset of prefixes
    allowed = (
        rel_path.startswith('/products/') or rel_path.startswith('products/') or
        rel_path.startswith('/media/products/') or rel_path.startswith('media/products/')
    )
    if not allowed:
        return jsonify({'error': 'Unsupported path'}), 400

    # Decode percent-encoding to get the real S3 key
    clean = unquote(rel_path.lstrip('/'))
    candidates = []
    # Try as-is
    candidates.append(f'https://architectsdeclareapp.s3.amazonaws.com/{clean}')
    # If it's products/..., also try media/products/...
    if clean.startswith('products/'):
        candidates.append(f'https://architectsdeclareapp.s3.amazonaws.com/media/{clean}')
    # If it's media/products/..., we already tried as-is

    for url in candidates:
        try:
            with httpx.Client(follow_redirects=True, timeout=10) as client:
                r = client.get(url)
                if r.status_code == 200:
                    ct = r.headers.get('content-type', 'application/octet-stream')
                    if not ct.startswith('image/'):
                        continue
                    return Response(r.content, headers={'Content-Type': ct, 'Cache-Control': 'public, max-age=86400'})
        except Exception:
            continue

    return jsonify({'error': 'Image not found'}), 404

# -------- Serve built frontend (EPD Risk Scanner) via Flask only --------

@app.route('/epd-app/')
@app.route('/epd-app/<path:path>')
def serve_epd_app(path='index.html'):
    """
    Serve the built React app (Vite dist) without running the frontend dev server.
    Visit: /epd-app/
    """
    # If it looks like a static asset (e.g. assets/foo.js), serve from static/assets
    if path.startswith('assets/'):
        return send_from_directory('static', path)
    
    # Otherwise serve the index.html (React entry point)
    return render_template('index.html')



@app.route('/assets/<path:path>')
def serve_assets(path):
    """Serve React assets from static/assets"""
    return send_from_directory('static/assets', path)

if __name__ == '__main__':
    # Check if running locally
    if not (os.environ.get('PYTHONANYWHERE_DOMAIN') or os.environ.get('PYTHONANYWHERE_SITE')):
        print("=" * 60)
        print("AI Product Search Application")
        print("=" * 60)
        print("\nStarting Flask server...")
        print("This may take a moment while embeddings are generated...\n")
        
        # Run the app
        app.run(debug=True, host='0.0.0.0', port=5001)

