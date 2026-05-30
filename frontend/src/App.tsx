import React from 'react';
import { AppProvider } from './context/AppContext';
import { DashboardWrapper } from './components/DashboardWrapper';

function App() {
  return (
    <AppProvider>
      <DashboardWrapper />
    </AppProvider>
  );
}

export default App;
