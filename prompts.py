"""AI prompt templates for product search and recommendations"""

def get_product_embedding_text(product):
    """
    Create a rich text representation of a product for embedding generation.
    Combines all relevant searchable features.
    """
    parts = []
    
    # Core identity
    if product.get('manufacturer_name'):
        parts.append(f"Manufacturer: {product['manufacturer_name']}")
    if product.get('product_name'):
        parts.append(f"Product: {product['product_name']}")
    if product.get('product_code'):
        parts.append(f"Code: {product['product_code']}")
    
    # Description
    if product.get('product_description'):
        parts.append(f"Description: {product['product_description']}")
    
    # Categories
    categories = product.get('product_categories', [])
    if categories:
        cat_names = [cat.get('category_name', '') for cat in categories if cat.get('category_name')]
        if cat_names:
            parts.append(f"Categories: {', '.join(cat_names)}")
    
    # Sustainability profile
    sustainability_parts = []
    
    certifications = product.get('certifications', [])
    if certifications:
        cert_names = [cert.get('certification', '') for cert in certifications if cert.get('certification')]
        if cert_names:
            sustainability_parts.append(f"Certifications: {', '.join(cert_names)}")
    
    if product.get('recycled_content_percentage'):
        sustainability_parts.append(f"Recycled content: {product['recycled_content_percentage']}%")
    if product.get('recyclable_percentage'):
        sustainability_parts.append(f"Recyclable: {product['recyclable_percentage']}%")
    if product.get('carbon_neutral'):
        sustainability_parts.append("Carbon neutral")
    if product.get('net_carbon_emissions'):
        sustainability_parts.append(f"Carbon emissions: {product['net_carbon_emissions']} kg CO2e")
    
    if sustainability_parts:
        parts.append("Sustainability: " + "; ".join(sustainability_parts))
    
    # Technical attributes
    tech_parts = []
    if product.get('standard_dimensions'):
        tech_parts.append(f"Dimensions: {product['standard_dimensions']}")
    if product.get('expected_lifespan_years'):
        tech_parts.append(f"Lifespan: {product['expected_lifespan_years']} years")
    if product.get('manufacturers_warranty_years'):
        tech_parts.append(f"Warranty: {product['manufacturers_warranty_years']} years")
    
    if tech_parts:
        parts.append("Technical: " + "; ".join(tech_parts))
    
    # Commercial info
    commercial_parts = []
    if product.get('price_adjustment_structure'):
        commercial_parts.append(f"Price: {product['price_adjustment_structure']}")
    elif product.get('price_per_unit'):
        commercial_parts.append(f"Price: {product['price_per_unit']}")
    if product.get('lead_time'):
        commercial_parts.append(f"Lead time: {product['lead_time']}")
    
    if commercial_parts:
        parts.append("Commercial: " + "; ".join(commercial_parts))
    
    # Safety & compliance
    safety_parts = []
    if product.get('volatile_organic_compounds'):
        safety_parts.append(f"VOC: {product['volatile_organic_compounds']}")
    if product.get('substances_of_concern') == 'No':
        safety_parts.append("No substances of concern")
    
    if safety_parts:
        parts.append("Safety: " + "; ".join(safety_parts))
    
    return " | ".join(parts)


def get_search_refinement_prompt(query, products):
    """
    Create prompt for LLM to refine and rank search results.
    
    Args:
        query: User's search query
        products: List of product dictionaries with similarity scores
    
    Returns:
        Prompt string for LLM
    """
    products_text = ""
    for i, prod in enumerate(products, 1):
        products_text += f"\n{i}. [Product ID: {prod.get('id')}] {prod.get('manufacturer_name', 'Unknown')} - {prod.get('product_name', 'Unknown')}\n"
        if prod.get('product_description'):
            products_text += f"   Description: {prod['product_description']}\n"
        
        # Add key distinguishing features
        categories = prod.get('product_categories', [])
        if categories:
            cat_names = [c.get('category_name', '') for c in categories if c.get('category_name')]
            if cat_names:
                products_text += f"   Categories: {', '.join(cat_names)}\n"
        
        # Sustainability highlights
        if prod.get('certifications'):
            cert_count = len(prod['certifications'])
            products_text += f"   Certifications: {cert_count} certification(s)\n"
        
        if prod.get('price_adjustment_structure'):
            products_text += f"   Price: {prod['price_adjustment_structure']}\n"
        
        products_text += f"   Similarity Score: {prod.get('similarity_score', 0):.3f}\n"
    
    prompt = f"""You are an expert product recommendation system for architectural and building materials. 

User Query: "{query}"

I've found {len(products)} potentially relevant products using semantic search. Your task is to:
1. Analyze which products best match the user's intent and requirements
2. Rank them by relevance (most relevant first)
3. Provide a brief explanation for each recommended product

Products found:
{products_text}

Respond with a JSON array of recommended products in this exact format:
[
  {{
    "product_id": <USE THE ACTUAL PRODUCT ID FROM [Product ID: X] ABOVE>,
    "rank": 1,
    "relevance_score": 0.95,
    "explanation": "Brief explanation of why this product matches the query"
  }},
  ...
]

IMPORTANT: Use the exact Product ID numbers shown in [Product ID: X] format above. Do not use sequential numbers.
Only include products that are actually relevant to the query. Return between 5-10 products maximum.
Respond ONLY with the JSON array, no other text."""

    return prompt


def get_chat_response_prompt(query, products, chat_history=None):
    """
    Create prompt for conversational product recommendations.
    
    Args:
        query: User's current question/message
        products: List of relevant product dictionaries
        chat_history: Previous conversation messages (optional)
    
    Returns:
        Prompt string for conversational LLM
    """
    history_text = ""
    if chat_history:
        for msg in chat_history[-6:]:  # Last 3 exchanges
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            history_text += f"\n{role.upper()}: {content}\n"
    
    products_summary = ""
    for i, prod in enumerate(products[:10], 1):
        products_summary += f"\n{i}. **{prod.get('manufacturer_name', 'Unknown')} - {prod.get('product_name', 'Unknown')}** (ID: {prod.get('id')})\n"
        if prod.get('product_description'):
            desc = prod['product_description'][:200] + "..." if len(prod.get('product_description', '')) > 200 else prod.get('product_description', '')
            products_summary += f"   {desc}\n"
        
        # Key features including pricing
        features = []
        categories = prod.get('product_categories', [])
        if categories and categories[0].get('category_name'):
            features.append(categories[0]['category_name'])
        
        # Add pricing information if available
        if prod.get('price_adjustment_structure'):
            features.append(f"Price: {prod['price_adjustment_structure']}")
        elif prod.get('price_per_unit'):
            features.append(f"Price: {prod['price_per_unit']}")
        
        if prod.get('certifications'):
            cert_names = [c.get('certification', '')[:30] for c in prod['certifications'][:2]]
            features.append(f"Certs: {', '.join(cert_names)}")
        
        if prod.get('expected_lifespan_years'):
            features.append(f"{prod['expected_lifespan_years']}yr lifespan")
        
        if prod.get('lead_time'):
            features.append(f"Lead time: {prod['lead_time']}")
        
        if features:
            products_summary += f"   {' | '.join(features)}\n"
    
    prompt = f"""You are a knowledgeable assistant helping architects and designers find building products and materials.

CONVERSATION HISTORY:
{history_text if history_text else 'None - this is the first message'}

CURRENT USER QUERY: {query}

PRODUCTS RELEVANT TO THIS QUERY:
{products_summary}

YOUR TASK:
- Read the conversation history carefully to understand the context
- If this is a follow-up question (like "what about pricing" or "tell me more"), refer back to products previously discussed
- Answer the user's current query in a helpful, conversational tone
- When recommending products, include 3-5 most relevant items with brief explanations
- Include pricing information when available or when asked
- Highlight key differentiators (sustainability, technical specs, price, certifications, etc.) based on what matters for the query
- For comparison questions, provide clear side-by-side insights
- If asked about products mentioned earlier, use those product IDs from the history and current product list
- Keep responses concise but informative (2-3 paragraphs max)
- Use bullet points for product recommendations with this format: • Manufacturer — Product Name (ID: X)

IMPORTANT: If the user asks a follow-up question about products you already recommended (e.g., pricing, more details, comparisons), use the conversation history to understand which products they're referring to, even if those exact products aren't in the current search results.

Respond naturally as a product expert would."""

    return prompt

