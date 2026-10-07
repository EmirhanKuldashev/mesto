import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';

const api = 'http://127.0.0.1:18100';
const endpoint = `${api}/api/analytics/mobility`;
const origin = { latitude: 56.01, longitude: 92.85 };
const destination = { latitude: 55.985, longitude: 92.9, label: 'Работа', kind: 'work' };
const tile = readFileSync(path.join(__dirname, 'fixtures/map-tile.png'));
const panel = (page: Page) => page.getByRole('region', { name: 'Важные места', exact: true });

async function selectOrigin(page: Page, point = origin) {
  const local = page.getByRole('region', { name: 'MESTO Local', exact: true });
  await local.getByLabel('Широта места').fill(String(point.latitude));
  await local.getByLabel('Долгота места').fill(String(point.longitude));
  await local.getByRole('button', { name: 'Оценить место', exact: true }).click();
}

async function setup(page: Page) {
  await page.goto('/district');
  await panel(page).getByRole('button', { name: 'Добавить важное место', exact: true }).click();
  await expect(panel(page).getByText('Сначала выберите исходную точку в MESTO Local или на карте.')).toBeVisible();
  await expect(panel(page).getByRole('button', { name: 'Рассчитать поездку', exact: true })).toBeDisabled();
  await selectOrigin(page);
  await panel(page).getByLabel('Широта важного места').fill(String(destination.latitude));
  await panel(page).getByLabel('Долгота важного места').fill(String(destination.longitude));
}

test.beforeEach(async ({ context }) => {
  await context.route('https://tile.openstreetmap.org/**', route => route.fulfill({ contentType: 'image/png', body: tile }));
});

for (const width of [1440, 390, 360]) test(`real road route, PT blocked and responsive Mobility at ${width}px`, async ({ page, request }, testInfo) => {
  await page.setViewportSize({ width, height: 1000 });
  const response = await request.post(endpoint, { data: { origin, destination, mode: 'car' } });
  expect(response.status()).toBe(200);
  const expected = await response.json();
  expect(expected.availability).toBe('AVAILABLE');
  expect(expected.distance_meters).toBe(6354.7);
  expect(expected.duration_seconds).toBe(634.5);
  expect(expected.traffic).toBe('not_included');
  expect(expected.provider_version).toBe('osrm-5.27.1/car-v1');
  await setup(page);
  await panel(page).getByRole('button', { name: 'Рассчитать поездку', exact: true }).focus();
  const routed = page.waitForResponse(r => r.url() === endpoint);
  await page.keyboard.press('Enter');
  expect((await routed).status()).toBe(200);
  await expect(panel(page).getByLabel('Результат поездки')).toContainText('11 мин');
  await expect(panel(page).getByLabel('Результат поездки')).toContainText('6,4 км');
  await expect(panel(page).getByText('Расчётное время без учёта текущих пробок.', { exact: false })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await panel(page).scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath(`mobility-car-${width}.png`) });
  await panel(page).getByRole('button', { name: 'Общественный транспорт', exact: true }).click();
  await expect(panel(page).getByText('Расчёт общественного транспорта пока недоступен: нет подтверждённого источника маршрутов и расписаний.')).toBeVisible();
  await expect(panel(page).getByLabel('Результат поездки')).toHaveCount(0);
  await panel(page).getByRole('button', { name: 'На машине', exact: true }).click();
  await expect(panel(page).getByLabel('Результат поездки')).toBeVisible();
  await panel(page).getByLabel('Долгота важного места').fill('0');
  await expect(panel(page).getByLabel('Результат поездки')).toHaveCount(0);
  await panel(page).getByRole('button', { name: 'Рассчитать поездку', exact: true }).click();
  await expect(panel(page).getByText('Одна из точек вне поддерживаемой территории Красноярска и ближайших окрестностей.')).toBeVisible();
  await expect(panel(page).getByLabel('Результат поездки')).toHaveCount(0);
});

test('changed origin reroutes and metadata editing clears stale values', async ({ page }) => {
  await setup(page);
  await panel(page).getByRole('button', { name: 'Рассчитать поездку', exact: true }).click();
  await expect(panel(page).getByLabel('Результат поездки')).toContainText('11 мин');
  const changed = page.waitForResponse(r => r.url() === endpoint);
  await selectOrigin(page, { latitude: 56.02, longitude: 92.90 });
  const result = await (await changed).json();
  expect(result.origin).toEqual({ latitude: 56.02, longitude: 92.90 });
  expect(result.availability).toBe('AVAILABLE');
  expect(result.distance_meters).not.toBe(6354.7);
  await expect(panel(page).getByLabel('Результат поездки')).toContainText(`${Math.ceil(result.duration_seconds / 60)} мин`);
  await panel(page).getByLabel('Название важного места').fill('Университет');
  await expect(panel(page).getByLabel('Результат поездки')).toHaveCount(0);
  await panel(page).getByLabel('Тип важного места').selectOption('university');
  await panel(page).getByRole('button', { name: 'Рассчитать поездку', exact: true }).click();
  await expect(panel(page).getByText('Университет', { exact: true }).last()).toBeVisible();
  await expect(panel(page).getByLabel('Результат поездки')).toContainText(`${Math.ceil(result.duration_seconds / 60)} мин`);
});

test('API error, malformed response and real recovery without metric fallback', async ({ page }) => {
  let calls = 0;
  await page.route(endpoint, route => {
    calls++;
    if (calls === 1) return route.fulfill({ status: 503, json: {} });
    if (calls === 2) return route.fulfill({ json: { version: 'mobility-v1', duration_seconds: 600, distance_meters: 4000 } });
    return route.continue();
  });
  await setup(page);
  await panel(page).getByRole('button', { name: 'Рассчитать поездку', exact: true }).click();
  await expect(panel(page).getByRole('alert')).toContainText('HTTP 503');
  await expect(panel(page).getByLabel('Результат поездки')).toHaveCount(0);
  await panel(page).getByRole('button', { name: 'Повторить расчёт поездки', exact: true }).click();
  await expect(panel(page).getByRole('alert')).toContainText('некорректный результат');
  await expect(panel(page).getByLabel('Результат поездки')).toHaveCount(0);
  await panel(page).getByRole('button', { name: 'Повторить расчёт поездки', exact: true }).click();
  await expect(panel(page).getByLabel('Результат поездки')).toBeVisible();
  expect(calls).toBe(3);
});

test('pending response cannot restore a stale route after destination edit', async ({ page, request }) => {
  const response = await request.post(endpoint, { data: { origin, destination, mode: 'car' } });
  const recorded = await response.json();
  let release: () => void = () => {};
  const held = new Promise<void>(resolve => { release = resolve; });
  let calls = 0;
  await page.route(endpoint, async route => {
    if (++calls === 1) { await held; await route.fulfill({ json: recorded }).catch(() => {}); }
    else await route.continue();
  });
  await setup(page);
  await panel(page).getByRole('button', { name: 'Рассчитать поездку', exact: true }).click();
  await expect(panel(page).getByText('Рассчитываем маршрут…')).toBeVisible();
  await panel(page).getByLabel('Долгота важного места').fill('92.91');
  release();
  await expect(panel(page).getByLabel('Результат поездки')).toHaveCount(0);
  await expect(panel(page).getByText('Рассчитываем маршрут…')).toHaveCount(0);
  await panel(page).getByRole('button', { name: 'Рассчитать поездку', exact: true }).click();
  await expect(panel(page).getByLabel('Результат поездки')).toBeVisible();
});

test('provider-neutral factual result allows optional geometry and snaps', async ({ page, request }) => {
  const response = await request.post(endpoint, { data: { origin, destination, mode: 'car' } });
  const factual = await response.json();
  // The public DTO permits providers that do not report route geometry/snaps.
  // Metrics remain from the recorded real engine response.
  factual.geometry = factual.origin_snap = factual.destination_snap = null;
  await page.route(endpoint, route => route.fulfill({ json: factual }));
  await setup(page);
  await panel(page).getByRole('button', { name: 'Рассчитать поездку', exact: true }).click();
  await expect(panel(page).getByLabel('Результат поездки')).toContainText('11 мин');
  await expect(panel(page).getByLabel('Результат поездки')).toContainText('6,4 км');
});
