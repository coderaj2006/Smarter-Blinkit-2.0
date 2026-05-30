import React from 'react';
import { Plus } from 'lucide-react';
import { useAppContext } from '../context/AppContext';

interface Product {
  id: string; // SellerInventory.id
  productCatalogId?: string;
  shopId?: string;
  name: string;
  category?: string | null;
  price: number;
  stockCount?: number;
  image: string;
  distance?: string;
}

interface ProductCardProps {
  product: Product;
  /** When true, the Add to Cart button is disabled. Set during checkout. */
  disabled?: boolean;
}

export const ProductCard: React.FC<ProductCardProps> = ({ product, disabled = false }) => {
  const { addToCart } = useAppContext();

  const handleAddToCart = () => {
    if (disabled) return;
    addToCart({
      id:               product.id,
      productCatalogId: product.productCatalogId ?? '',
      shopId:           product.shopId ?? '',
      name:             product.name,
      category:         product.category,
      price:            product.price,
      image:            product.image,
    });
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden hover:shadow-md transition-shadow duration-300 group">
      <div className="relative aspect-square overflow-hidden bg-gray-100">
        <img
          src={product.image}
          alt={product.name}
          onError={(e) => {
            e.currentTarget.src = 'https://images.unsplash.com/photo-1542838132-92c53300491e?w=500';
          }}
          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
        />
        {product.distance && (
          <div className="absolute top-2 left-2 bg-white/90 backdrop-blur-sm px-2 py-1 rounded-md text-xs font-medium text-gray-700 shadow-sm">
            📍 {product.distance}
          </div>
        )}
      </div>
      <div className="p-4">
        <h3 className="font-semibold text-gray-900 mb-1 truncate">{product.name}</h3>
        {product.category && (
          <p className="text-xs text-gray-500 truncate">{product.category}</p>
        )}
        <div className="flex items-center justify-between mt-3">
          <span className="font-bold text-lg text-gray-900">₹{product.price.toFixed(2)}</span>
          <button
            onClick={handleAddToCart}
            disabled={disabled}
            className="bg-primary-50 text-primary-600 hover:bg-primary-600 hover:text-white p-2 rounded-lg transition-colors duration-200 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-primary-50 disabled:hover:text-primary-600"
            aria-label={disabled ? 'Checkout in progress' : 'Add to cart'}
          >
            <Plus className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
};
