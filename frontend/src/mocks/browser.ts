import { setupWorker } from 'msw/browser';
import { createMockHandlers } from './handlers';
import type { MockScenario } from './handlers';

export async function startMockApi() {
  const requested = new URLSearchParams(location.search).get('scenario');
  const scenario: MockScenario =
    requested === 'empty' || requested === 'backend-error' || requested === 'api-error'
      ? requested
      : 'success';
  const worker = setupWorker(...createMockHandlers({
    scenario, storage: sessionStorage, responseDelay: 400,
  }));
  await worker.start();
  return scenario;
}
