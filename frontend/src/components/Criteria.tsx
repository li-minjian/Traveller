import {
  CalendarDays,
  Euro,
  Compass,
  MapPin,
  Pencil,
  Plane,
  SlidersHorizontal,
  Users,
  X,
} from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { useTravel } from '../app/TravelContext';
import {
  budgetLabel,
  datesLabel,
  field,
  modeNames,
  modes,
} from '../domain/travel';
import type { Mode, Provenance, TravelIntent } from '../domain/travel';
import { DemoBadge, Eyebrow } from './ui';

export function CriteriaForm({
  onApply,
  label = 'Apply criteria',
  compact = false,
}: {
  onApply: (changes: Partial<TravelIntent>) => void;
  label?: string;
  compact?: boolean;
}) {
  const {
    session: { intent },
    service,
  } = useTravel();
  const prefix = useId();
  const [businessEnabled, setBusinessEnabled] = useState(
    Boolean(intent.business.value),
  );
  const [validation, setValidation] = useState('');
  const dates = intent.dates.value;
  const budget = intent.budget.value;
  const transport = intent.transport.value;
  const business = intent.business.value;

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const get = (key: string) => String(values.get(key) ?? '').trim();
    const start = get('start');
    const end = get('end');
    if (end && (!start || end < start)) {
      setValidation('Choose a departure date on or before the return date.');
      return;
    }
    const chosenModes = modes.filter((mode) => values.has(mode));
    const hardTransport = values.has('hardTransport');
    if (hardTransport && !chosenModes.length) {
      setValidation(
        'Choose at least one allowed transport mode or make transport a preference.',
      );
      return;
    }
    const meetingDate = get('meetingDate');
    if (
      businessEnabled &&
      meetingDate &&
      start &&
      (meetingDate < start || (end && meetingDate > end))
    ) {
      setValidation(
        'Choose a meeting date within the work portion of your trip.',
      );
      return;
    }
    const flexibility = Number(get('flexibility'));
    const season = start ? '' : get('season');
    const changes: Partial<TravelIntent> = {};
    function set<K extends keyof TravelIntent>(key: K, next: TravelIntent[K]) {
      const previous = intent[key];
      if (
        JSON.stringify(previous.value) !== JSON.stringify(next.value) ||
        (values.has('confirmInferences') && previous.provenance === 'inferred')
      )
        changes[key] = next;
    }

    set('destination', field(get('destination') || null));
    set('origin', field(get('origin') || null));
    set(
      'dates',
      field(
        start || flexibility || season
          ? { start, end, flexibility, season }
          : null,
        flexibility || season ? 'flexible' : 'confirmed',
      ),
    );
    set('duration', field(Number(get('duration')) || null));
    set('travelers', field(Number(get('travelers')) || 1));
    set(
      'budget',
      field(
        get('budget')
          ? {
              amount: Number(get('budget')),
              currency: 'EUR',
              hard: values.has('hardBudget'),
            }
          : null,
      ),
    );
    set(
      'transport',
      field(
        chosenModes.length ? { modes: chosenModes, hard: hardTransport } : null,
      ),
    );
    set('accommodation', field(get('accommodation') || null));
    const interests = [
      ...new Set(
        get('interests')
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
      ),
    ];
    set('interests', field(interests.length ? interests : null));
    set(
      'business',
      field(
        businessEnabled
          ? {
              purpose: get('purpose') || 'Meeting',
              meetingDate,
              meetingTime: get('meetingTime'),
              privateNights: Number(get('privateNights')),
              hardMeeting: values.has('hardMeeting'),
            }
          : null,
      ),
    );
    setValidation('');
    onApply(changes);
  }

  return (
    <form
      className={`criteria-form ${compact ? 'criteria-compact' : ''}`}
      onSubmit={apply}
    >
      <div className="form-grid">
        <label>
          Destination
          <input
            name="destination"
            placeholder="Any destination"
            list={`${prefix}-places`}
            defaultValue={intent.destination.value ?? ''}
          />
        </label>
        <datalist id={`${prefix}-places`}>
          {service.destinations().map((place) => (
            <option key={place.id} value={place.name} />
          ))}
        </datalist>
        <label>
          Departing from
          <input
            name="origin"
            placeholder="e.g. Berlin"
            defaultValue={intent.origin.value ?? ''}
            list={`${prefix}-origins`}
          />
        </label>
        <datalist id={`${prefix}-origins`}>
          {[
            'Berlin',
            'Copenhagen',
            'Dresden',
            'Edinburgh',
            'London',
            'Munich',
          ].map((city) => (
            <option key={city} value={city} />
          ))}
        </datalist>
        <label>
          Departure date
          <input name="start" type="date" defaultValue={dates?.start ?? ''} />
        </label>
        <label>
          Return date
          <input name="end" type="date" defaultValue={dates?.end ?? ''} />
        </label>
        <label>
          Date flexibility
          <select name="flexibility" defaultValue={dates?.flexibility ?? 0}>
            {[...new Set([0, 1, 3, 7, 14, dates?.flexibility ?? 0])]
              .sort((a, b) => a - b)
              .map((value) => (
                <option key={value} value={value}>
                  {value ? `±${value} days` : 'No date buffer'}
                </option>
              ))}
          </select>
        </label>
        <label>
          Season or month
          <input
            name="season"
            placeholder="Any season"
            defaultValue={dates?.season ?? ''}
          />
        </label>
        <label>
          Trip length (days)
          <input
            name="duration"
            type="number"
            min="1"
            max="30"
            placeholder="Flexible"
            defaultValue={intent.duration.value ?? ''}
          />
        </label>
        <label>
          Travelers
          <input
            name="travelers"
            type="number"
            min="1"
            max="12"
            required
            defaultValue={intent.travelers.value ?? 1}
          />
        </label>
        <label>
          Group budget (€)
          <input
            name="budget"
            type="number"
            min="1"
            step="0.01"
            placeholder="Any budget"
            defaultValue={budget?.amount ?? ''}
          />
        </label>
        <label className="check budget-check">
          <input
            name="hardBudget"
            type="checkbox"
            defaultChecked={budget?.hard ?? true}
          />{' '}
          Strict budget limit
        </label>
        <label>
          Interests
          <input
            name="interests"
            placeholder="e.g. Nature, Food"
            defaultValue={intent.interests.value?.join(', ') ?? ''}
          />
        </label>
        <label>
          Accommodation preference
          <input
            name="accommodation"
            placeholder="e.g. Guesthouse"
            defaultValue={intent.accommodation.value ?? ''}
          />
        </label>
      </div>
      <fieldset className="form-section">
        <legend>Transport</legend>
        <div className="check-row">
          {modes.map((mode: Mode) => (
            <label className="check" key={mode}>
              <input
                type="checkbox"
                name={mode}
                defaultChecked={transport?.modes.includes(mode) ?? false}
              />
              {modeNames[mode]}
            </label>
          ))}
          <label className="check">
            <input
              name="hardTransport"
              type="checkbox"
              defaultChecked={transport?.hard ?? false}
            />{' '}
            Require selected modes
          </label>
        </div>
      </fieldset>
      <div className="form-section">
        <label className="check">
          <input
            type="checkbox"
            checked={businessEnabled}
            onChange={(event) => setBusinessEnabled(event.target.checked)}
          />{' '}
          Business trip <DemoBadge />
        </label>
        {businessEnabled && (
          <div className="business-fields">
            <p className="muted">
              Example checks use fixture costs and a 30-minute arrival buffer.
              Your organization’s policies and approvals are separate.
            </p>
            <div className="form-grid">
              <label>
                Business purpose
                <input
                  name="purpose"
                  placeholder="e.g. Team meeting"
                  defaultValue={business?.purpose ?? ''}
                />
              </label>
              <label>
                Meeting date
                <input
                  name="meetingDate"
                  type="date"
                  defaultValue={business?.meetingDate ?? ''}
                />
              </label>
              <label>
                Meeting time (local)
                <input
                  name="meetingTime"
                  type="time"
                  defaultValue={business?.meetingTime ?? ''}
                />
              </label>
              <label>
                Private extension (nights)
                <input
                  name="privateNights"
                  type="number"
                  min="0"
                  max="14"
                  defaultValue={business?.privateNights ?? 0}
                />
              </label>
            </div>
            <label className="check">
              <input
                name="hardMeeting"
                type="checkbox"
                defaultChecked={business?.hardMeeting ?? true}
              />{' '}
              Require a 30-minute meeting buffer
            </label>
          </div>
        )}
      </div>
      {Object.values(intent).some((item) => item.provenance === 'inferred') && (
        <label className="check confirm-check">
          <input name="confirmInferences" type="checkbox" /> Confirm the
          inferred values shown here
        </label>
      )}
      {validation && (
        <p className="validation" role="alert">
          {validation}
        </p>
      )}
      <button type="submit" className="button button-primary">
        {label}
      </button>
    </form>
  );
}

export function CriteriaDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const { dispatch } = useTravel();
  useEffect(() => {
    const element = dialog.current;
    if (open && !element?.open) element?.showModal();
    if (!open && element?.open) element.close();
  }, [open]);

  return (
    <dialog
      ref={dialog}
      className="criteria-dialog"
      aria-labelledby="criteria-title"
      onCancel={onClose}
      onClose={onClose}
    >
      {open && (
        <>
          <div className="dialog-header">
            <div>
              <Eyebrow>Shared across Wohin</Eyebrow>
              <h2 id="criteria-title">Journey criteria</h2>
            </div>
            <button
              type="button"
              className="icon-button"
              aria-label="Close journey criteria"
              onClick={onClose}
            >
              <X size={20} />
            </button>
          </div>
          <CriteriaForm
            compact
            onApply={(changes) => {
              if (Object.keys(changes).length)
                dispatch({ type: 'update', changes });
              onClose();
            }}
          />
        </>
      )}
    </dialog>
  );
}

export function CriteriaBar({
  onEdit,
  children,
}: {
  onEdit: () => void;
  children?: ReactNode;
}) {
  const {
    session: { intent },
  } = useTravel();
  const {
    destination,
    origin,
    dates,
    duration,
    travelers,
    budget,
    transport,
    interests,
    accommodation,
    business,
  } = intent;
  const items: { label: string; provenance: Provenance; icon: ReactNode }[] = [
    {
      label: destination.value ?? 'Any destination',
      provenance: destination.provenance,
      icon: <MapPin />,
    },
    {
      label: origin.value ? `From ${origin.value}` : 'Any origin',
      provenance: origin.provenance,
      icon: <Plane />,
    },
    {
      label: datesLabel(dates.value),
      provenance: dates.provenance,
      icon: <CalendarDays />,
    },
    {
      label: `${travelers.value ?? 1} ${travelers.value === 1 ? 'traveler' : 'travelers'}`,
      provenance: travelers.provenance,
      icon: <Users />,
    },
    {
      label: budget.value
        ? `${budget.value.hard ? 'Max' : 'Around'} ${budgetLabel(budget.value.amount)}`
        : 'Any budget',
      provenance: budget.provenance,
      icon: <Euro />,
    },
  ];
  if (duration.value)
    items.push({
      label: `${duration.value} days`,
      provenance: duration.provenance,
      icon: <CalendarDays />,
    });
  if (transport.value)
    items.push({
      label: transport.value.modes.length
        ? transport.value.modes.map((mode) => modeNames[mode]).join(' · ')
        : 'No allowed modes',
      provenance: transport.provenance,
      icon: <Plane />,
    });
  if (interests.value?.length)
    items.push({
      label: interests.value.join(' · '),
      provenance: interests.provenance,
      icon: <Compass />,
    });
  if (accommodation.value)
    items.push({
      label: accommodation.value,
      provenance: accommodation.provenance,
      icon: <Compass />,
    });
  if (business.value)
    items.push({
      label: 'Business trip',
      provenance: business.provenance,
      icon: <SlidersHorizontal />,
    });
  return (
    <div className="criteria-bar">
      <Eyebrow>Journey criteria</Eyebrow>
      <div className="chip-row">
        {items.map(({ label, provenance, icon }, index) => (
          <button
            type="button"
            className="chip criteria-chip"
            key={index}
            onClick={onEdit}
            aria-label={`Edit journey criteria: ${label} (${provenance})`}
          >
            {icon}
            <span>{label}</span>
            <small>{provenance}</small>
          </button>
        ))}
        <button type="button" className="chip edit-chip" onClick={onEdit}>
          <Pencil size={13} /> Edit criteria
        </button>
        {children}
      </div>
    </div>
  );
}
