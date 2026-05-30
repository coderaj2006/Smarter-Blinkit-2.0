import React, { useState, useEffect, useCallback } from 'react';
import { Package, TrendingUp, AlertCircle, Edit2, Check, X, Loader2, ScanLine } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { BarcodeScanner } from './BarcodeScanner';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface InventoryItem {
  inventory_id:       number;
  product_catalog_id: number;
  name:               string;
  category:           string | null;
  image_url:          string | null;
  price:              number;
  stock_quantity:     number;
  status:             'In Stock' | 'Low Stock' | 'Out of Stock';
}

interface ShopInfo {
  id:         number;
  shop_name:  string;
  latitude:   number;
  longitude:  number;
}

interface ApiResponse {
  shop:      ShopInfo | null;
  inventory: InventoryItem[];
  stats: {
    total_products:  number;
    low_stock_count: number;
  };
}

/** Fields the seller can edit inline. */
interface EditState {
  price:          string;
  stock_quantity: string;
}

const API_BASE = 'http://127.0.0.1:8000';

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const SellerDashboard: React.FC = () => {
  const { token, inventoryVersion } = useAppContext();

  // --- data state ---
  const [shop, setShop]           = useState<ShopInfo | null>(null);
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [stats, setStats]         = useState({ total_products: 0, low_stock_count: 0 });
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);

  // --- inline edit state: keyed by inventory_id ---
  const [editingId, setEditingId]   = useState<number | null>(null);
  const [editValues, setEditValues] = useState<EditState>({ price: '', stock_quantity: '' });
  const [saving, setSaving]         = useState(false);
  const [saveError, setSaveError]   = useState<string | null>(null);

  // --- barcode scanner ---
  const [scannerOpen, setScannerOpen] = useState(false);

  // -------------------------------------------------------------------------
  // Fetch inventory from live API
  // -------------------------------------------------------------------------
  const fetchInventory = useCallback(async () => {
    if (!token) {
      setError('Not authenticated. Please log in again.');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/seller/inventory`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Server error ${res.status}`);
      }

      const data: ApiResponse = await res.json();
      setShop(data.shop);
      setInventory(data.inventory);
      setStats(data.stats);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load inventory.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchInventory(); }, [fetchInventory]);

  // Re-fetch whenever a buyer completes a purchase — inventoryVersion is
  // bumped by the checkout hook immediately after /api/payments/verify succeeds.
  // Using a separate effect keeps the dependency clean and avoids re-running
  // the initial fetch twice on mount.
  useEffect(() => {
    if (inventoryVersion > 0) fetchInventory();
  // fetchInventory is stable (useCallback with [token] dep), so this is safe.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inventoryVersion]);

  // -------------------------------------------------------------------------
  // Inline edit handlers
  // -------------------------------------------------------------------------

  const startEdit = (item: InventoryItem) => {
    setEditingId(item.inventory_id);
    setEditValues({
      price:          String(item.price),
      stock_quantity: String(item.stock_quantity),
    });
    setSaveError(null);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setSaveError(null);
  };

  const commitEdit = async (inventoryId: number) => {
    const price    = parseFloat(editValues.price);
    const stock    = parseInt(editValues.stock_quantity, 10);

    if (isNaN(price) || price < 0) {
      setSaveError('Price must be a non-negative number.');
      return;
    }
    if (isNaN(stock) || stock < 0) {
      setSaveError('Stock must be a non-negative whole number.');
      return;
    }

    setSaving(true);
    setSaveError(null);

    try {
      const res = await fetch(`${API_BASE}/api/seller/inventory/${inventoryId}`, {
        method:  'PATCH',
        headers: {
          'Content-Type':  'application/json',
          Authorization:   `Bearer ${token}`,
        },
        body: JSON.stringify({ price, stock_quantity: stock }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Server error ${res.status}`);
      }

      const updated = await res.json();

      // Patch the local state directly — no full refetch needed
      setInventory(prev =>
        prev.map(item =>
          item.inventory_id === inventoryId
            ? {
                ...item,
                price:          updated.price,
                stock_quantity: updated.stock_quantity,
                status:         updated.status,
              }
            : item
        )
      );

      // Recompute stats locally
      setStats(prev => ({
        ...prev,
        low_stock_count: inventory.filter(
          i => (i.inventory_id === inventoryId ? stock : i.stock_quantity) <= 20
               && (i.inventory_id === inventoryId ? stock : i.stock_quantity) > 0
        ).length,
      }));

      setEditingId(null);
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : 'Save failed.');
    } finally {
      setSaving(false);
    }
  };

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------

  const statusBadge = (item: InventoryItem) => {
    const colours =
      item.stock_quantity > 20  ? 'bg-green-100 text-green-800'  :
      item.stock_quantity > 0   ? 'bg-yellow-100 text-yellow-800' :
                                  'bg-red-100 text-red-800';
    return (
      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colours}`}>
        {item.status} ({item.stock_quantity})
      </span>
    );
  };

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-primary-500 animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-500 font-medium">{error}</p>
          <button
            onClick={fetchInventory}
            className="mt-4 btn-primary"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-4 md:p-8">

      {/* Header */}
      <header className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-gray-900">Seller Dashboard</h1>
            <p className="text-gray-500 mt-1">
              {shop ? `Managing inventory for ${shop.shop_name}` : 'Manage your inventory and track performance'}
            </p>
          </div>
          <button
            onClick={() => setScannerOpen(true)}
            className="flex items-center gap-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-semibold px-4 py-2.5 rounded-xl transition-colors shadow-sm"
            aria-label="Open barcode scanner"
          >
            <ScanLine className="w-4 h-4" />
            Scan Barcode
          </button>
        </div>
      </header>

      {/* Barcode scanner modal */}
      {scannerOpen && (
        <BarcodeScanner
          onClose={() => {
            setScannerOpen(false);
            // Refresh inventory so updated stock counts are reflected
            fetchInventory();
          }}
        />
      )}

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex items-center gap-4">
          <div className="bg-blue-50 p-3 rounded-lg text-blue-600">
            <Package className="w-6 h-6" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500">Total Products</p>
            <p className="text-2xl font-bold text-gray-900">{stats.total_products}</p>
          </div>
        </div>

        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex items-center gap-4">
          <div className="bg-green-50 p-3 rounded-lg text-green-600">
            <TrendingUp className="w-6 h-6" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500">In-Stock Items</p>
            <p className="text-2xl font-bold text-gray-900">
              {inventory.filter(i => i.stock_quantity > 20).length}
            </p>
          </div>
        </div>

        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex items-center gap-4">
          <div className="bg-red-50 p-3 rounded-lg text-red-600">
            <AlertCircle className="w-6 h-6" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500">Low Stock Alerts</p>
            <p className="text-2xl font-bold text-gray-900">{stats.low_stock_count}</p>
          </div>
        </div>
      </div>

      {/* Inventory Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="p-6 border-b border-gray-100 flex justify-between items-center">
          <h2 className="text-lg font-semibold text-gray-900">Inventory Overview</h2>
        </div>

        {saveError && (
          <div className="mx-6 mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">
            {saveError}
          </div>
        )}

        {inventory.length === 0 ? (
          <div className="p-12 text-center text-gray-500">
            No inventory found for your shop. Add products to get started.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  <th className="p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Product</th>
                  <th className="p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Category</th>
                  <th className="p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Price (₹)</th>
                  <th className="p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Stock</th>
                  <th className="p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="p-4 text-xs font-semibold text-gray-500 uppercase tracking-wider text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {inventory.map(item => {
                  const isEditing = editingId === item.inventory_id;

                  return (
                    <tr key={item.inventory_id} className="hover:bg-gray-50/50 transition-colors">

                      {/* Product name */}
                      <td className="p-4 font-medium text-gray-900">{item.name}</td>

                      {/* Category */}
                      <td className="p-4 text-sm text-gray-500">{item.category ?? '—'}</td>

                      {/* Price — editable */}
                      <td className="p-4 text-sm text-gray-900">
                        {isEditing ? (
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={editValues.price}
                            onChange={e => setEditValues(v => ({ ...v, price: e.target.value }))}
                            className="w-24 border border-gray-300 rounded-md px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500"
                            aria-label="Edit price"
                          />
                        ) : (
                          `₹${item.price.toFixed(2)}`
                        )}
                      </td>

                      {/* Stock — editable */}
                      <td className="p-4 text-sm text-gray-900">
                        {isEditing ? (
                          <input
                            type="number"
                            min="0"
                            step="1"
                            value={editValues.stock_quantity}
                            onChange={e => setEditValues(v => ({ ...v, stock_quantity: e.target.value }))}
                            className="w-24 border border-gray-300 rounded-md px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500"
                            aria-label="Edit stock quantity"
                          />
                        ) : (
                          item.stock_quantity
                        )}
                      </td>

                      {/* Status badge */}
                      <td className="p-4">{statusBadge(item)}</td>

                      {/* Actions */}
                      <td className="p-4 text-right">
                        {isEditing ? (
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => commitEdit(item.inventory_id)}
                              disabled={saving}
                              className="flex items-center gap-1 text-xs font-semibold text-green-600 hover:text-green-700 disabled:opacity-50"
                              aria-label="Save changes"
                            >
                              {saving
                                ? <Loader2 className="w-4 h-4 animate-spin" />
                                : <Check className="w-4 h-4" />}
                              Save
                            </button>
                            <button
                              onClick={cancelEdit}
                              disabled={saving}
                              className="flex items-center gap-1 text-xs font-semibold text-gray-500 hover:text-gray-700 disabled:opacity-50"
                              aria-label="Cancel edit"
                            >
                              <X className="w-4 h-4" /> Cancel
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => startEdit(item)}
                            className="text-primary-600 hover:text-primary-800 font-medium text-sm flex items-center justify-end w-full gap-1"
                            aria-label={`Edit ${item.name}`}
                          >
                            <Edit2 className="w-4 h-4" /> Update
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
