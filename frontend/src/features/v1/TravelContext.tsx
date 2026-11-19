import { X } from 'lucide-react';
import { useRef } from 'react';
import type { FormEvent, Ref } from 'react';
import { displayDate } from './demo';
import type { TripContext } from './demo';

export function ContextContent({ trip }: { trip: TripContext }) {
  const entries = [
    ['From', trip.origin || 'Not set'],
    ['To', trip.destination || 'Not set'],
    ['Departure', displayDate(trip.date)],
    ['Travelers', `${trip.travelers} ${trip.travelers === 1 ? 'person' : 'people'}`],
  ];

  return (
    <>
      <p className="v1-context-intro">A simple overview of what we know so far.</p>
      <dl className="v1-context-list">
        {entries.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="v1-context-note">
        <strong>Keep it flexible.</strong>
        Your plans can change anytime. Update them here or tell the assistant.
      </p>
    </>
  );
}

export function ContextEditor({
  trip, dialogRef, onApply,
}: {
  trip: TripContext;
  dialogRef: Ref<HTMLDialogElement>;
  onApply: (trip: TripContext) => void;
}) {
  const form = useRef<HTMLFormElement>(null);

  function close() {
    form.current?.closest('dialog')?.close();
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    onApply({
      origin: String(fields.get('origin')).trim(),
      destination: String(fields.get('destination')).trim(),
      date: String(fields.get('date')),
      travelers: Number(fields.get('travelers')),
    });
    close();
  }

  return (
    <dialog
      ref={dialogRef}
      className="v1-dialog"
      aria-labelledby="v1-editor-title"
    >
      <header>
        <h2 id="v1-editor-title">Edit trip details</h2>
        <button className="v1-dialog-close" type="button" onClick={close} aria-label="Close dialog">
          <X size={16} aria-hidden="true" />
        </button>
      </header>
      <form ref={form} onSubmit={submit}>
        <label>From <input name="origin" defaultValue={trip.origin} placeholder="City" /></label>
        <label>To <input name="destination" defaultValue={trip.destination} placeholder="City" /></label>
        <label>Departure date <input name="date" type="date" max="9999-12-31" defaultValue={trip.date} /></label>
        <label>
          Travelers
          <input name="travelers" type="number" min="1" max="12" required defaultValue={trip.travelers} />
        </label>
        <div className="v1-dialog-actions">
          <button type="button" onClick={close}>Cancel</button>
          <button type="submit">Apply</button>
        </div>
      </form>
    </dialog>
  );
}
