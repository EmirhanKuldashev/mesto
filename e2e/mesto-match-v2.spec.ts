import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';

const api = 'http://127.0.0.1:18100';
const endpoint = `${api}/api/analytics/match-v2`;
const origin = { latitude: 56.01, longitude: 92.85 };
const panel = (page: Page) => page.getByRole('region', { name: 'Ваши приоритеты', exact: true });
const result = (page: Page) => panel(page).getByLabel('Результат предпочтений');
const tile = readFileSync(path.join(__dirname, 'fixtures/map-tile.png'));

async function setup(page: Page) {
  await page.goto('/district');
  const local = page.getByRole('region', { name: 'MESTO Local', exact: true });
  await local.getByLabel('Широта места').fill(String(origin.latitude));
  await local.getByLabel('Долгота места').fill(String(origin.longitude));
  await local.getByRole('button', { name: 'Оценить место', exact: true }).click();
  await panel(page).getByRole('button', { name: 'Настроить приоритеты', exact: true }).click();
}

async function priorities(page: Page, values = ['1','3','3','2','2']) {
  for (const [i,name] of ['Остановки','Школы','Детские сады','Медицина','Парки'].entries()) {
    await panel(page).getByLabel(`Важность: ${name}`, { exact: true }).selectOption(values[i]);
  }
}

async function calculate(page: Page) {
  const response = page.waitForResponse(r => r.url() === endpoint);
  await panel(page).getByRole('button', { name: 'Проверить предпочтения', exact: true }).click();
  const r = await response; expect(r.status()).toBe(200); return r.json();
}

test.beforeEach(async ({ context }) => {
  await context.route('https://tile.openstreetmap.org/**', route => route.fulfill({ contentType: 'image/png', body: tile }));
});

for (const width of [1440,390,360]) test(`experimental Infrastructure Fit and preserved Local at ${width}px`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width,height:1000 });
  await setup(page); await priorities(page);
  const expected = await calculate(page);
  expect(expected.overall_match).toBeNull(); expect(expected.research_gate).toBe('B');
  expect(expected.personal_fit.infrastructure.availability).toBe('AVAILABLE');
  await expect(result(page)).toContainText(`${Math.round(expected.personal_fit.infrastructure.score)} / 100`);
  await expect(result(page)).toContainText('Очень важно');
  await expect(page.getByRole('region',{ name:'MESTO Local',exact:true })).toContainText('Объективная оценка конкретного места');
  await expect(page.getByLabel(`MESTO Local: ${Math.round(expected.objective.mesto_local.score)} из 100`,{ exact:true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await panel(page).scrollIntoViewIfNeeded();
  await page.screenshot({ path:testInfo.outputPath(`match-v2-${width}.png`) });
  await priorities(page,['0','0','0','0','0']);
  await expect(result(page)).toHaveCount(0); await calculate(page);
  await expect(result(page)).toContainText('Все факторы исключены. Оценка не рассчитана.');
  await panel(page).getByLabel('Важность: Школы',{ exact:true }).selectOption('');
  await calculate(page); await expect(result(page)).toContainText('Укажите важность всех пяти факторов');
});

test('CAR threshold compatibility, excluded destination and explicit blocked PT', async ({ page }) => {
  await setup(page); await priorities(page);
  await panel(page).getByText('Поездки и бюджет — необязательно',{ exact:true }).click();
  await panel(page).getByRole('button',{ name:'Добавить поездку',exact:true }).click();
  await panel(page).getByLabel('Название поездки 1').fill('Работа');
  await panel(page).getByLabel('Широта поездки 1').fill('55.985');
  await panel(page).getByLabel('Долгота поездки 1').fill('92.9');
  await panel(page).getByLabel('Допустимое время поездки 1').fill('25');
  const expected = await calculate(page);
  expect(expected.personal_fit.mobility.destinations[0].route.duration_seconds).toBe(634.5);
  await expect(result(page)).toContainText('11 мин на машине');
  await expect(result(page)).toContainText('Укладывается в ваши 25 мин.');
  await panel(page).getByLabel('Допустимое время поездки 1').fill('5');
  await expect(result(page)).toHaveCount(0); await calculate(page);
  await expect(result(page)).toContainText('Не укладывается в ваши 5 мин.');
  await panel(page).getByLabel('Транспорт для предпочтений').selectOption('public_transport'); await calculate(page);
  await expect(result(page)).toContainText('Нет подтверждённого источника маршрутов и расписаний');
  await expect(result(page)).toContainText('Infrastructure Fit');
  await expect(result(page)).not.toContainText('11 мин');
  await panel(page).getByLabel('Важность поездки 1').selectOption('0'); await calculate(page);
  await expect(result(page)).toContainText('Поездка исключена из проверки.');
});

test('observed candidate price bound to its own anchor and optional budget', async ({ page,request }) => {
  const catalog = await (await request.get(`${api}/api/residential-complexes?source_id=cian`)).json();
  const candidate = catalog.find((c: { price_from: number | null; location: unknown }) => c.price_from && c.location);
  expect(candidate).toBeTruthy();
  await setup(page); await priorities(page);
  await panel(page).getByText('Поездки и бюджет — необязательно',{ exact:true }).click();
  await panel(page).getByLabel('Бюджет покупки для места').fill(String(candidate.price_from + 1000000));
  await expect(panel(page).getByLabel('ЖК для проверки бюджета').locator(`option[value="${candidate.id}"]`)).toHaveCount(1);
  await panel(page).getByLabel('ЖК для проверки бюджета').selectOption(String(candidate.id));
  const expected = await calculate(page);
  expect(expected.candidate).toEqual({ latitude:candidate.location.coordinates[1],longitude:candidate.location.coordinates[0] });
  expect(expected.personal_fit.affordability.within_budget).toBe(true);
  await expect(result(page)).toContainText('В пределах бюджета');
  await expect(result(page)).toContainText('не цена сделки');
  await panel(page).getByLabel('Бюджет покупки для места').fill(String(candidate.price_from - 1)); await calculate(page);
  await expect(result(page)).toContainText('Выше бюджета');
});

test('API errors, malformed result and retry never show fabricated fit', async ({ page }) => {
  let calls = 0;
  await page.route(endpoint,route => {
    calls++;
    if(calls === 1) return route.fulfill({ status:503,json:{} });
    if(calls === 2) return route.fulfill({ json:{ version:'match-v2-foundation-v1',overall_match:91 } });
    return route.continue();
  });
  await setup(page); await priorities(page);
  await panel(page).getByRole('button',{ name:'Проверить предпочтения',exact:true }).click();
  await expect(panel(page).getByRole('alert')).toContainText('HTTP 503');
  await expect(result(page)).toHaveCount(0);
  await panel(page).getByRole('button',{ name:'Повторить проверку предпочтений',exact:true }).click();
  await expect(panel(page).getByRole('alert')).toContainText('некорректный результат');
  await expect(result(page)).toHaveCount(0);
  await panel(page).getByRole('button',{ name:'Повторить проверку предпочтений',exact:true }).click();
  await expect(result(page)).toContainText('Infrastructure Fit');
});

test('preference edit cancels pending result and cannot restore stale fit', async ({ page,request }) => {
  const recorded = await (await request.post(endpoint,{ data:{ candidate:origin,profile:{ infrastructure:{ stop:1,school:3,kindergarten:3,healthcare:2,parks:2 } } } })).json();
  let release: () => void = () => {};
  const held = new Promise<void>(resolve => { release = resolve; });
  let calls = 0;
  await page.route(endpoint,async route => {
    if (++calls===1) { await held; await route.fulfill({ json:recorded }).catch(() => {}); }
    else await route.continue();
  });
  await setup(page); await priorities(page);
  await panel(page).getByRole('button',{ name:'Проверить предпочтения',exact:true }).click();
  await expect(panel(page).getByRole('status')).toContainText('Проверяем');
  await panel(page).getByLabel('Важность: Парки',{ exact:true }).selectOption('0');
  release(); await expect(result(page)).toHaveCount(0);
  await calculate(page); await expect(result(page)).toContainText('Не важно');
});
