import { UserRound } from 'lucide-react';
import { useId, useRef } from 'react';

export function SignIn({ guest = false }: { guest?: boolean }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  return (
    <>
      <button
        className={guest ? 'v1-account' : 'v1-sign-in'}
        type="button"
        aria-haspopup="dialog"
        aria-label={guest ? 'Guest account, sign in' : undefined}
        onClick={() => dialog.current?.showModal()}
      >
        {guest ? (
          <>
            <span className="v1-account-avatar"><UserRound size={16} aria-hidden="true" /></span>
            <span className="v1-account-label"><strong>Guest</strong><small>Sign in</small></span>
          </>
        ) : 'Sign in'}
      </button>
      <dialog ref={dialog} className="v1-dialog v1-sign-in-dialog" aria-labelledby={titleId}>
        <h2 id={titleId}>Sign in</h2>
        <p>Traveller accounts are coming soon.</p>
        <div className="v1-dialog-actions">
          <button className="v1-dialog-primary" type="button" onClick={() => dialog.current?.close()}>
            Done
          </button>
        </div>
      </dialog>
    </>
  );
}
