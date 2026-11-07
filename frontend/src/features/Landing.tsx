import {
  ArrowRight,
  CalendarDays,
  Compass,
  MapPin,
  Mountain,
  Search,
  Sparkles,
  Sun,
} from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { useTravel } from '../app/TravelContext';
import { Eyebrow } from '../components/ui';
import { inspiration } from '../mocks/fixtures';

const icons = {
  sun: Sun,
  calendar: CalendarDays,
  mountain: Mountain,
  sparkles: Sparkles,
};

export function Landing() {
  const { submit, service } = useTravel();
  const navigate = useNavigate();
  const [prompt, setPrompt] = useState('');
  const featured = service.destinations().filter((item) => item.editorialImage);

  function start(text: string) {
    if (submit(text)) navigate('/discover');
  }

  return (
    <div className="landing page">
      <div className="index-line">
        <span>
          <i /> 01 / Travel discovery
        </span>
        <span>Wohin travel journal</span>
        <span>Europe · Demo edition</span>
      </div>
      <section className="landing-hero">
        <img src="/images/hero.webp" alt="" fetchPriority="high" />
        <div className="hero-top">
          <div>
            <Eyebrow>The travel journal · 01</Eyebrow>
            <span className="hero-wordmark">Wohin</span>
          </div>
          <Link to="/search" className="hero-link">
            <Search size={15} /> Travel search <ArrowRight size={15} />
          </Link>
        </div>
        <div className="hero-content">
          <span className="hero-kicker">
            <Sparkles size={14} /> A little curiosity goes a long way
          </span>
          <h1>Where will you go?</h1>
          <p>Explore the world, at your own pace.</p>
          <form
            className="hero-form"
            onSubmit={(event) => {
              event.preventDefault();
              start(prompt);
            }}
          >
            <Compass size={22} aria-hidden="true" />
            <input
              aria-label="Your travel wish"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              maxLength={600}
              placeholder="Where would you like to go?"
            />
            <button className="button button-primary" type="submit">
              Ask AI <ArrowRight size={17} />
            </button>
          </form>
          <div className="inspiration">
            <span>Try</span>
            {inspiration.map(({ label, prompt, icon }) => {
              const Icon = icons[icon];
              return (
                <button
                  key={label}
                  className="hero-chip"
                  type="button"
                  onClick={() => start(prompt)}
                >
                  <Icon size={13} />
                  {label}
                </button>
              );
            })}
          </div>
        </div>
        <div className="hero-caption">
          <span>Field notes / 01</span>
          <span>Start with a place. Or with a feeling.</span>
        </div>
      </section>
      <section className="editorial-intro">
        <div>
          <Eyebrow>02 / A way to travel</Eyebrow>
          <h2>Considered journeys.</h2>
        </div>
        <div>
          <p>
            Some trips start with a place. Others start with a long weekend, a
            small budget, or the wish to be somewhere quiet.
          </p>
          <div className="intro-facts">
            <Link to="/search">
              <Search size={18} />
              <strong>Know where you’re going?</strong>
              <span>Search by destination, dates and budget.</span>
              <ArrowRight size={16} />
            </Link>
            <Link to="/discover">
              <Sparkles size={18} />
              <strong>Open to ideas?</strong>
              <span>Describe a trip and explore the possibilities.</span>
              <ArrowRight size={16} />
            </Link>
          </div>
        </div>
      </section>
      <section className="featured-section">
        <div className="section-heading">
          <div>
            <Eyebrow>03 / From the travel journal</Eyebrow>
            <h2>Places to get you started</h2>
          </div>
          <Link className="text-link" to="/search">
            Browse destinations <ArrowRight size={16} />
          </Link>
        </div>
        <div className="featured-grid">
          {featured.map((place) => (
            <article key={place.id} className="editorial-card">
              <div className="editorial-image">
                <img src={place.editorialImage} alt="" loading="lazy" />
                <span>
                  <MapPin size={12} /> {place.tags[0]}
                </span>
              </div>
              <div className="editorial-content">
                <Eyebrow>{place.region}</Eyebrow>
                <h3>{place.name}</h3>
                <p>{place.description}</p>
                <Link className="text-link" to={`/destinations/${place.id}`}>
                  Discover the destination <ArrowRight size={16} />
                </Link>
              </div>
            </article>
          ))}
          <article className="editorial-invitation">
            <div>
              <Eyebrow>
                Wohin assistant <Sparkles size={17} />
              </Eyebrow>
              <h3>Still deciding where to go?</h3>
              <p>
                Start with a feeling, a date or a budget. Refine your criteria
                as you discover what matters.
              </p>
            </div>
            <Link className="button button-light" to="/discover">
              Open Ask AI <ArrowRight size={16} />
            </Link>
          </article>
        </div>
      </section>
    </div>
  );
}
