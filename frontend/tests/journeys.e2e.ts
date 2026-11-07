import { expect, test } from '@playwright/test';
import axe from 'axe-core';

declare global {
  interface Window {
    axe: typeof axe;
  }
}

test('AI prompt, comparison, exploration, back and deep refresh preserve the session', async ({
  page,
}) => {
  await page.goto('/');
  const prompt = page.getByRole('textbox', { name: 'Your travel wish' });
  await prompt.fill('   ');
  await prompt.press('Enter');
  await expect(page).toHaveURL(/\/$/);

  await page.getByRole('button', { name: 'Nature and quiet places' }).click();
  await expect(page).toHaveURL(/\/discover$/);
  await expect(
    page
      .getByText('Nature and quiet places for 6 days around €1,800')
      .filter({ visible: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Curating travel opportunities…' }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Journeys to consider' }),
  ).toBeVisible();
  await expect(page.getByText('Some estimates are incomplete.')).toBeVisible();

  await page.getByRole('button', { name: 'View map' }).click();
  await page.getByRole('button', { name: 'Show Isle of Skye on map' }).click();
  await expect(
    page.getByRole('link', { name: 'See Isle of Skye in results' }),
  ).toBeVisible();

  await page.getByLabel('Sort journeys').selectOption('price');
  const faroe = page.getByRole('button', {
    name: 'Compare The Misty Archipelago',
  });
  const skye = page.getByRole('button', { name: 'Compare The Highland Way' });
  await faroe.click();
  await skye.click();
  await expect(faroe).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('link', { name: 'Compare (2)' }).click();
  await expect(
    page.getByRole('heading', { name: 'See the differences.' }),
  ).toBeVisible();
  await expect(
    page.getByRole('table').getByRole('cell', { name: 'Unknown' }),
  ).toBeVisible();

  await page
    .getByRole('link', { name: 'Explore The Misty Archipelago' })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Faroe Islands', exact: true, level: 1 }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Show Saksun lagoon on map' }).click();
  await expect(
    page.getByRole('heading', { name: 'Saksun lagoon', exact: true }),
  ).toHaveCount(2);
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'A 6-day outline' }),
  ).toBeVisible();

  await page.getByRole('link', { name: 'Back to comparison' }).click();
  await expect(
    page.getByRole('heading', { name: 'Comparison matrix' }),
  ).toBeVisible();
  await page.getByRole('link', { name: 'Back to discoveries' }).click();
  await expect(faroe).toHaveAttribute('aria-pressed', 'true');
  await expect(skye).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByLabel('Sort journeys')).toHaveValue('price');
});

test('traditional search and Ask AI share destination, budget, filters and business context', async ({
  page,
}) => {
  await page.goto('/search');
  await page.getByLabel('Destination', { exact: true }).fill('Leipzig');
  await page.getByLabel('Departing from').fill('Berlin');
  await page.getByLabel('Group budget (€)').fill('400');
  await page.getByRole('checkbox', { name: 'Business trip' }).check();
  await page.getByLabel('Business purpose').fill('Project meeting');
  await page.getByLabel('Meeting time (local)').fill('10:30');
  await page.getByRole('button', { name: 'Search journeys' }).click();

  await expect(page.getByText('1 journey found')).toBeVisible();
  await page
    .getByRole('link', { name: 'View destination for Leipzig by Morning Rail' })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Leipzig', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Connections to consider' }),
  ).toBeVisible();
  await page
    .getByRole('button', { name: 'Ask AI about this destination' })
    .click();

  await expect(
    page.getByRole('button', {
      name: 'Edit journey criteria: Leipzig (confirmed)',
    }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', {
      name: 'Edit journey criteria: Max €400 (confirmed)',
    }),
  ).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Back to destination guide' }),
  ).toBeVisible();
  await expect(page.getByText('1 journey found')).toBeVisible();
  await page
    .getByRole('link', { name: 'Explore Leipzig by Morning Rail' })
    .click();
  await expect(page.getByText('Work trip · Project meeting')).toBeVisible();
  await expect(page.getByText('Meeting buffer · fits')).toBeVisible();
  await expect(page.getByText('Example constraint checks')).toBeVisible();

  await page
    .getByRole('button', { name: 'Edit criteria', exact: true })
    .click();
  const dialog = page.getByRole('dialog', { name: 'Journey criteria' });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel('Group budget (€)').fill('50');
  await dialog.getByRole('button', { name: 'Apply criteria' }).click();
  await expect(
    page.getByRole('heading', { name: 'This journey is unavailable' }),
  ).toBeVisible();

  await page
    .getByRole('navigation')
    .getByRole('link', { name: 'Travel search' })
    .click();
  await expect(
    page.getByRole('heading', { name: 'No journeys fit these criteria' }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', {
      name: 'Edit journey criteria: Max €50 (confirmed)',
    }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Review criteria' }).click();
  await expect(dialog.getByLabel('Destination', { exact: true })).toHaveValue(
    'Leipzig',
  );
  await expect(dialog.getByLabel('Business purpose')).toHaveValue(
    'Project meeting',
  );
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Review criteria' }),
  ).toBeFocused();
});

test('in-flight refinement wins, stale results are marked, and retry is deterministic', async ({
  page,
}) => {
  await page.goto('/');
  const prompt = page.getByRole('textbox', { name: 'Your travel wish' });
  await prompt.fill('Quiet nature and the Faroe Islands');
  await prompt.press('Enter');
  const refine = page.getByRole('textbox', { name: 'Refine your trip' });
  await expect(
    page.getByRole('heading', { name: 'Curating travel opportunities…' }),
  ).toBeVisible();
  await refine.fill('Leipzig from Berlin');
  await refine.press('Enter');
  await expect(page.getByText('2 journeys found')).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Faroe Islands' }),
  ).toHaveCount(0);

  await refine.fill('Faroe Islands, no flights');
  await refine.press('Enter');
  await expect(
    page.getByRole('heading', { name: 'Refreshing your journeys…' }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'No journeys fit these criteria' }),
  ).toBeVisible();
  await expect(
    page.getByText(/Required transport modes exclude other connections/),
  ).toBeVisible();

  await refine.fill('Demo error');
  await refine.press('Enter');
  await expect(page.getByRole('alert')).toContainText(
    'sample search service was interrupted',
  );
  await page.getByRole('button', { name: 'Retry search' }).click();
  await expect(
    page.getByRole('heading', { name: 'No journeys fit these criteria' }),
  ).toBeVisible();
  await refine.fill('Book a private helicopter for me');
  await refine.press('Enter');
  await expect(page.getByText(/Your criteria are unchanged/)).toBeVisible();
});

test('unknown coordinates stay empty on destination and report routes', async ({
  page,
}) => {
  await page.goto('/destinations/dresden');
  await expect(
    page.getByText(
      'Map unavailable. No coordinates were supplied for these places.',
    ),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: /on map/ })).toHaveCount(0);
  await page.goto('/explore/dresden-rail');
  await expect(
    page.getByRole('heading', { name: 'Dresden', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(
      'Map unavailable. No coordinates were supplied for these places.',
    ),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: /on map/ })).toHaveCount(0);
});

test('keyboard entry, narrow workspace and core accessibility checks', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.keyboard.press('Tab');
  await expect(
    page.getByRole('link', { name: 'Skip to content' }),
  ).toBeFocused();
  await page.addScriptTag({ content: axe.source });
  const scan = () =>
    page.evaluate(async () => {
      const { violations } = await window.axe.run({
        runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] },
      });
      return violations.map(({ id, nodes }) => ({
        id,
        targets: nodes.map((node) => node.target),
      }));
    });
  expect(await scan()).toEqual([]);

  await page.getByRole('button', { name: 'A weekend escape' }).focus();
  await page.keyboard.press('Enter');
  await expect(
    page
      .getByText('A spontaneous weekend escape by train')
      .filter({ visible: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Open chat' }).click();
  await expect(
    page.getByRole('textbox', { name: 'Refine your trip' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Close chat' }).click();
  await expect(
    page.getByRole('heading', { name: 'Journeys to consider' }),
  ).toBeVisible();
  expect(await scan()).toEqual([]);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
});
