// Search functionality for AI Product Search

// State management
const state = {
    filters: {
        categories: [],
        manufacturers: [],
        has_certifications: false,
        has_carbon_data: false
    },
    allManufacturers: [],
    currentResults: [],
    pagination: {
        page: 1,
        per_page: 50,
        total: 0,
        total_pages: 0
    }
};

// DOM elements
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const resultsGrid = document.getElementById('resultsGrid');
const resultsInfo = document.getElementById('resultsInfo');
const resultCount = document.getElementById('resultCount');
const searchQuery = document.getElementById('searchQuery');
const loadingState = document.getElementById('loadingState');
const emptyState = document.getElementById('emptyState');
const clearFiltersBtn = document.getElementById('clearFilters');
const productModal = document.getElementById('productModal');
const closeModal = document.getElementById('closeModal');
const modalContent = document.getElementById('modalContent');
const statsBtn = document.getElementById('statsBtn');
const statsModal = document.getElementById('statsModal');
const closeStatsModal = document.getElementById('closeStatsModal');
const statsContent = document.getElementById('statsContent');

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadFilters();
    setupEventListeners();
    loadInitialProducts();  // Load products on page load
});

// Setup event listeners
function setupEventListeners() {
    searchBtn.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') performSearch();
    });

    clearFiltersBtn.addEventListener('click', clearFilters);
    
    // Example queries
    document.querySelectorAll('.example-query').forEach(btn => {
        btn.addEventListener('click', () => {
            searchInput.value = btn.textContent.trim();
            performSearch();
        });
    });

    // Modal close
    closeModal.addEventListener('click', () => {
        productModal.classList.add('hidden');
    });
    productModal.addEventListener('click', (e) => {
        if (e.target === productModal) {
            productModal.classList.add('hidden');
        }
    });

    // Stats modal
    statsBtn.addEventListener('click', loadStats);
    closeStatsModal.addEventListener('click', () => {
        statsModal.classList.add('hidden');
    });

    // Manufacturer search
    const manufacturerSearch = document.getElementById('manufacturerSearch');
    if (manufacturerSearch) {
        manufacturerSearch.addEventListener('input', filterManufacturers);
    }

    // Sustainability filters
    document.getElementById('filterCertifications').addEventListener('change', (e) => {
        state.filters.has_certifications = e.target.checked;
        applyFilters();  // Automatically update results
    });
    document.getElementById('filterCarbonData').addEventListener('change', (e) => {
        state.filters.has_carbon_data = e.target.checked;
        applyFilters();  // Automatically update results
    });
}

// Load filter options from API
async function loadFilters() {
    try {
        const response = await fetch('/api/filters');
        const data = await response.json();

        // Load categories
        const categoryFilters = document.getElementById('categoryFilters');
        categoryFilters.innerHTML = '';
        data.categories.slice(0, 15).forEach(cat => {
            const label = document.createElement('label');
            label.className = 'flex items-center text-sm cursor-pointer hover:bg-gray-50 p-1 rounded';
            label.innerHTML = `
                <input type="checkbox" class="category-filter mr-2" value="${cat.name}">
                <span class="flex-1">${cat.name}</span>
                <span class="text-gray-400 text-xs">${cat.count}</span>
            `;
            categoryFilters.appendChild(label);
        });

        // Load manufacturers
        state.allManufacturers = data.manufacturers;
        renderManufacturers(data.manufacturers.slice(0, 20));

        // Add change listeners
        document.querySelectorAll('.category-filter').forEach(checkbox => {
            checkbox.addEventListener('change', updateCategoryFilters);
        });

    } catch (error) {
        console.error('Failed to load filters:', error);
    }
}

function renderManufacturers(manufacturers) {
    const manufacturerFilters = document.getElementById('manufacturerFilters');
    manufacturerFilters.innerHTML = '';
    
    manufacturers.forEach(mfr => {
        const label = document.createElement('label');
        label.className = 'flex items-center text-sm cursor-pointer hover:bg-gray-50 p-1 rounded';
        label.innerHTML = `
            <input type="checkbox" class="manufacturer-filter mr-2" value="${mfr.name}">
            <span class="flex-1 truncate" title="${mfr.name}">${mfr.name}</span>
            <span class="text-gray-400 text-xs">${mfr.count}</span>
        `;
        manufacturerFilters.appendChild(label);
    });

    // Add change listeners
    document.querySelectorAll('.manufacturer-filter').forEach(checkbox => {
        checkbox.addEventListener('change', updateManufacturerFilters);
    });
}

function filterManufacturers(e) {
    const query = e.target.value.toLowerCase();
    const filtered = state.allManufacturers.filter(m => 
        m.name.toLowerCase().includes(query)
    ).slice(0, 20);
    renderManufacturers(filtered);
}

function updateCategoryFilters() {
    state.filters.categories = Array.from(
        document.querySelectorAll('.category-filter:checked')
    ).map(cb => cb.value);
    applyFilters();  // Automatically update results when filter changes
}

function updateManufacturerFilters() {
    state.filters.manufacturers = Array.from(
        document.querySelectorAll('.manufacturer-filter:checked')
    ).map(cb => cb.value);
    applyFilters();  // Automatically update results when filter changes
}

function clearFilters() {
    state.filters = {
        categories: [],
        manufacturers: [],
        has_certifications: false,
        has_carbon_data: false
    };
    document.querySelectorAll('.category-filter, .manufacturer-filter').forEach(cb => {
        cb.checked = false;
    });
    document.getElementById('filterCertifications').checked = false;
    document.getElementById('filterCarbonData').checked = false;
    applyFilters();  // Refresh products after clearing filters
}

// Load initial products on page load
async function loadInitialProducts() {
    state.pagination.page = 1;
    loadingState.classList.remove('hidden');
    emptyState.classList.add('hidden');
    resultsInfo.classList.add('hidden');
    resultsGrid.innerHTML = '';

    try {
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: '',  // Empty query = show all products
                filters: state.filters,
                use_llm_refinement: false,  // No LLM for initial load
                page: state.pagination.page,
                per_page: state.pagination.per_page
            })
        });

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        state.currentResults = data.results;
        state.pagination.total = data.total;
        state.pagination.total_pages = data.total_pages;
        state.pagination.page = data.page;
        
        displayResults(data.results, 'All Products');

    } catch (error) {
        console.error('Failed to load products:', error);
        resultsGrid.innerHTML = `
            <div class="col-span-full text-center py-8">
                <p class="text-red-600">Failed to load products: ${error.message}</p>
            </div>
        `;
    } finally {
        loadingState.classList.add('hidden');
    }
}

// Apply current filters to products
async function applyFilters() {
    state.pagination.page = 1;  // Reset to page 1 when filters change
    const query = searchInput.value.trim();
    
    // If there's a search query, use the search function
    if (query) {
        performSearch();
        return;
    }
    
    // Otherwise, just filter products
    loadingState.classList.remove('hidden');
    resultsGrid.innerHTML = '';

    try {
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: '',  // Empty query = filter only
                filters: state.filters,
                use_llm_refinement: false,
                page: state.pagination.page,
                per_page: state.pagination.per_page
            })
        });

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        state.currentResults = data.results;
        state.pagination.total = data.total;
        state.pagination.total_pages = data.total_pages;
        state.pagination.page = data.page;
        
        // Show info about active filters
        const activeFilters = [];
        if (state.filters.categories.length > 0) activeFilters.push(`${state.filters.categories.length} categories`);
        if (state.filters.manufacturers.length > 0) activeFilters.push(`${state.filters.manufacturers.length} manufacturers`);
        if (state.filters.has_certifications) activeFilters.push('with certifications');
        if (state.filters.has_carbon_data) activeFilters.push('with carbon data');
        
        const filterText = activeFilters.length > 0 ? ` (filtered by ${activeFilters.join(', ')})` : '';
        displayResults(data.results, `All Products${filterText}`);

    } catch (error) {
        console.error('Filter error:', error);
        resultsGrid.innerHTML = `
            <div class="col-span-full text-center py-8">
                <p class="text-red-600">Filter failed: ${error.message}</p>
            </div>
        `;
    } finally {
        loadingState.classList.add('hidden');
    }
}

// Change page
async function changePage(newPage) {
    if (newPage < 1 || newPage > state.pagination.total_pages) return;
    
    state.pagination.page = newPage;
    window.scrollTo({ top: 0, behavior: 'smooth' });
    
    const query = searchInput.value.trim();
    if (query) {
        performSearch();
    } else {
        loadingState.classList.remove('hidden');
        resultsGrid.innerHTML = '';

        try {
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: '',
                    filters: state.filters,
                    use_llm_refinement: false,
                    page: state.pagination.page,
                    per_page: state.pagination.per_page
                })
            });

            const data = await response.json();
            if (data.error) throw new Error(data.error);

            state.currentResults = data.results;
            state.pagination.total = data.total;
            state.pagination.total_pages = data.total_pages;
            state.pagination.page = data.page;

            const activeFilters = [];
            if (state.filters.categories.length > 0) activeFilters.push(`${state.filters.categories.length} categories`);
            if (state.filters.manufacturers.length > 0) activeFilters.push(`${state.filters.manufacturers.length} manufacturers`);
            if (state.filters.has_certifications) activeFilters.push('with certifications');
            if (state.filters.has_carbon_data) activeFilters.push('with carbon data');
            
            const filterText = activeFilters.length > 0 ? ` (filtered by ${activeFilters.join(', ')})` : '';
            displayResults(data.results, `All Products${filterText}`);

        } catch (error) {
            console.error('Page change error:', error);
            resultsGrid.innerHTML = `
                <div class="col-span-full text-center py-8">
                    <p class="text-red-600">Failed to load page: ${error.message}</p>
                </div>
            `;
        } finally {
            loadingState.classList.add('hidden');
        }
    }
}

// Perform search
async function performSearch() {
    const query = searchInput.value.trim();
    
    // If no query, just apply filters
    if (!query) {
        applyFilters();
        return;
    }

    // Update UI state
    loadingState.classList.remove('hidden');
    emptyState.classList.add('hidden');
    resultsInfo.classList.add('hidden');
    resultsGrid.innerHTML = '';

    try {
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                filters: state.filters,
                use_llm_refinement: true,
                page: state.pagination.page,
                per_page: state.pagination.per_page
            })
        });

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        state.currentResults = data.results;
        state.pagination.total = data.total;
        state.pagination.total_pages = data.total_pages;
        state.pagination.page = data.page;
        
        displayResults(data.results, query);

    } catch (error) {
        console.error('Search error:', error);
        resultsGrid.innerHTML = `
            <div class="col-span-full text-center py-8">
                <p class="text-red-600">Search failed: ${error.message}</p>
            </div>
        `;
    } finally {
        loadingState.classList.add('hidden');
    }
}

// Display search results
function displayResults(results, query) {
    resultsGrid.innerHTML = '';

    if (results.length === 0) {
        resultsGrid.innerHTML = `
            <div class="col-span-full text-center py-12">
                <p class="text-gray-600">No products found matching your search.</p>
                <p class="text-sm text-gray-500 mt-2">Try adjusting your filters or search terms.</p>
            </div>
        `;
        resultsInfo.classList.add('hidden');
        return;
    }

    // Show results info with pagination
    resultsInfo.classList.remove('hidden');
    const startIdx = (state.pagination.page - 1) * state.pagination.per_page + 1;
    const endIdx = Math.min(startIdx + results.length - 1, state.pagination.total);
    resultCount.textContent = `${startIdx}-${endIdx} of ${state.pagination.total}`;
    searchQuery.textContent = query;

    // Render product cards
    results.forEach(product => {
        const card = createProductCard(product);
        resultsGrid.appendChild(card);
    });

    // Add pagination controls if more than one page
    if (state.pagination.total_pages > 1) {
        const paginationDiv = document.createElement('div');
        paginationDiv.className = 'col-span-full flex justify-center items-center gap-2 mt-6';
        paginationDiv.innerHTML = renderPaginationControls();
        resultsGrid.appendChild(paginationDiv);
    }
}

// Render pagination controls
function renderPaginationControls() {
    const currentPage = state.pagination.page;
    const totalPages = state.pagination.total_pages;
    
    let html = '';
    
    // Previous button
    html += `
        <button onclick="changePage(${currentPage - 1})" 
                ${currentPage === 1 ? 'disabled' : ''}
                class="px-4 py-2 border rounded-lg ${currentPage === 1 ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-100'}">
            ← Previous
        </button>
    `;
    
    // Page numbers
    const maxButtons = 7;
    let startPage = Math.max(1, currentPage - Math.floor(maxButtons / 2));
    let endPage = Math.min(totalPages, startPage + maxButtons - 1);
    
    if (endPage - startPage < maxButtons - 1) {
        startPage = Math.max(1, endPage - maxButtons + 1);
    }
    
    if (startPage > 1) {
        html += `<button onclick="changePage(1)" class="px-3 py-2 border rounded-lg hover:bg-gray-100">1</button>`;
        if (startPage > 2) html += `<span class="px-2">...</span>`;
    }
    
    for (let i = startPage; i <= endPage; i++) {
        html += `
            <button onclick="changePage(${i})" 
                    class="px-3 py-2 border rounded-lg ${i === currentPage ? 'bg-blue-600 text-white' : 'hover:bg-gray-100'}">
                ${i}
            </button>
        `;
    }
    
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) html += `<span class="px-2">...</span>`;
        html += `<button onclick="changePage(${totalPages})" class="px-3 py-2 border rounded-lg hover:bg-gray-100">${totalPages}</button>`;
    }
    
    // Next button
    html += `
        <button onclick="changePage(${currentPage + 1})" 
                ${currentPage === totalPages ? 'disabled' : ''}
                class="px-4 py-2 border rounded-lg ${currentPage === totalPages ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-100'}">
            Next →
        </button>
    `;
    
    return html;
}

// Create product card element
function createProductCard(product) {
    const card = document.createElement('div');
    card.className = 'product-card bg-white rounded-lg shadow-sm overflow-hidden cursor-pointer';
    card.onclick = () => showProductDetail(product.id);

    const categories = product.product_categories || [];
    const categoryNames = categories.map(c => c.category_name).filter(Boolean);
    
    const certCount = (product.certifications || []).length;
    const hasImage = product.image && !product.image.includes('undefined');

    const llmExplanation = product.llm_explanation ? `
        <div class="mt-2 pt-2 border-t border-gray-100">
            <p class="text-sm text-blue-700"><strong>Why recommended:</strong> ${product.llm_explanation}</p>
        </div>
    ` : '';

    card.innerHTML = `
        ${hasImage ? `
            <div class="h-48 bg-gray-200 overflow-hidden">
                <img src="/${product.image}" alt="${product.product_name}" 
                     class="w-full h-full object-cover"
                     onerror="this.parentElement.innerHTML='<div class=\\'flex items-center justify-center h-full text-gray-400\\'>No Image</div>'">
            </div>
        ` : `
            <div class="h-48 bg-gradient-to-br from-blue-50 to-blue-100 flex items-center justify-center">
                <svg class="w-16 h-16 text-blue-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                          d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"></path>
                </svg>
            </div>
        `}
        <div class="p-4">
            <div class="text-xs text-blue-600 font-medium mb-1">${product.manufacturer_name || 'Unknown'}</div>
            <h3 class="font-semibold text-gray-800 mb-2 line-clamp-2">${product.product_name || 'Untitled Product'}</h3>
            <p class="text-sm text-gray-600 mb-3 line-clamp-2">${product.product_description || 'No description available'}</p>
            
            ${categoryNames.length > 0 ? `
                <div class="flex flex-wrap gap-1 mb-2">
                    ${categoryNames.slice(0, 2).map(cat => 
                        `<span class="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">${cat}</span>`
                    ).join('')}
                </div>
            ` : ''}
            
            <div class="flex items-center justify-between text-xs text-gray-500 mt-3">
                <span>${certCount > 0 ? `✓ ${certCount} Certification${certCount > 1 ? 's' : ''}` : 'No certifications'}</span>
                ${product.similarity_score ? `<span>Match: ${(product.similarity_score * 100).toFixed(0)}%</span>` : ''}
            </div>

            ${llmExplanation}
        </div>
    `;

    return card;
}

// Show product detail modal
async function showProductDetail(productId) {
    modalContent.innerHTML = '<p class="text-center py-8">Loading product details...</p>';
    productModal.classList.remove('hidden');

    try {
        const response = await fetch(`/api/products/${productId}`);
        const product = await response.json();

        if (product.error) {
            throw new Error(product.error);
        }

        modalContent.innerHTML = renderProductDetail(product);

    } catch (error) {
        modalContent.innerHTML = `<p class="text-red-600">Failed to load product details: ${error.message}</p>`;
    }
}

// Render product detail view
function renderProductDetail(product) {
    const categories = (product.product_categories || []).map(c => c.category_name).filter(Boolean);
    const certifications = product.certifications || [];
    const hasImage = product.image && !product.image.includes('undefined');

    return `
        <div class="space-y-6">
            <div>
                <div class="text-sm text-blue-600 font-medium mb-1">${product.manufacturer_name || 'Unknown Manufacturer'}</div>
                <h2 class="text-2xl font-bold text-gray-900">${product.product_name || 'Untitled Product'}</h2>
                ${product.product_code ? `<p class="text-sm text-gray-500 mt-1">Code: ${product.product_code}</p>` : ''}
            </div>

            ${hasImage ? `
                <div class="rounded-lg overflow-hidden bg-gray-100">
                    <img src="/${product.image}" alt="${product.product_name}" class="w-full h-64 object-cover">
                </div>
            ` : ''}

            <div>
                <h3 class="font-semibold text-gray-800 mb-2">Description</h3>
                <p class="text-gray-600">${product.product_description || 'No description available'}</p>
            </div>

            ${categories.length > 0 ? `
                <div>
                    <h3 class="font-semibold text-gray-800 mb-2">Categories</h3>
                    <div class="flex flex-wrap gap-2">
                        ${categories.map(cat => `<span class="bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm">${cat}</span>`).join('')}
                    </div>
                </div>
            ` : ''}

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                ${product.standard_dimensions ? `
                    <div>
                        <h4 class="font-medium text-gray-700">Dimensions</h4>
                        <p class="text-gray-600">${product.standard_dimensions}</p>
                    </div>
                ` : ''}
                ${product.expected_lifespan_years ? `
                    <div>
                        <h4 class="font-medium text-gray-700">Expected Lifespan</h4>
                        <p class="text-gray-600">${product.expected_lifespan_years} years</p>
                    </div>
                ` : ''}
                ${product.manufacturers_warranty_years ? `
                    <div>
                        <h4 class="font-medium text-gray-700">Warranty</h4>
                        <p class="text-gray-600">${product.manufacturers_warranty_years} years</p>
                    </div>
                ` : ''}
                ${product.lead_time ? `
                    <div>
                        <h4 class="font-medium text-gray-700">Lead Time</h4>
                        <p class="text-gray-600">${product.lead_time}</p>
                    </div>
                ` : ''}
                ${product.price_adjustment_structure || product.price_per_unit ? `
                    <div>
                        <h4 class="font-medium text-gray-700">Pricing</h4>
                        <p class="text-gray-600">${product.price_adjustment_structure || product.price_per_unit}</p>
                    </div>
                ` : ''}
            </div>

            ${certifications.length > 0 ? `
                <div>
                    <h3 class="font-semibold text-gray-800 mb-2">Certifications</h3>
                    <div class="space-y-2">
                        ${certifications.map(cert => `
                            <div class="border border-gray-200 rounded p-3">
                                <div class="font-medium text-gray-800">${cert.certification}</div>
                                ${cert.link ? `<a href="${cert.link}" target="_blank" class="text-sm text-blue-600 hover:underline">View Certificate →</a>` : ''}
                            </div>
                        `).join('')}
                    </div>
                </div>
            ` : ''}

            ${product.net_carbon_emissions || product.recycled_content_percentage || product.recyclable_percentage ? `
                <div>
                    <h3 class="font-semibold text-gray-800 mb-2">Sustainability</h3>
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                        ${product.net_carbon_emissions ? `
                            <div class="bg-green-50 p-3 rounded">
                                <div class="text-sm text-gray-600">Carbon Emissions</div>
                                <div class="text-lg font-semibold text-gray-900">${product.net_carbon_emissions} kg CO₂e</div>
                            </div>
                        ` : ''}
                        ${product.recycled_content_percentage ? `
                            <div class="bg-blue-50 p-3 rounded">
                                <div class="text-sm text-gray-600">Recycled Content</div>
                                <div class="text-lg font-semibold text-gray-900">${product.recycled_content_percentage}%</div>
                            </div>
                        ` : ''}
                        ${product.recyclable_percentage ? `
                            <div class="bg-purple-50 p-3 rounded">
                                <div class="text-sm text-gray-600">Recyclable</div>
                                <div class="text-lg font-semibold text-gray-900">${product.recyclable_percentage}%</div>
                            </div>
                        ` : ''}
                    </div>
                </div>
            ` : ''}
        </div>
    `;
}

// Load statistics
async function loadStats() {
    statsModal.classList.remove('hidden');
    statsContent.innerHTML = '<p class="text-center py-8">Loading statistics...</p>';

    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();

        if (stats.error) {
            throw new Error(stats.error);
        }

        statsContent.innerHTML = `
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                <div class="stat-card text-white p-6 rounded-lg">
                    <div class="text-3xl font-bold">${stats.total_products}</div>
                    <div class="text-sm opacity-90">Total Products</div>
                </div>
                <div class="stat-card-2 text-white p-6 rounded-lg">
                    <div class="text-3xl font-bold">${stats.total_categories}</div>
                    <div class="text-sm opacity-90">Categories</div>
                </div>
                <div class="stat-card-3 text-white p-6 rounded-lg">
                    <div class="text-3xl font-bold">${stats.total_manufacturers}</div>
                    <div class="text-sm opacity-90">Manufacturers</div>
                </div>
                <div class="stat-card-4 text-white p-6 rounded-lg">
                    <div class="text-3xl font-bold">${stats.sustainability_stats.with_certifications}</div>
                    <div class="text-sm opacity-90">With Certifications</div>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                    <h3 class="font-semibold text-gray-800 mb-3">Top Categories</h3>
                    <div class="space-y-2">
                        ${stats.top_categories.slice(0, 8).map(([name, count]) => `
                            <div class="flex justify-between items-center text-sm">
                                <span class="text-gray-700">${name}</span>
                                <span class="font-medium text-blue-600">${count}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
                <div>
                    <h3 class="font-semibold text-gray-800 mb-3">Top Manufacturers</h3>
                    <div class="space-y-2">
                        ${stats.top_manufacturers.slice(0, 8).map(([name, count]) => `
                            <div class="flex justify-between items-center text-sm">
                                <span class="text-gray-700">${name}</span>
                                <span class="font-medium text-blue-600">${count}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        `;

    } catch (error) {
        statsContent.innerHTML = `<p class="text-red-600">Failed to load statistics: ${error.message}</p>`;
    }
}

