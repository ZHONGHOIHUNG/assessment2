"""Product indexing and embedding generation"""
import json
import os
import pickle
import numpy as np
from openai import OpenAI
from config import Config
from prompts import get_product_embedding_text


class ProductIndexer:
    """Handles product loading, embedding generation, and indexing"""
    
    def __init__(self, api_key=None):
        self.api_key = api_key or Config.OPENAI_API_KEY
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None
        self.products = []
        self.embeddings = None
        self.filter_indexes = {
            'categories': {},
            'manufacturers': {},
            'certifications': set(),
            'price_ranges': {}
        }
    
    def load_products(self, file_path=None):
        """Load products from JSON file"""
        file_path = file_path or Config.PRODUCT_DATA_FILE
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Product data file not found: {file_path}")
        
        print(f"Loading products from {file_path}...")
        with open(file_path, 'r', encoding='utf-8') as f:
            self.products = json.load(f)
        
        print(f"Loaded {len(self.products)} products")
        self._build_filter_indexes()
        return self.products
    
    def _build_filter_indexes(self):
        """Build indexes for filtering"""
        print("Building filter indexes...")
        
        for product in self.products:
            # Category index
            categories = product.get('product_categories', [])
            for cat in categories:
                cat_name = cat.get('category_name')
                if cat_name:
                    if cat_name not in self.filter_indexes['categories']:
                        self.filter_indexes['categories'][cat_name] = []
                    self.filter_indexes['categories'][cat_name].append(product['id'])
            
            # Manufacturer index
            manufacturer = product.get('manufacturer_name')
            if manufacturer:
                if manufacturer not in self.filter_indexes['manufacturers']:
                    self.filter_indexes['manufacturers'][manufacturer] = []
                self.filter_indexes['manufacturers'][manufacturer].append(product['id'])
            
            # Certifications
            certs = product.get('certifications', [])
            for cert in certs:
                cert_name = cert.get('certification')
                if cert_name:
                    self.filter_indexes['certifications'].add(cert_name)
        
        print(f"  - {len(self.filter_indexes['categories'])} categories")
        print(f"  - {len(self.filter_indexes['manufacturers'])} manufacturers")
        print(f"  - {len(self.filter_indexes['certifications'])} certification types")
    
    def generate_embeddings(self, force_regenerate=False):
        """Generate embeddings for all products"""
        cache_file = Config.EMBEDDINGS_CACHE_FILE
        
        # Try to load from cache
        if not force_regenerate and Config.CACHE_EMBEDDINGS and os.path.exists(cache_file):
            print(f"Loading embeddings from cache: {cache_file}")
            try:
                with open(cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                    if len(cache_data['embeddings']) == len(self.products):
                        self.embeddings = cache_data['embeddings']
                        print(f"Loaded {len(self.embeddings)} embeddings from cache")
                        return self.embeddings
            except Exception as e:
                print(f"Failed to load cache: {e}")
        
        # Generate embeddings
        if not self.client:
            raise ValueError("OpenAI client not initialized. Please provide API key.")
        
        print(f"Generating embeddings for {len(self.products)} products...")
        print("This may take a few minutes...")
        
        embeddings_list = []
        batch_size = 100
        
        for i in range(0, len(self.products), batch_size):
            batch = self.products[i:i+batch_size]
            batch_texts = [get_product_embedding_text(p) for p in batch]
            
            # Call OpenAI API
            response = self.client.embeddings.create(
                model=Config.EMBEDDING_MODEL,
                input=batch_texts
            )
            
            batch_embeddings = [item.embedding for item in response.data]
            embeddings_list.extend(batch_embeddings)
            
            print(f"  Generated {len(embeddings_list)}/{len(self.products)} embeddings")
        
        self.embeddings = np.array(embeddings_list)
        
        # Cache the embeddings
        if Config.CACHE_EMBEDDINGS:
            print(f"Caching embeddings to {cache_file}")
            with open(cache_file, 'wb') as f:
                pickle.dump({
                    'embeddings': self.embeddings,
                    'product_count': len(self.products)
                }, f)
        
        print(f"Embeddings generated: shape {self.embeddings.shape}")
        return self.embeddings
    
    def get_filter_options(self):
        """Get available filter options for the UI"""
        # Get top manufacturers by product count
        manufacturer_counts = [(name, len(ids)) for name, ids in self.filter_indexes['manufacturers'].items()]
        manufacturer_counts.sort(key=lambda x: x[1], reverse=True)
        
        # Get category counts
        category_counts = [(name, len(ids)) for name, ids in self.filter_indexes['categories'].items()]
        category_counts.sort(key=lambda x: x[1], reverse=True)
        
        return {
            'categories': [{'name': name, 'count': count} for name, count in category_counts],
            'manufacturers': [{'name': name, 'count': count} for name, count in manufacturer_counts[:50]],  # Top 50
            'certifications': sorted(list(self.filter_indexes['certifications']))
        }
    
    def get_product_by_id(self, product_id):
        """Get a product by ID"""
        for product in self.products:
            if product['id'] == product_id:
                return product
        return None
    
    def get_products_by_ids(self, product_ids):
        """Get multiple products by IDs"""
        id_set = set(product_ids)
        return [p for p in self.products if p['id'] in id_set]
    
    def get_statistics(self):
        """Get product database statistics"""
        total_products = len(self.products)
        
        # Count products with sustainability data
        with_certifications = sum(1 for p in self.products if p.get('certifications'))
        with_carbon_data = sum(1 for p in self.products if p.get('net_carbon_emissions'))
        with_recycled_content = sum(1 for p in self.products if p.get('recycled_content_percentage'))
        
        # Get price range info
        prices = []
        for p in self.products:
            price_str = p.get('price_adjustment_structure') or p.get('price_per_unit')
            if price_str:
                prices.append(price_str)
        
        return {
            'total_products': total_products,
            'total_categories': len(self.filter_indexes['categories']),
            'total_manufacturers': len(self.filter_indexes['manufacturers']),
            'sustainability_stats': {
                'with_certifications': with_certifications,
                'with_carbon_data': with_carbon_data,
                'with_recycled_content': with_recycled_content
            },
            'top_categories': [(name, len(ids)) for name, ids in 
                             sorted(self.filter_indexes['categories'].items(), 
                                   key=lambda x: len(x[1]), reverse=True)[:10]],
            'top_manufacturers': [(name, len(ids)) for name, ids in 
                                sorted(self.filter_indexes['manufacturers'].items(), 
                                      key=lambda x: len(x[1]), reverse=True)[:10]]
        }

