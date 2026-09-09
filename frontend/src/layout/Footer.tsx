import footerLogo from '../logo/footer-logo.svg';

export function Footer() {
  return <footer className="footer"><div className="footer-inner">
    <div className="footer-brand"><img className="footer-logo" src={footerLogo} alt="CoStrategix" /></div>
    <div>© 2026 CoStrategix. All rights reserved.</div>
  </div></footer>;
}
