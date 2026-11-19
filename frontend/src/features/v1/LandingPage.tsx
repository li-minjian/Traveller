import { Link, useNavigate } from 'react-router';
import { MessageComposer } from './MessageComposer';
import { SignIn } from './SignIn';
import { exampleRequest } from './demo';
import './v1.css';

export function LandingPage() {
  const navigate = useNavigate();

  function start(message: string) {
    void navigate('/chat', { state: { message } });
  }

  return (
    <div className="v1 v1-home">
      <a href="#main-content" className="skip-link">Skip to content</a>
      <nav className="v1-home-nav" aria-label="Main navigation">
        <Link to="/" className="v1-wordmark" aria-label="Traveller home">traveller.</Link>
        <div className="v1-nav-actions">
          <Link to="/chat">Workspace</Link>
          <SignIn />
        </div>
      </nav>
      <main id="main-content" tabIndex={-1} className="v1-home-content">
        <section className="v1-hero" aria-labelledby="landing-title">
          <p className="v1-eyebrow">Travel, made simple</p>
          <h1 id="landing-title">Where to next?</h1>
          <p className="v1-intro">Every journey begins with an idea.<br />Tell us yours.</p>
          <MessageComposer onSend={start} landing />
          <div className="v1-examples">
            <span>Try an example</span>
            <button type="button" onClick={() => start(exampleRequest)}>Berlin → Lisbon</button>
            <Link to="/chat">Start from scratch</Link>
          </div>
        </section>
      </main>
      <footer className="v1-home-footer">
        <strong>Traveller · Project VS</strong>
        <span>Simple planning. Nothing extra.</span>
        <span>Concept only — no live bookings</span>
      </footer>
    </div>
  );
}
