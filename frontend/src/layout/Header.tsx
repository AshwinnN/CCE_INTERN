import { NavLink, useNavigate } from 'react-router-dom';

import footerLogo from '../logo/footer-logo.svg';
import { auth } from '../config/auth';
import '../styles/brand-logo.css';

const links = [['Domains', '/domains'], ['Sources', '/sources'], ['Knowledge', '/proposals'], ['Packages', '/packages'], ['Query', '/query']];

export function Header() {
  const navigate = useNavigate();

  return <header className="header"><div className="header-inner">
    <NavLink to="/domains" className="brand" aria-label="CoStrategix Context Engine home">
      <img className="brand-logo" src={footerLogo} alt="CoStrategix" />
      <span className="brand-divider" />
      <span className="brand-product">CCE</span>
    </NavLink>
    <nav className="nav">{links.map(([label, to]) => <NavLink key={to} to={to} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>{label}</NavLink>)}</nav>
    <div className="header-user"><span>CCE Admin</span><button onClick={() => { auth.logout(); navigate('/login'); }}>Sign out</button></div>
  </div></header>;
}
