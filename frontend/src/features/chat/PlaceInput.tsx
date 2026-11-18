import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import type { Place } from '../../api/client';
import { canonicalPlace, matchPlaces } from './places';

type Props = {
  id: string;
  value: string;
  onChange: (value: string) => void;
  /** Cities to suggest; `null` turns this into a plain text input. */
  places: Place[] | null;
  placeholder?: string;
  disabled?: boolean;
  'aria-invalid'?: boolean;
  'aria-describedby'?: string;
};

/**
 * Text input for a city with suggestions (ARIA 1.2 combobox with a listbox
 * popup). Typing a city, an alias or a country lists matching cities;
 * picking one sets the canonical name. Free text stays allowed.
 */
export function PlaceInput({
  id,
  value,
  onChange,
  places,
  placeholder,
  disabled,
  'aria-invalid': ariaInvalid,
  'aria-describedby': describedBy,
}: Props) {
  const listRef = useRef<HTMLUListElement>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [focused, setFocused] = useState(false);

  const options = useMemo(
    () => (places ? matchPlaces(places, value) : []),
    [places, value],
  );
  const expanded = open && options.length > 0 && !disabled;
  const listId = `${id}-listbox`;
  const hintId = `${id}-hint`;
  const optionId = (index: number) => `${id}-option-${index}`;

  // Keep the highlighted option visible while moving through a long list.
  useEffect(() => {
    if (!expanded || active < 0) return;
    const option = listRef.current?.children[active];
    if (option instanceof HTMLElement) option.scrollIntoView({ block: 'nearest' });
  }, [expanded, active]);

  if (places === null)
    return (
      <input
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        disabled={disabled}
        aria-invalid={ariaInvalid}
        aria-describedby={describedBy}
      />
    );

  const known = canonicalPlace(places, value);
  const showHint = !focused && value.trim() !== '' && known === null;
  const describedByAll =
    [describedBy, showHint ? hintId : null].filter(Boolean).join(' ') ||
    undefined;

  function close() {
    setOpen(false);
    setActive(-1);
  }

  function pick(place: Place) {
    onChange(place.name);
    close();
  }

  /** Text that is exactly a city name or alias becomes the canonical name. */
  function normalize() {
    if (known !== null && known !== value) onChange(known);
  }

  function move(step: 1 | -1) {
    if (!expanded) {
      setOpen(true);
      setActive(step === 1 ? 0 : options.length - 1);
      return;
    }
    setActive((current) => {
      if (current < 0) return step === 1 ? 0 : options.length - 1;
      return (current + step + options.length) % options.length;
    });
  }

  function keyDown(event: KeyboardEvent<HTMLInputElement>) {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        if (event.altKey) setOpen(true);
        else move(1);
        break;
      case 'ArrowUp':
        event.preventDefault();
        move(-1);
        break;
      case 'Enter': {
        // With the list open, Enter picks instead of submitting the form.
        if (!expanded) return;
        event.preventDefault();
        const option = options[active];
        if (option) pick(option);
        else {
          normalize();
          close();
        }
        break;
      }
      case 'Escape':
        if (!expanded) return;
        event.preventDefault();
        close();
        break;
      case 'Tab':
        close();
        break;
    }
  }

  return (
    <>
      <div className="place-combo">
        <input
          id={id}
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={expanded}
          aria-controls={listId}
          aria-activedescendant={
            expanded && active >= 0 ? optionId(active) : undefined
          }
          value={value}
          onChange={(event) => {
            onChange(event.target.value);
            setOpen(true);
            setActive(-1);
          }}
          onKeyDown={keyDown}
          onClick={() => setOpen(true)}
          onFocus={() => setFocused(true)}
          onBlur={() => {
            setFocused(false);
            close();
            normalize();
          }}
          placeholder={placeholder}
          autoComplete="off"
          spellCheck={false}
          disabled={disabled}
          aria-invalid={ariaInvalid}
          aria-describedby={describedByAll}
        />
        <ul
          id={listId}
          ref={listRef}
          className="place-list"
          role="listbox"
          aria-label="Cities with flight data"
          hidden={!expanded}
          // Clicks in the list (also on its scrollbar) keep the input focused.
          onMouseDown={(event) => event.preventDefault()}
        >
          {expanded &&
            options.map((place, index) => (
              <li
                key={`${place.country}/${place.name}`}
                id={optionId(index)}
                role="option"
                aria-selected={index === active}
                className="place-option"
                onMouseDown={(event) => {
                  event.preventDefault();
                  pick(place);
                }}
                onMouseMove={() => {
                  if (index !== active) setActive(index);
                }}
              >
                <span className="place-name">{place.name}</span>
                <span className="place-country"> · {place.country}</span>
              </li>
            ))}
        </ul>
      </div>
      {showHint && (
        <p className="place-hint" id={hintId}>
          No flight data for this place yet – pick one from the list.
        </p>
      )}
    </>
  );
}
