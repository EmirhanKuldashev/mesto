import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test } from '@playwright/test';

const api = 'http://127.0.0.1:18100';
const tile = readFileSync(path.join(__dirname, 'fixtures/map-tile.png'));
const first = { latitude: 56.01, longitude: 92.85 };
const second = { latitude: 56.02, longitude: 92.9 };

test.beforeEach(async ({ context }) => {
  await context.route('https://tile.openstreetmap.org/**', route => route.fulfill({ contentType: 'image/png', body: tile }));
});

test('real Local point, changed coordinates, map selection and keyboard-accessible inputs', async ({ page, request }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const expected = await request.post(`${api}/api/analytics/local`, { data: first });
  expect(expected.status()).toBe(200);
  const result = await expected.json();
  expect(result.availability).toBe('AVAILABLE');
  await page.goto('/district');
  const panel = page.getByRole('region', { name: 'MESTO Local', exact: true });
  await expect(panel).toBeVisible();
  await panel.getByLabel('Широта места').fill(String(first.latitude));
  await panel.getByLabel('Долгота места').fill(String(first.longitude));
  await panel.getByRole('button', { name: 'Оценить место', exact: true }).focus();
  const response = page.waitForResponse(r => r.url() === `${api}/api/analytics/local`);
  await page.keyboard.press('Enter');
  expect((await response).status()).toBe(200);
  await expect(panel.getByLabel(`MESTO Local: ${Math.round(result.score)} из 100`, { exact: true })).toBeVisible();
  for (const label of ['Остановки', 'Школы', 'Детские сады', 'Медицина', 'Парки']) await expect(panel.getByText(label, { exact: true })).toBeVisible();
  for (const c of Object.values(result.components) as { distance_m: number }[]) {
    await expect(panel.getByText(`~${Math.round(c.distance_m)} м ·`, { exact: false })).toBeVisible();
  }
  await panel.getByLabel('Широта места').fill(String(second.latitude));
  await panel.getByLabel('Долгота места').fill(String(second.longitude));
  const changed = page.waitForResponse(r => r.url() === `${api}/api/analytics/local`);
  await panel.getByRole('button', { name: 'Оценить место', exact: true }).click();
  const changedResult = await (await changed).json();
  expect(changedResult.availability).toBe('AVAILABLE');
  expect(changedResult.location).toEqual(second);
  expect(changedResult.components).not.toEqual(result.components);
  await expect(panel.getByLabel(`MESTO Local: ${Math.round(changedResult.score)} из 100`, { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Оценить место на карте', exact: true }).click();
  const mapResponse = page.waitForResponse(r => r.url() === `${api}/api/analytics/local`);
  const canvas = page.getByRole('application', { name: 'Карта административных районов и оценок ЖК' }).locator('canvas');
  await canvas.click({ position: { x: 180, y: 200 } });
  const mapResult = await (await mapResponse).json();
  expect(mapResult.location).not.toEqual(second);
  await expect(panel.getByLabel('Широта места')).toHaveValue(String(mapResult.location.latitude));
  await expect(panel.getByLabel('Долгота места')).toHaveValue(String(mapResult.location.longitude));
  await expect(page.getByLabel('Выбранное место')).toBeVisible();
});

for (const width of [1440, 390, 360]) test(`Local unavailable, real recovery and responsive layout at ${width}px`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width, height: 1000 });
  await page.goto('/district');
  const panel = page.getByRole('region', { name: 'MESTO Local', exact: true });
  await panel.getByLabel('Широта места').fill('0');
  await panel.getByLabel('Долгота места').fill('0');
  await panel.getByRole('button', { name: 'Оценить место', exact: true }).click();
  await expect(panel.getByText('Точка вне поддерживаемой территории Красноярска.')).toBeVisible();
  await expect(panel.locator('[aria-label^="MESTO Local:"]')).toHaveCount(0);
  await panel.getByLabel('Широта места').fill(String(first.latitude));
  await panel.getByLabel('Долгота места').fill(String(first.longitude));
  await panel.getByRole('button', { name: 'Оценить место', exact: true }).click();
  await expect(panel.locator('[aria-label^="MESTO Local:"]')).toBeVisible();
  await expect(panel.getByText('Объективная оценка конкретного места', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const bounds = await panel.boundingBox();
  expect(bounds!.width).toBeLessThanOrEqual(width);
  expect(await panel.getByLabel('Широта места').evaluate(el => getComputedStyle(el).colorScheme)).toBe('light');
  await expect(page.getByRole('application').getByRole('button', { name: 'Map marker', exact: true }).first()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath(`local-${width}.png`), fullPage: true });
});

test('Parks inside and unnamed evidence presentation', async ({ page, request }) => {
  const response = await request.post(`${api}/api/analytics/local`, { data: first });
  const fixture = await response.json();
  const park = fixture.components.parks;
  park.nearest = { ...park.nearest, name: null, osm_type: 'way', distance_m: 0 };
  park.distance_m = 0; park.inside_geometry = true;
  await page.route(`${api}/api/analytics/local`, route => route.fulfill({ json: fixture }));
  await page.goto('/district');
  const panel = page.getByRole('region', { name: 'MESTO Local', exact: true });
  await panel.getByLabel('Широта места').fill(String(first.latitude));
  await panel.getByLabel('Долгота места').fill(String(first.longitude));
  await panel.getByRole('button', { name: 'Оценить место', exact: true }).click();
  await expect(panel.getByText('Выбранная точка находится внутри парка или на его границе.')).toBeVisible();
  await expect(panel.getByText('~0 м · Объект без названия')).toBeVisible();
});

test('API failure and retry clear stale score without any legacy fallback', async ({ page }) => {
  let calls = 0;
  await page.route(`${api}/api/analytics/local`, route => ++calls === 1 ? route.fulfill({ status: 503, json: {} }) : route.continue());
  await page.goto('/district');
  const panel = page.getByRole('region', { name: 'MESTO Local', exact: true });
  await panel.getByLabel('Широта места').fill(String(first.latitude));
  await panel.getByLabel('Долгота места').fill(String(first.longitude));
  await panel.getByRole('button', { name: 'Оценить место', exact: true }).click();
  await expect(panel.getByRole('alert')).toContainText('HTTP 503');
  await expect(panel.locator('[aria-label^="MESTO Local:"]')).toHaveCount(0);
  await panel.getByRole('button', { name: 'Повторить оценку места', exact: true }).click();
  await expect(panel.locator('[aria-label^="MESTO Local:"]')).toBeVisible();
});

test('malformed Local result is rejected instead of displaying a legacy score', async ({ page }) => {
  await page.route(`${api}/api/analytics/local`, route => route.fulfill({ json: { score: 99, version: 'future-signals-v4' } }));
  await page.goto('/district');
  const panel = page.getByRole('region', { name: 'MESTO Local', exact: true });
  await panel.getByLabel('Широта места').fill(String(first.latitude));
  await panel.getByLabel('Долгота места').fill(String(first.longitude));
  await panel.getByRole('button', { name: 'Оценить место', exact: true }).click();
  await expect(panel.getByRole('alert')).toContainText('некорректный результат');
  await expect(panel.locator('[aria-label^="MESTO Local:"]')).toHaveCount(0);
});
