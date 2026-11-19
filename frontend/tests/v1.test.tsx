// @vitest-environment jsdom
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrictMode } from 'react';
import { RouterProvider, createMemoryRouter } from 'react-router';
import { afterEach, describe, expect, it } from 'vitest';
import { routes } from '../src/app/App';

// JSDOM models the open attribute but leaves the dialog methods to browsers.
Object.defineProperties(HTMLDialogElement.prototype, {
  showModal: {
    value(this: HTMLDialogElement) { this.open = true; },
    configurable: true,
  },
  close: {
    value(this: HTMLDialogElement) { this.open = false; },
    configurable: true,
  },
});

afterEach(cleanup);

function open(path = '/') {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const user = userEvent.setup();
  render(<StrictMode><RouterProvider router={router} /></StrictMode>);
  return { router, user };
}

const confirmation = /Is that correct/;

async function send(user: ReturnType<typeof userEvent.setup>, text: string) {
  const composer = screen.getByRole('textbox', { name: 'Message the travel assistant' });
  await user.type(composer, text + '{Enter}');
}

describe('Traveller UI V1', () => {
  it('ignores blank input and hands off one trimmed request, even in Strict Mode', async () => {
    const { router, user } = open();
    const input = screen.getByRole('textbox', { name: 'Describe your trip' });
    await user.type(input, '   {Enter}');
    expect(router.state.location.pathname).toBe('/');

    await user.type(input, 'Berlin to Lisbon {Enter}');
    expect(router.state.location.pathname).toBe('/chat');
    const conversation = within(screen.getByRole('log'));
    expect(conversation.getByText('Preparing a demo reply…')).toBeTruthy();
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Send message' }).disabled).toBe(true);
    await conversation.findByText(confirmation);
    expect(conversation.getAllByText('Berlin to Lisbon')).toHaveLength(1);
    expect(router.state.location.state).toBeNull();

    await send(user, 'yes');
    expect(await conversation.findByRole('article', { name: 'Berlin → Lisbon' })).toBeTruthy();
    expect(conversation.getByText('Demo only')).toBeTruthy();

    await user.click(within(screen.getByRole('main')).getByRole('button', { name: 'New journey' }));
    expect(screen.getByRole('heading', { name: 'Let’s plan your trip.' })).toBeTruthy();
    expect(screen.queryByRole('article')).toBeNull();
    expect(within(screen.getByRole('complementary', { name: 'Travel context' })).getAllByText('Not set')).toHaveLength(3);
  });

  it('cancels context edits and invalidates the displayed result when a change is applied', async () => {
    const { user } = open();
    await user.click(screen.getByRole('button', { name: 'Berlin → Lisbon' }));
    await screen.findByText(confirmation);
    await send(user, 'yes');
    await screen.findByRole('article');

    const context = within(screen.getByRole('complementary', { name: 'Travel context' }));
    await user.click(context.getByRole('button', { name: 'Edit' }));
    let editor = within(screen.getByRole('dialog', { name: 'Edit trip details' }));
    const destination = editor.getByRole('textbox', { name: 'To' });
    await user.clear(destination);
    await user.type(destination, 'Porto');
    await user.click(editor.getByRole('button', { name: 'Cancel' }));
    expect(context.getByText('Lisbon', { exact: true })).toBeTruthy();
    expect(screen.getByRole('article')).toBeTruthy();

    await user.click(context.getByRole('button', { name: 'Edit' }));
    editor = within(screen.getByRole('dialog', { name: 'Edit trip details' }));
    const reopened = editor.getByRole<HTMLInputElement>('textbox', { name: 'To' });
    expect(reopened.value).toBe('Lisbon');
    await user.clear(reopened);
    await user.type(reopened, 'Porto');
    await user.click(editor.getByRole('button', { name: 'Apply' }));
    expect(context.getByText('Porto', { exact: true })).toBeTruthy();
    expect(screen.queryByRole('article')).toBeNull();
  });

  it.each([
    ['empty', 'No example flights found in this demo scenario.'],
    ['api-error', 'The simulated flight search failed. Reply “yes” to retry.'],
  ])('shows the %s state without a flight', async (scenario, expected) => {
    const { user } = open('/chat?scenario=' + scenario);
    await send(user, 'Berlin to Lisbon');
    await screen.findByText(confirmation);
    await send(user, 'yes');
    expect(await screen.findByText(expected)).toBeTruthy();
    expect(screen.queryByRole('article')).toBeNull();
    if (scenario === 'api-error') expect(screen.getByRole('alert').textContent).toBe(expected);
  });

  it('cancels a pending reply when starting a new journey', async () => {
    const { user } = open('/chat');
    await send(user, 'Berlin to Lisbon');
    expect(screen.getByText('Preparing a demo reply…')).toBeTruthy();
    await user.click(within(screen.getByRole('main')).getByRole('button', { name: 'New journey' }));
    await send(user, 'Paris');
    expect(await screen.findByText(/This demo uses scripted replies/)).toBeTruthy();
    expect(screen.queryByText(confirmation)).toBeNull();
    expect(within(screen.getByRole('log')).queryByText('Berlin to Lisbon', { exact: true })).toBeNull();
  });
});
