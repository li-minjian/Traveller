import { ArrowUp, ArrowUpRight } from 'lucide-react';
import { useState } from 'react';
import type { FormEvent, Ref } from 'react';

export function MessageComposer({
  onSend, landing = false, pending = false, inputRef,
}: {
  onSend: (message: string) => void;
  landing?: boolean;
  pending?: boolean;
  inputRef?: Ref<HTMLTextAreaElement>;
}) {
  const [text, setText] = useState('');
  const action = landing ? 'Start planning' : 'Send message';

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = text.trim();
    if (pending || !message) return;
    onSend(message);
    setText('');
  }

  return (
    <form className={`v1-composer ${landing ? 'v1-hero-composer' : ''}`} onSubmit={submit}>
      <textarea
        ref={inputRef}
        aria-label={landing ? 'Describe your trip' : 'Message the travel assistant'}
        placeholder={landing ? 'I want to travel from Berlin to Lisbon…' : 'Ask anything about your trip…'}
        rows={landing ? 2 : 1}
        value={text}
        onChange={(event) => setText(event.currentTarget.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }
        }}
      />
      <button className="v1-send" type="submit" aria-label={action} title={action} disabled={pending}>
        {landing ? <ArrowUpRight size={21} aria-hidden="true" /> : <ArrowUp size={17} aria-hidden="true" />}
      </button>
    </form>
  );
}
