import React from 'react';
import { BuyerDashboard } from './BuyerDashboard';
import { SellerDashboard } from './SellerDashboard';
import { Login } from './Login';
import { useAppContext } from '../context/AppContext';

export const DashboardWrapper: React.FC = () => {
  const { userRole, setUserRole, setToken } = useAppContext();

  if (!userRole) {
    return <Login />;
  }

  return (
    <div className="flex flex-col min-h-screen">
      {/* Global Header to toggle roles for demo purposes */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16 items-center">
            <div className="flex-shrink-0 flex items-center">
              <span className="text-xl font-black text-primary-600 tracking-tight">SmartMarket</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium bg-primary-50 text-primary-700 px-3 py-1.5 rounded-full capitalize">
                {userRole} Mode
              </span>
              <button
                onClick={() => {
                  setUserRole(null);
                  setToken(null);
                }}
                className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex-1">
        {userRole === 'buyer' ? <BuyerDashboard /> : <SellerDashboard />}
      </div>
    </div>
  );
};
