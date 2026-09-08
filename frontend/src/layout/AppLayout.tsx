import {
  Navigate,
  Outlet,
  useLocation,
} from 'react-router-dom';

import { Header } from './Header';
import { Footer } from './Footer';
import { auth } from '../config/auth';

export function AppLayout() {
  const location = useLocation();

  if (!auth.isAuthenticated()) {
    return (
      <Navigate
        to="/login"
        replace
        state={{
          from: location.pathname,
        }}
      />
    );
  }

  return (
    <div className="app-shell">
      <Header />

      <main className="main">
        <Outlet />
      </main>

      <Footer />
    </div>
  );
}