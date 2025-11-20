"""Hybrid search engine combining semantic search and LLM reasoning"""
import numpy as np
import json
from openai import OpenAI
from config import Config
from prompts import get_search_refinement_prompt, get_chat_response_prompt


class SearchEngine:
    """Hybrid search using embeddings + LLM refinement"""
    
    def __init__(self, indexer, api_key=None):
        self.indexer = indexer
        self.api_key = api_key or Config.OPENAI_API_KEY
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None
    
    def cosine_similarity(self, a, b):
        """Calculate cosine similarity between vectors"""
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    
    def semantic_search(self, query, top_k=None, filters=None):
        """
        Perform semantic search using embeddings.
        
        Args:
            query: Search query string
            top_k: Number of results to return (default from config)
            filters: Dict of filters to apply (categories, manufacturers, etc.)
        
        Returns:
            List of products with similarity scores
        """
        top_k = top_k or Config.TOP_K_SEMANTIC
        
        if not self.client:
            raise ValueError("OpenAI client not initialized")
        
        # Generate query embedding
        response = self.client.embeddings.create(
            model=Config.EMBEDDING_MODEL,
            input=[query]
        )
        query_embedding = np.array(response.data[0].embedding)
        
        # Calculate similarities
        similarities = []
        for i, product_embedding in enumerate(self.indexer.embeddings):
            similarity = self.cosine_similarity(query_embedding, product_embedding)
            similarities.append((i, similarity))
        
        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        # Apply filters if provided
        filtered_products = []
        for idx, similarity in similarities:
            if similarity < Config.SIMILARITY_THRESHOLD:
                continue
            
            product = self.indexer.products[idx]
            
            # Apply filters
            if filters:
                if not self._passes_filters(product, filters):
                    continue
            
            product_copy = product.copy()
            product_copy['similarity_score'] = float(similarity)
            filtered_products.append(product_copy)
            
            if len(filtered_products) >= top_k:
                break
        
        return filtered_products
    
    def _passes_filters(self, product, filters):
        """Check if product passes all filters"""
        # Category filter
        if filters.get('categories'):
            product_cats = [c.get('category_name') for c in product.get('product_categories', [])]
            if not any(cat in filters['categories'] for cat in product_cats):
                return False
        
        # Manufacturer filter
        if filters.get('manufacturers'):
            if product.get('manufacturer_name') not in filters['manufacturers']:
                return False
        
        # Certification filter
        if filters.get('certifications'):
            product_certs = [c.get('certification') for c in product.get('certifications', [])]
            if not any(cert in filters['certifications'] for cert in product_certs):
                return False
        
        # Sustainability filter
        if filters.get('has_certifications') and not product.get('certifications'):
            return False
        
        if filters.get('has_carbon_data') and not product.get('net_carbon_emissions'):
            return False
        
        return True
    
    def llm_refine_results(self, query, products):
        """
        Use LLM to refine and rank search results.
        
        Args:
            query: Original search query
            products: List of products from semantic search
        
        Returns:
            Refined and ranked list of products with explanations
        """
        if not products:
            return []
        
        if not self.client:
            return products[:Config.TOP_K_FINAL]
        
        try:
            # Get refinement prompt
            prompt = get_search_refinement_prompt(query, products)
            
            # Call LLM
            response = self.client.chat.completions.create(
                model=Config.CHAT_MODEL,
                messages=[
                    {"role": "system", "content": "You are a product recommendation expert for building materials."},
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=2000
            )
            
            # Parse JSON response
            content = response.choices[0].message.content.strip()
            
            # Extract JSON if wrapped in markdown
            if content.startswith("```"):
                parts = content.split("```")
                if len(parts) >= 2:
                    content = parts[1]
                    if content.startswith("json"):
                        content = content[4:]
                    content = content.strip()
            
            recommendations = json.loads(content)
            
            # Map recommendations back to products
            product_map = {p['id']: p for p in products}
            refined_products = []
            
            for rec in recommendations:
                product_id = rec['product_id']
                if product_id in product_map:
                    product = product_map[product_id].copy()
                    product['llm_rank'] = rec.get('rank', 0)
                    product['llm_relevance'] = rec.get('relevance_score', 0)
                    product['llm_explanation'] = rec.get('explanation', '')
                    refined_products.append(product)
                else:
                    print(f"Warning: LLM returned product_id {product_id} which is not in the semantic search results")
            
            if not refined_products:
                print(f"Warning: LLM refinement produced no valid products. Product IDs in semantic results: {list(product_map.keys())[:5]}")
                print(f"LLM returned recommendations: {[r.get('product_id') for r in recommendations[:5]]}")
                return products[:Config.TOP_K_FINAL]
            
            return refined_products[:Config.TOP_K_FINAL]
        
        except json.JSONDecodeError as e:
            print(f"LLM refinement JSON parse error: {e}")
            print(f"LLM response content: {content[:200]}...")
            # Fallback to semantic search results
            return products[:Config.TOP_K_FINAL]
        except Exception as e:
            print(f"LLM refinement failed: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to semantic search results
            return products[:Config.TOP_K_FINAL]
    
    def search(self, query, filters=None, use_llm_refinement=True):
        """
        Main search function combining semantic search and LLM refinement.
        
        Args:
            query: Search query string
            filters: Optional filters dict
            use_llm_refinement: Whether to use LLM for result refinement
        
        Returns:
            List of recommended products
        """
        # Step 1: Semantic search
        semantic_results = self.semantic_search(query, filters=filters)
        
        if not semantic_results:
            return []
        
        # Step 2: LLM refinement (optional)
        if use_llm_refinement and self.client:
            refined_results = self.llm_refine_results(query, semantic_results)
            return refined_results
        
        return semantic_results[:Config.TOP_K_FINAL]
    
    def chat(self, query, chat_history=None, max_products=10):
        """
        Conversational product recommendations.
        
        Args:
            query: User's question
            chat_history: Previous messages
            max_products: Max products to consider
        
        Returns:
            AI response text
        """
        if not self.client:
            return "AI chat is not available. Please configure OpenAI API key."
        
        try:
            # Get relevant products from semantic search
            products = self.semantic_search(query, top_k=max_products)
            
            # Extract product IDs from chat history for follow-up questions
            previously_mentioned_ids = set()
            if chat_history:
                import re
                for msg in chat_history[-6:]:  # Last 3 exchanges
                    if msg.get('role') == 'assistant':
                        content = msg.get('content', '')
                        # Extract product IDs like (ID: 1221)
                        ids = re.findall(r'\(ID:\s*(\d+)\)', content)
                        previously_mentioned_ids.update(int(id_str) for id_str in ids)
            
            # If this looks like a follow-up question and we have previous IDs, include those products
            follow_up_keywords = ['pricing', 'price', 'cost', 'ballpark', 'tell me more', 'compare', 
                                  'difference', 'which one', 'suggestions', 'recommendations', 
                                  'you mentioned', 'you suggested', 'above', 'these', 'those']
            is_follow_up = any(keyword in query.lower() for keyword in follow_up_keywords)
            
            if is_follow_up and previously_mentioned_ids:
                # Get the previously mentioned products
                previous_products = self.indexer.get_products_by_ids(list(previously_mentioned_ids))
                
                # Merge with semantic search results, prioritizing previous products
                product_ids_in_results = {p['id'] for p in products}
                for prev_prod in previous_products:
                    if prev_prod['id'] not in product_ids_in_results:
                        products.insert(0, prev_prod)  # Add to beginning
                
                # Keep only max_products
                products = products[:max_products]
            
            if not products:
                return "I couldn't find any products matching your query. Could you try rephrasing or being more specific?"
            
            # Generate chat prompt
            prompt = get_chat_response_prompt(query, products, chat_history)
            
            # Get LLM response
            messages = [
                {"role": "system", "content": "You are a helpful product expert for architectural and building materials."}
            ]
            
            if chat_history:
                messages.extend(chat_history[-6:])  # Last 3 exchanges
            
            messages.append({"role": "user", "content": prompt})
            
            response = self.client.chat.completions.create(
                model=Config.CHAT_MODEL,
                messages=messages,
                max_completion_tokens=4000
            )
            
            return response.choices[0].message.content
        
        except Exception as e:
            print(f"Chat error: {e}")
            return f"I encountered an error processing your request. Please try again."
    
    def stream_chat(self, query, chat_history=None, max_products=10):
        """
        Streaming conversational product recommendations.
        
        Args:
            query: User's question
            chat_history: Previous messages
            max_products: Max products to consider
        
        Yields:
            Text chunks from streaming response
        """
        if not self.client:
            yield "AI chat is not available. Please configure OpenAI API key."
            return
        
        try:
            # Get relevant products from semantic search
            products = self.semantic_search(query, top_k=max_products)
            
            # Extract product IDs from chat history for follow-up questions
            previously_mentioned_ids = set()
            if chat_history:
                import re
                for msg in chat_history[-6:]:  # Last 3 exchanges
                    if msg.get('role') == 'assistant':
                        content = msg.get('content', '')
                        # Extract product IDs like (ID: 1221)
                        ids = re.findall(r'\(ID:\s*(\d+)\)', content)
                        previously_mentioned_ids.update(int(id_str) for id_str in ids)
            
            # If this looks like a follow-up question and we have previous IDs, include those products
            follow_up_keywords = ['pricing', 'price', 'cost', 'ballpark', 'tell me more', 'compare', 
                                  'difference', 'which one', 'suggestions', 'recommendations', 
                                  'you mentioned', 'you suggested', 'above', 'these', 'those']
            is_follow_up = any(keyword in query.lower() for keyword in follow_up_keywords)
            
            if is_follow_up and previously_mentioned_ids:
                # Get the previously mentioned products
                previous_products = self.indexer.get_products_by_ids(list(previously_mentioned_ids))
                
                # Merge with semantic search results, prioritizing previous products
                product_ids_in_results = {p['id'] for p in products}
                for prev_prod in previous_products:
                    if prev_prod['id'] not in product_ids_in_results:
                        products.insert(0, prev_prod)  # Add to beginning
                
                # Keep only max_products
                products = products[:max_products]
            
            if not products:
                yield "I couldn't find any products matching your query. Could you try rephrasing or being more specific?"
                return
            
            # Generate chat prompt
            prompt = get_chat_response_prompt(query, products, chat_history)
            
            # Get LLM response with streaming
            messages = [
                {"role": "system", "content": "You are a helpful product expert for architectural and building materials."}
            ]
            
            if chat_history:
                messages.extend(chat_history[-6:])
            
            messages.append({"role": "user", "content": prompt})
            
            stream = self.client.chat.completions.create(
                model=Config.CHAT_MODEL,
                messages=messages,
                max_completion_tokens=2000,
                stream=True
            )
            
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        
        except Exception as e:
            print(f"Stream chat error: {e}")
            yield f"I encountered an error processing your request. Please try again."

