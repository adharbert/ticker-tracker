import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import DashboardPage from './pages/DashboardPage';
import WatchlistPage from './pages/WatchlistPage';
import './App.css';

export default function App() {
  return (
    <BrowserRouter>
      <header style={styles.header}>
        <span style={styles.logo}>News Market Agent</span>
        <nav style={styles.nav}>
          <NavLink to="/"          style={navStyle} end>Dashboard</NavLink>
          <NavLink to="/watchlist" style={navStyle}>Watchlist</NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/"          element={<DashboardPage />} />
          <Route path="/watchlist" element={<WatchlistPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}

function navStyle({ isActive }) {
  return {
    color:         isActive ? '#93c5fd' : '#94a3b8',
    textDecoration: 'none',
    fontWeight:     isActive ? 600 : 400,
    padding:        '4px 10px',
  };
}

const styles = {
  header: {
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'space-between',
    padding:        '12px 24px',
    background:     '#0f172a',
    borderBottom:   '1px solid #1e293b',
  },
  logo: { color: '#f8fafc', fontWeight: 700, fontSize: 18 },
  nav:  { display: 'flex', gap: 4 },
};
