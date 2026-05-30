import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

export type UserRole = 'buyer' | 'seller' | null;

interface Location {
  latitude: number;
  longitude: number;
}

export interface CartItem {
  id: string;             // SellerInventory.id — primary cart key
  productCatalogId: string;
  shopId: string;
  name: string;
  category?: string | null;
  price: number;
  image: string;
  quantity: number;
}

interface AppContextType {
  userRole: UserRole;
  setUserRole: (role: UserRole) => void;
  token: string | null;
  setToken: (token: string | null) => void;
  location: Location | null;
  setLocation: (location: Location) => void;
  locationError: string | null;
  cart: CartItem[];
  addToCart: (product: Omit<CartItem, 'quantity'>) => void;
  clearCart: () => void;
  incrementQuantity: (productId: string) => void;
  decrementQuantity: (productId: string) => void;
  removeFromCart: (productId: string) => void;
  /** Incremented after a successful payment — SellerDashboard watches this to refetch. */
  inventoryVersion: number;
  bumpInventoryVersion: () => void;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [userRole, setUserRole] = useState<UserRole>(null);
  const [token, setToken] = useState<string | null>(null);
  const [location, setLocation] = useState<Location | null>(null);
  const [locationError, setLocationError] = useState<string | null>(null);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [inventoryVersion, setInventoryVersion] = useState(0);

  const bumpInventoryVersion = () => setInventoryVersion(v => v + 1);

  const addToCart = (product: Omit<CartItem, 'quantity'>) => {
    setCart((prev) => {
      const existing = prev.find((item) => item.id === product.id);
      if (existing) {
        return prev.map((item) =>
          item.id === product.id ? { ...item, quantity: item.quantity + 1 } : item
        );
      }
      return [...prev, { ...product, quantity: 1 }];
    });
  };

  const incrementQuantity = (productId: string) => {
    setCart((prev) =>
      prev.map((item) => (item.id === productId ? { ...item, quantity: item.quantity + 1 } : item))
    );
  };

  const decrementQuantity = (productId: string) => {
    setCart((prev) =>
      prev
        .map((item) =>
          item.id === productId ? { ...item, quantity: Math.max(0, item.quantity - 1) } : item
        )
        .filter((item) => item.quantity > 0)
    );
  };

  const removeFromCart = (productId: string) => {
    setCart((prev) => prev.filter((item) => item.id !== productId));
  };

  const clearCart = () => {
    setCart([]);
  };

  useEffect(() => {
    if ('geolocation' in navigator) {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          setLocation({
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
          });
        },
        (error) => {
          console.error("Error fetching location", error);
          setLocationError("Could not fetch location. Please enable location services.");
        }
      );
    } else {
      setLocationError("Geolocation is not supported by your browser.");
    }
  }, []);

  return (
    <AppContext.Provider
      value={{
        userRole,
        setUserRole,
        token,
        setToken,
        location,
        setLocation,
        locationError,
        cart,
        addToCart,
        clearCart,
        incrementQuantity,
        decrementQuantity,
        removeFromCart,
        inventoryVersion,
        bumpInventoryVersion,
      }}
    >
      {children}
    </AppContext.Provider>
  );
};

export const useAppContext = () => {
  const context = useContext(AppContext);
  if (context === undefined) {
    throw new Error('useAppContext must be used within an AppProvider');
  }
  return context;
};
