// @vitest-environment jsdom
/// <reference types="vitest/jsdom" />
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatPage } from '../src/features/Chat';
import { createMockHandlers } from '../src/mocks/handlers';
import type { MockScenario } from '../src/mocks/handlers';

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
beforeEach(() => {
  // Use browser storage when the Node version already defines localStorage.
  vi.stubGlobal('localStorage', jsdom.window.localStorage);
});
afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.unstubAllGlobals();
  server.resetHandlers();
});
afterAll(() => server.close());

async function openChat(scenario: MockScenario = 'success', responseDelay = 0) {
  server.use(...createMockHandlers({ scenario, responseDelay }));
  const view = render(<ChatPage />);
  const user = userEvent.setup();
  const input = screen.getByRole<HTMLInputElement>('textbox', { name: 'Message' });
  await waitFor(() => expect(input.disabled).toBe(false));

  return {
    view,
    user,
    input,
    async send(text: string) {
      await user.type(input, text);
      await user.click(screen.getByRole('button', { name: 'Send' }));
    },
  };
}

describe('planning chat', () => {
  it('submits text, shows the pending state and asks for missing details', async () => {
    const { send, input } = await openChat('success', 300);
    const messages = within(screen.getByRole('log'));

    await send('I want to travel');
    expect(messages.getByText('I want to travel')).toBeTruthy();
    expect(messages.getByText('thinking…')).toBeTruthy();
    expect(input.disabled).toBe(true);
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Sending…' }).disabled).toBe(true);

    await messages.findByText('Still needed: origin.');
    expect(messages.queryByText('thinking…')).toBeNull();
    expect(input.value).toBe('');
  });

  it('restores the saved conversation next to the itinerary workspace', async () => {
    const { send, view } = await openChat();
    await send('I want to travel');
    await screen.findByText('Still needed: origin.');

    view.unmount();
    render(<ChatPage />);
    await screen.findByText('Still needed: origin.');
    const messages = within(screen.getByRole('log'));
    expect(messages.getByText('I want to travel')).toBeTruthy();
    expect(messages.getByText('Still needed: origin.')).toBeTruthy();
    expect(
      screen.getByRole('heading', { name: /Results for/ }),
    ).toBeTruthy();
    expect(screen.getByRole('region', { name: 'Trip map' })).toBeTruthy();
  });

  it('saves the trip and updates travelers through the API', async () => {
    const { user } = await openChat();
    await user.click(
      screen.getByRole('button', { name: 'Save this itinerary to a trip' }),
    );
    expect(
      screen.getByRole('button', { name: /Saved to your trip/ }),
    ).toBeTruthy();

    await user.click(
      screen.getByRole('button', { name: /Dates & travelers/ }),
    );
    expect(screen.getByLabelText('Departure')).toBeTruthy();
    expect(screen.getByLabelText('Return')).toBeTruthy();
    const travelers = screen.getByLabelText<HTMLInputElement>('Travelers');

    await user.clear(travelers);
    await user.type(travelers, '2');
    await user.click(screen.getByRole('button', { name: /Update trip/ }));
    await screen.findByText('Still needed: origin.');

    // The form closed after the API accepted the structured fields. Reopening
    // shows the trip state returned by the backend.
    await user.click(
      screen.getByRole('button', { name: /Dates & travelers/ }),
    );
    expect(screen.getByLabelText<HTMLInputElement>('Travelers').value).toBe('2');
  });

  it('shows a structured journey after the inferred destination is confirmed', async () => {
    const { send } = await openChat();
    await send('Berlin to Lissabon');
    await screen.findByText(/Did you mean Lissabon/);
    expect(screen.queryByText(/EX 1201/)).toBeNull();

    await send('yes');
    await screen.findByText('I found a sample flight.');
    expect(screen.getByText(/EX 1201/)).toBeTruthy();
    expect(screen.getByText('recommended')).toBeTruthy();
  });

  it('shows a no-results reply without a flight card', async () => {
    const { send } = await openChat('empty');
    await send('Berlin to Lissabon');
    await screen.findByText(/Did you mean Lissabon/);
    await send('yes');

    await screen.findByText('No flights match this demo search.');
    expect(screen.queryByText(/EX 1201/)).toBeNull();
  });

  it.each([
    ['backend-error', 'The language model or planner is temporarily unavailable.'],
    ['api-error', 'The input is invalid.'],
  ] as const)('shows the %s message and restores the input for retry', async (scenario, expected) => {
    const { send, input } = await openChat(scenario);
    await send('Plan a trip');
    expect((await screen.findByRole('alert')).textContent).toContain(expected);
    expect(input.value).toBe('Plan a trip');
    expect(input.disabled).toBe(false);
  });
});
