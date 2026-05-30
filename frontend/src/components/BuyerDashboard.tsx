import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Search, ShoppingCart, MapPin, Loader2, X, CreditCard, CheckCircle, Sparkles, AlertCircle } from 'lucide-react';
import { ProductCard } from './ProductCard';
import { useAppContext } from '../context/AppContext';
import { useRazorpayCheckout } from '../hooks/useRazorpayCheckout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ApiProduct {
  id: number;
  product_catalog_id: number;
  name: string;
  description?: string | null;
  category?: string | null;
  price: number;
  stock_count: number;
  image_url: string;
  shop: {
    id: number;
    shop_name: string;
    latitude: number;
    longitude: number;
    distance_km: number;
  };
}

interface AgentResult {
  ingredient: string;
  status: 'found' | 'not_found';
  message?: string;
  id?: number;
  product_catalog_id?: number;
  name?: string;
  description?: string | null;
  category?: string | null;
  price?: number;
  stock_count?: number;
  image_url?: string;
  shop?: {
    id: number;
    shop_name: string;
    latitude: number;
    longitude: number;
    distance_km: number;
  };
}

interface AgentResponse {
  prompt: string;
  ingredients_extracted: string[];
  results: AgentResult[];
  found_count: number;
  not_found_count: number;
}

interface FormattedProduct {
  id: string;
  productCatalogId: string;
  shopId: string;
  name: string;
  category?: string | null;
  price: number;
  stockCount: number;
  image: string;
  distance?: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TEST_LOCATIONS = [
  { label: 'MNIT Campus',   latitude: 26.8631, longitude: 75.8106 },
  { label: 'Malviya Nagar', latitude: 26.8546, longitude: 75.8174 },
  { label: 'Raja Park',     latitude: 26.8982, longitude: 75.8239 },
] as const;

const CATEGORIES = [
  'Fruits & Vegetables', 'Dairy & Eggs', 'Bakery',
  'Beverages', 'Snacks', 'Household', 'Personal Care',
] as const;

const API_BASE = 'http://127.0.0.1:8000';
const SEARCH_DEBOUNCE_MS = 400;

// ---------------------------------------------------------------------------
// Fallback image helper
// ---------------------------------------------------------------------------

function getFallbackImage(name: string): string {
  const n = name.toLowerCase();
  if (n.includes('milk'))                               return 'https://images.unsplash.com/photo-1550583724-b2692b85b150?w=500';
  if (n.includes('banana'))                             return 'https://images.unsplash.com/photo-1571501712814-24e537d0c345?w=500';
  if (n.includes('bread') || n.includes('biscuit'))     return 'https://images.unsplash.com/photo-1589367920969-abce87c29eb1?w=500';
  if (n.includes('egg'))                                return 'https://images.unsplash.com/photo-1587486913049-53fc88980cfc?w=500';
  if (n.includes('tomato') || n.includes('vegetable'))  return 'https://images.unsplash.com/photo-1561136594-7f68413baa99?w=500';
  if (n.includes('detergent') || n.includes('soap'))    return 'https://images.unsplash.com/photo-1584820927500-1c05d762e106?w=500';
  if (n.includes('atta') || n.includes('flour'))        return 'https://images.unsplash.com/photo-1509440159596-0249088772ff?w=500';
  if (n.includes('noodle'))                             return 'https://images.unsplash.com/photo-1612929633738-8fe44f7ec841?w=500';
  return 'https://images.unsplash.com/photo-1542838132-92c53300491e?w=500';
}

function agentResultToProduct(r: AgentResult): FormattedProduct | null {
  if (r.status !== 'found' || !r.id || !r.shop) return null;
  return {
    id:              String(r.id),
    productCatalogId: String(r.product_catalog_id),
    shopId:          String(r.shop.id),
    name:            r.name!,
    category:        r.category ?? null,
    price:           r.price!,
    stockCount:      r.stock_count!,
    image:           r.image_url || getFallbackImage(r.name!),
    distance:        `${r.shop.distance_km} km`,
  };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const BuyerDashboard: React.FC = () => {
  const {
    location, setLocation, locationError,
    cart, token,
    incrementQuantity, decrementQuantity, removeFromCart,
    clearCart, bumpInventoryVersion,
  } = useAppContext();

  // --- tab ---
  const [activeTab, setActiveTab] = useState<'browse' | 'agent'>('browse');

  // --- browse state ---
  const [searchInput, setSearchInput]       = useState('');
  const [searchQuery, setSearchQuery]       = useState('');
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [products, setProducts]             = useState<FormattedProduct[]>([]);
  const [loading, setLoading]               = useState(false);
  const [error, setError]                   = useState<string | null>(null);
  const [activeLocation, setActiveLocation] = useState<string | null>(null);

  // --- agent state ---
  const [agentInput, setAgentInput]         = useState('');
  const [agentLoading, setAgentLoading]     = useState(false);
  const [agentError, setAgentError]         = useState<string | null>(null);
  const [agentResponse, setAgentResponse]   = useState<AgentResponse | null>(null);

  // --- checkout state ---
  const [checkoutState, setCheckoutState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [checkoutMsg,   setCheckoutMsg]   = useState<string | null>(null);
  const { startCheckout } = useRazorpayCheckout();
  const isProcessing = checkoutState === 'loading';

  const errorResetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scheduleErrorReset = useCallback(() => {
    if (errorResetTimer.current) clearTimeout(errorResetTimer.current);
    errorResetTimer.current = setTimeout(() => {
      setCheckoutState('idle');
      setCheckoutMsg(null);
    }, 5000);
  }, []);

  // --- debounce ---
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleSearchChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setSearchInput(value);
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => setSearchQuery(value.trim()), SEARCH_DEBOUNCE_MS);
  }, []);

  const clearSearch = useCallback(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    setSearchInput('');
    setSearchQuery('');
  }, []);

  // --- fetch products (browse tab) ---
  useEffect(() => {
    if (!location || activeTab !== 'browse') return;
    const params = new URLSearchParams({
      buyer_latitude:  String(location.latitude),
      buyer_longitude: String(location.longitude),
      limit: '40',
    });
    if (searchQuery)    params.set('q',        searchQuery);
    if (activeCategory) params.set('category', activeCategory);

    setLoading(true);
    setError(null);

    fetch(`${API_BASE}/api/products/search?${params.toString()}`)
      .then(res => { if (!res.ok) throw new Error(`Server error ${res.status}`); return res.json() as Promise<ApiProduct[]>; })
      .then(data => setProducts(data.map(p => ({
        id: String(p.id), productCatalogId: String(p.product_catalog_id),
        shopId: String(p.shop.id), name: p.name, category: p.category ?? null,
        price: p.price, stockCount: p.stock_count,
        image: p.image_url || getFallbackImage(p.name),
        distance: `${p.shop.distance_km} km`,
      }))))
      .catch(err => { console.error(err); setError(err.message); })
      .finally(() => setLoading(false));
  }, [location, searchQuery, activeCategory, activeTab]);

  // --- agent submit ---
  const handleAgentSubmit = useCallback(async () => {
    if (!agentInput.trim() || !location || !token) return;
    setAgentLoading(true);
    setAgentError(null);
    setAgentResponse(null);
    try {
      const res = await fetch(`${API_BASE}/api/agent/recipe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          prompt:    agentInput.trim(),
          latitude:  location.latitude,
          longitude: location.longitude,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? `Error ${res.status}`);
      setAgentResponse(data as AgentResponse);
    } catch (err: unknown) {
      setAgentError(err instanceof Error ? err.message : 'Agent request failed');
    } finally {
      setAgentLoading(false);
    }
  }, [agentInput, location, token]);

  // --- handlers ---
  const handleLocationSelect = (loc: typeof TEST_LOCATIONS[number]) => {
    setActiveLocation(loc.label);
    setLocation({ latitude: loc.latitude, longitude: loc.longitude });
  };

  const handleCheckout = () => {
    startCheckout({
      cart, token, clearCart, bumpInventoryVersion,
      onLoadingStart: () => { setCheckoutState('loading'); setCheckoutMsg(null); },
      onLoadingEnd:   () => { setCheckoutState(prev => prev === 'loading' ? 'idle' : prev); },
      onSuccess: (paymentId) => { setCheckoutState('success'); setCheckoutMsg(`Payment confirmed! ID: ${paymentId}`); },
      onFailure: (reason) => {
        if (reason === 'Payment cancelled.') { setCheckoutState('idle'); setCheckoutMsg(null); }
        else { setCheckoutState('error'); setCheckoutMsg('Payment was unsuccessful. Please try again.'); scheduleErrorReset(); }
      },
    });
  };

  const cartItemCount = cart.reduce((sum, i) => sum + i.quantity, 0);
  const cartTotal     = cart.reduce((sum, i) => sum + i.price * i.quantity, 0);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col md:flex-row">
      <main className="flex-1 p-4 md:p-8 overflow-y-auto">

        {/* Header */}
        <header className="mb-6 flex flex-col gap-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl md:text-3xl font-bold text-gray-900">Discover Nearby</h1>
              <p className="text-gray-500 mt-1 flex items-center gap-1 text-sm">
                <MapPin className="w-4 h-4" />
                {location ? `Showing results near ${activeLocation ?? 'your location'}` : 'Locating…'}
              </p>
            </div>
          </div>

          {/* Test location buttons */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-gray-500">Test Locations:</span>
            {TEST_LOCATIONS.map(loc => (
              <button key={loc.label} onClick={() => handleLocationSelect(loc)}
                className={`text-xs px-3 py-1.5 rounded-md border transition-colors ${activeLocation === loc.label ? 'bg-primary-600 text-white border-primary-600' : 'bg-white border-gray-200 hover:bg-gray-50 text-gray-700'}`}>
                📍 {loc.label}
              </button>
            ))}
          </div>

          {/* Tab switcher */}
          <div className="flex gap-1 bg-gray-100 p-1 rounded-xl w-fit">
            <button onClick={() => setActiveTab('browse')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === 'browse' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>
              <Search className="w-4 h-4" /> Browse
            </button>
            <button onClick={() => setActiveTab('agent')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === 'agent' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>
              <Sparkles className="w-4 h-4 text-indigo-500" /> AI Smart Search
            </button>
          </div>
        </header>

        {/* ── Browse Tab ── */}
        {activeTab === 'browse' && (
          <>
            <div className="flex flex-col gap-3 mb-6">
              {/* Search input */}
              <div className="relative w-full md:w-96">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Search className="h-5 w-5 text-gray-400" />
                </div>
                <input type="text" value={searchInput} onChange={handleSearchChange}
                  className="block w-full pl-10 pr-9 py-3 border border-gray-200 rounded-xl bg-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-primary-500 focus:border-primary-500 sm:text-sm shadow-sm"
                  placeholder="Search for groceries, essentials…" aria-label="Search products" />
                {searchInput && (
                  <button onClick={clearSearch} className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600" aria-label="Clear search">
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>
              {/* Category pills */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-gray-500">Category:</span>
                {CATEGORIES.map(cat => (
                  <button key={cat} onClick={() => setActiveCategory(prev => prev === cat ? null : cat)}
                    className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${activeCategory === cat ? 'bg-primary-600 text-white border-primary-600' : 'bg-white border-gray-200 hover:bg-gray-50 text-gray-700'}`}>
                    {cat}
                  </button>
                ))}
                {activeCategory && (
                  <button onClick={() => setActiveCategory(null)} className="text-xs text-red-500 hover:underline flex items-center gap-1">
                    <X className="w-3 h-3" /> Clear
                  </button>
                )}
              </div>
              {(searchQuery || activeCategory) && (
                <p className="text-xs text-gray-500">
                  {[searchQuery && `Search: "${searchQuery}"`, activeCategory && `Category: ${activeCategory}`].filter(Boolean).join(' · ')}
                  {' '}— {products.length} result{products.length !== 1 ? 's' : ''}
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4 md:gap-6">
              {loading ? (
                <div className="col-span-full flex justify-center py-12"><Loader2 className="w-8 h-8 text-primary-500 animate-spin" /></div>
              ) : error || locationError ? (
                <div className="col-span-full text-center py-12 text-red-500">{error || locationError}</div>
              ) : !location ? (
                <div className="col-span-full text-center py-12 text-gray-500">Select a test location above to see nearby products.</div>
              ) : products.length === 0 ? (
                <div className="col-span-full text-center py-12 text-gray-500">
                  No products found{searchQuery ? ` for "${searchQuery}"` : ''}{activeCategory ? ` in ${activeCategory}` : ''}.
                  {(searchQuery || activeCategory) && (
                    <button onClick={() => { clearSearch(); setActiveCategory(null); }} className="block mx-auto mt-2 text-primary-600 hover:underline text-sm">Clear filters</button>
                  )}
                </div>
              ) : (
                products.map(p => <ProductCard key={p.id} product={p} disabled={isProcessing} />)
              )}
            </div>
          </>
        )}

        {/* ── AI Agent Tab ── */}
        {activeTab === 'agent' && (
          <div className="flex flex-col gap-6">
            {/* Prompt box */}
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
              <div className="flex items-center gap-2 mb-3">
                <Sparkles className="w-5 h-5 text-indigo-500" />
                <h2 className="font-semibold text-gray-900">AI Smart Search</h2>
              </div>
              <p className="text-sm text-gray-500 mb-4">
                Describe what you need in plain language. Try: <span className="italic">"I have a cold"</span>, <span className="italic">"make pizza for 4"</span>, <span className="italic">"I feel tired"</span>
              </p>
              <div className="flex gap-3">
                <input
                  type="text"
                  value={agentInput}
                  onChange={e => setAgentInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleAgentSubmit()}
                  placeholder="e.g. I have a cold and sore throat…"
                  className="flex-1 px-4 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
                  disabled={agentLoading}
                />
                <button
                  onClick={handleAgentSubmit}
                  disabled={agentLoading || !agentInput.trim() || !location}
                  className="flex items-center gap-2 px-5 py-3 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {agentLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                  {agentLoading ? 'Thinking…' : 'Search'}
                </button>
              </div>
              {!location && <p className="text-xs text-amber-600 mt-2">⚠ Select a test location first</p>}
            </div>

            {/* Error */}
            {agentError && (
              <div className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
                <AlertCircle className="w-4 h-4 shrink-0" />
                {agentError}
              </div>
            )}

            {/* Results */}
            {agentResponse && (
              <div className="flex flex-col gap-4">
                {/* Summary bar */}
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div>
                    <p className="text-sm font-medium text-gray-700">
                      Results for: <span className="text-indigo-600">"{agentResponse.prompt}"</span>
                    </p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      Extracted {agentResponse.ingredients_extracted.length} items ·{' '}
                      <span className="text-green-600">{agentResponse.found_count} found</span>
                      {agentResponse.not_found_count > 0 && (
                        <span className="text-red-500"> · {agentResponse.not_found_count} not found</span>
                      )}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {agentResponse.ingredients_extracted.map(ing => (
                      <span key={ing} className="text-xs bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full border border-indigo-100">{ing}</span>
                    ))}
                  </div>
                </div>

                {/* Not-found items */}
                {agentResponse.results.filter(r => r.status === 'not_found').length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {agentResponse.results.filter(r => r.status === 'not_found').map(r => (
                      <span key={r.ingredient} className="text-xs bg-red-50 text-red-600 px-3 py-1 rounded-full border border-red-100">
                        ✗ {r.ingredient} — not in stock
                      </span>
                    ))}
                  </div>
                )}

                {/* Found products grid */}
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4 md:gap-6">
                  {agentResponse.results
                    .filter(r => r.status === 'found')
                    .map(r => {
                      const p = agentResultToProduct(r);
                      if (!p) return null;
                      return (
                        <div key={r.ingredient} className="flex flex-col gap-1">
                          <span className="text-xs text-indigo-600 font-medium px-1 truncate">→ {r.ingredient}</span>
                          <ProductCard product={p} disabled={isProcessing} />
                        </div>
                      );
                    })}
                </div>
              </div>
            )}
          </div>
        )}

      </main>

      {/* ── Cart sidebar ── */}
      <aside className="hidden lg:flex flex-col w-80 bg-white border-l border-gray-200 p-6 shadow-sm z-10 h-screen sticky top-0">
        <div className="flex items-center gap-2 mb-6">
          <ShoppingCart className="w-6 h-6 text-primary-600" />
          <h2 className="text-xl font-bold text-gray-900">Your Cart</h2>
          {cartItemCount > 0 && (
            <span className="ml-auto bg-primary-100 text-primary-800 text-xs font-bold px-2 py-1 rounded-full">{cartItemCount}</span>
          )}
        </div>

        {cart.length === 0 ? (
          <div className="flex flex-col items-center justify-center flex-1 text-center">
            <div className="w-16 h-16 bg-gray-50 rounded-full flex items-center justify-center mb-4">
              <ShoppingCart className="w-8 h-8 text-gray-300" />
            </div>
            <p className="text-gray-500">Your cart is empty</p>
            <p className="text-sm text-gray-400 mt-1">Add items to get started</p>
          </div>
        ) : (
          <div className="flex-1 flex flex-col overflow-hidden">
            {isProcessing && (
              <div className="flex items-center gap-2 mb-3 px-3 py-2 bg-indigo-50 border border-indigo-200 rounded-lg text-xs text-indigo-700">
                <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
                Payment in progress — cart is locked
              </div>
            )}
            <div className="flex-1 overflow-y-auto pr-2 space-y-4">
              {cart.map(item => (
                <div key={item.id} className="flex gap-3 border-b border-gray-100 pb-4">
                  <img src={item.image} alt={item.name} className="w-16 h-16 object-cover rounded-md bg-gray-100" />
                  <div className="flex-1">
                    <h4 className="text-sm font-semibold text-gray-900 line-clamp-1">{item.name}</h4>
                    <div className="flex justify-between items-center mt-2">
                      <span className="text-primary-600 font-bold">₹{(item.price * item.quantity).toFixed(2)}</span>
                      <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded-md">₹{item.price.toFixed(2)} each</span>
                    </div>
                    <div className="flex items-center justify-between mt-3">
                      <div className="flex items-center gap-2">
                        <button type="button" onClick={() => decrementQuantity(item.id)} disabled={isProcessing}
                          className="w-8 h-8 rounded-md border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">-</button>
                        <span className="min-w-6 text-center text-sm font-semibold text-gray-900">{item.quantity}</span>
                        <button type="button" onClick={() => incrementQuantity(item.id)} disabled={isProcessing}
                          className="w-8 h-8 rounded-md border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">+</button>
                      </div>
                      <button type="button" onClick={() => removeFromCart(item.id)} disabled={isProcessing}
                        className="text-xs font-semibold text-red-600 hover:text-red-700 hover:underline disabled:opacity-40 disabled:cursor-not-allowed">Remove</button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="pt-4 border-t border-gray-200 mt-4">
              <div className="flex justify-between font-bold text-lg mb-4">
                <span>Total</span><span>₹{cartTotal.toFixed(2)}</span>
              </div>
              {checkoutState === 'success' && checkoutMsg && (
                <div className="flex items-center gap-2 mb-3 p-2 bg-green-50 rounded-lg text-xs text-green-700">
                  <CheckCircle className="w-4 h-4 shrink-0" />{checkoutMsg}
                </div>
              )}
              {checkoutState === 'error' && checkoutMsg && (
                <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded-lg">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-xs text-red-700 font-medium">{checkoutMsg}</p>
                    <button onClick={() => { setCheckoutState('idle'); setCheckoutMsg(null); }} className="text-red-400 hover:text-red-600 shrink-0"><X className="w-3.5 h-3.5" /></button>
                  </div>
                  <p className="text-xs text-red-500 mt-1">Resetting automatically…</p>
                </div>
              )}
              <button onClick={handleCheckout} disabled={checkoutState === 'loading' || cart.length === 0}
                className="w-full btn-primary flex items-center justify-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed">
                {checkoutState === 'loading'
                  ? <><Loader2 className="w-4 h-4 animate-spin" /> Processing…</>
                  : <><CreditCard className="w-4 h-4" /> Pay ₹{cartTotal.toFixed(2)}</>}
              </button>
            </div>
          </div>
        )}
      </aside>

      {/* Mobile cart FAB */}
      <button className="lg:hidden fixed bottom-6 right-6 bg-primary-600 text-white p-4 rounded-full shadow-lg hover:bg-primary-700 transition-colors z-20"
        aria-label={`Cart — ${cartItemCount} item${cartItemCount !== 1 ? 's' : ''}`}>
        <div className="relative">
          <ShoppingCart className="w-6 h-6" />
          {cartItemCount > 0 && (
            <span className="absolute -top-2 -right-2 bg-red-500 text-white text-xs font-bold w-5 h-5 flex items-center justify-center rounded-full">{cartItemCount}</span>
          )}
        </div>
      </button>
    </div>
  );
};
