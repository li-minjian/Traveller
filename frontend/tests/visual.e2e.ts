import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

async function snapshot(page: Page, name: string) {
  await page.evaluate(() => {
    window.scrollTo(0, 0);
  });
  await page.evaluate(() => document.fonts.ready);
  const viewport = page.viewportSize();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(viewport!.width);
  await page.screenshot({
    path: test.info().outputPath(`${name}.png`),
    fullPage: true,
    animations: 'disabled',
  });
}

for (const size of [
  { width: 1440, height: 960 },
  { width: 390, height: 844 },
]) {
  test(`all view layouts at ${size.width}px`, async ({ page }) => {
    const failedRequests: string[] = [];
    page.on('pageerror', (error) => failedRequests.push(error.message));
    await page.route('**/*', (route) => {
      if (
        new URL(route.request().url()).origin !== new URL(page.url()).origin &&
        page.url() !== 'about:blank'
      ) {
        failedRequests.push(route.request().url());
        return route.abort();
      }
      return route.continue();
    });
    await page.setViewportSize(size);
    await page.goto('/');
    await snapshot(page, '01-landing');
    await page.getByRole('button', { name: 'Nature and quiet places' }).click();
    await expect(
      page.getByRole('heading', { name: 'Curating travel opportunities…' }),
    ).toBeVisible();
    await snapshot(page, '02-discovery-initial');
    await expect(
      page.getByRole('heading', { name: 'Journeys to consider' }),
    ).toBeVisible();
    await page
      .getByRole('button', { name: 'Compare The Misty Archipelago' })
      .click();
    await page
      .getByRole('button', { name: 'Compare Tuscan Hills by Rail' })
      .click();
    await snapshot(page, '03-discovery-results');
    await page.getByRole('link', { name: 'Compare (2)' }).click();
    await expect(
      page.getByRole('heading', { name: 'Comparison matrix' }),
    ).toBeVisible();
    await snapshot(page, '04-compare');
    await page
      .getByRole('link', { name: 'Explore The Misty Archipelago' })
      .click();
    await expect(
      page.getByRole('heading', {
        name: 'Faroe Islands',
        exact: true,
        level: 1,
      }),
    ).toBeVisible();
    await snapshot(page, '05-explore');

    await page
      .getByRole('navigation')
      .getByRole('link', { name: 'Travel search' })
      .click();
    await page.getByRole('button', { name: 'Open search form' }).click();
    await expect(
      page.getByRole('heading', { name: 'Find your next journey.' }),
    ).toBeVisible();
    await snapshot(page, '06-search-entry');
    await page.getByRole('button', { name: 'Hide search form' }).click();
    await snapshot(page, '07-search-results');
    await page
      .getByRole('link', { name: 'View destination for The Misty Archipelago' })
      .click();
    await expect(
      page.getByRole('heading', { name: 'Places and activities' }),
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Connections to consider' }),
    ).toBeVisible();
    await snapshot(page, '08-destination');
    expect(failedRequests).toEqual([]);
  });
}

test('tablet comparison keeps horizontal scrolling inside the matrix', async ({
  page,
}) => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.goto('/search');
  await page
    .getByRole('button', { name: 'Compare The Misty Archipelago' })
    .click();
  await page
    .getByRole('button', { name: 'Compare Tuscan Hills by Rail' })
    .click();
  await page.getByRole('button', { name: 'Compare The Highland Way' }).click();
  await page.getByRole('link', { name: 'Compare (3)' }).click();
  await expect(
    page.getByRole('heading', { name: 'Comparison matrix' }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(768);
});
