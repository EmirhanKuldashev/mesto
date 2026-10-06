import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test } from '@playwright/test';
import { isPoi } from '../frontend/lib/poi-data';

const api = 'http://127.0.0.1:18100';
const frontend = 'http://127.0.0.1:3100';
const tile = readFileSync(path.join(__dirname, 'fixtures/map-tile.png'));

test('onboarding persists a profile and opens a recommended district and map', async ({ page, context, request }, testInfo) => {
  // Exercise the shared POI parser without changing the real API dataset.
  const poi = { id: 1, name: 'Школа №1', category: 'school', district_id: null,
    location: { type: 'Point', coordinates: [92.85, 56.01] }, source_id: 'osm', is_synthetic: false };
  expect(isPoi(poi)).toBe(true);
  expect(isPoi({ ...poi, name: null })).toBe(true);
  for (const name of [42, true, {}, undefined]) expect(isPoi({ ...poi, name })).toBe(false);
  expect(isPoi({ ...poi, name: null, is_synthetic: true })).toBe(false);
  const externalRequests: string[] = [];
  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  // Only the visual basemap is substituted. All MESTO API calls go to real services.
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin === api || url.origin === frontend) return route.continue();
    if (url.origin === 'https://tile.openstreetmap.org' && /^\/\d+\/\d+\/\d+\.png$/.test(url.pathname)) {
      return route.fulfill({ contentType: 'image/png', body: tile });
    }
    externalRequests.push(url.origin);
    return route.abort('blockedbyclient');
  });

  const health = await request.get(`${api}/health`);
  expect(health.status()).toBe(200);
  expect(await health.json()).toEqual({ status: 'ok', database: 'ok' });
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1, name: /Найди место, которое подойдёт/ })).toBeVisible();
  await page.getByRole('link', { name: 'Начать подбор', exact: true }).first().click();

  const step = async (heading: string) => {
    await expect(page.getByRole('heading', { level: 1, name: heading, exact: true })).toBeVisible();
  };
  const next = async () => page.getByRole('button', { name: 'Продолжить', exact: true }).click();
  await step('Кто будет жить в новом месте?');
  await page.getByRole('button', { name: /^Для себя/ }).click();
  await next();
  await step('Что вы планируете?');
  await page.getByRole('button', { name: /^Покупка/ }).click();
  await next();
  await step('Какой бюджет комфортен?');
  await page.getByRole('button', { name: '5–8 млн ₽', exact: true }).click();
  await next();
  await step('Сколько времени готовы тратить на дорогу?');
  await page.getByRole('button', { name: '30 минут', exact: true }).click();
  await next();
  await step('Как вы передвигаетесь?');
  await page.getByRole('button', { name: /^Пешком/ }).click();
  await page.getByRole('button', { name: /^Общественный/ }).click();
  await next();
  await step('Что для вас важно рядом?');
  await page.getByRole('button', { name: 'Школы и детсады', exact: true }).click();
  await page.getByRole('button', { name: 'Больше зелени', exact: true }).click();
  await next();
  await step('Какой ритм места вам ближе?');
  await next();
  await step('Что может измениться?');
  await page.getByRole('button', { name: 'Пока не знаю', exact: true }).click();
  await next();
  await step('Где ваши важные места?');
  await next();
  await step('Ваш сценарий готов');
  await page.getByRole('checkbox', { name: /^Согласен\(на\) на сохранение анкеты/ }).check();

  const responseFor = (endpoint: string) => page.waitForResponse(response =>
    response.url() === `${api}${endpoint}` && response.request().method() === 'POST');
  const profileResponse = responseFor('/api/profile');
  const analysisResponse = responseFor('/api/analysis/request');
  const scoreResponse = responseFor('/api/analytics/score');
  const recommendationsResponse = responseFor('/api/recommendations');
  const summaryResponse = responseFor('/api/ai/district-summary');
  await page.getByRole('button', { name: 'Показать моё место', exact: true }).click();

  const savedResponse = await profileResponse;
  expect(savedResponse.status()).toBe(201);
  const profile = await savedResponse.json();
  expect(profile.id).toMatch(/^[0-9a-f-]{36}$/);
  // A separate backend read proves the UI-created profile was persisted.
  const persistedResponse = await request.get(`${api}/api/profile/${profile.id}`);
  expect(persistedResponse.status()).toBe(200);
  const persisted = await persistedResponse.json();
  expect(persisted).toMatchObject({ id: profile.id, household_type: 'single', housing_goal: 'buy',
    purchase_budget: 8_000_000, commute_minutes: 30, transport_preferences: ['walking'],
    data_processing_consent: true });
  expect(persisted.preferences.parks_weight.is_answered).toBe(true);
  expect(persisted.preferences.education_weight.is_answered).toBe(true);
  const analysis = await analysisResponse;
  expect(analysis.status()).toBe(202);
  expect(await analysis.json()).toMatchObject({ profile_id: profile.id, status: 'pending' });

  const scored = await scoreResponse;
  expect(scored.status()).toBe(200);
  expect(scored.request().postDataJSON().profile_id).toBe(profile.id);
  const scores = await scored.json();
  await testInfo.attach('objective-v2-real-api', { body: JSON.stringify(scores, null, 2), contentType: 'application/json' });
  expect(scores.length).toBeGreaterThan(0);
  const recommended = await recommendationsResponse;
  expect(recommended.status()).toBe(200);
  expect(recommended.request().postDataJSON().profile_id).toBe(profile.id);
  const { recommendations } = await recommended.json();
  expect(recommendations.length).toBeGreaterThan(0);
  const best = recommendations[0];
  expect(best.profile_id).toBe(profile.id);
  expect(best.district_name).toBeTruthy();
  expect(best.match_score).toBeGreaterThanOrEqual(0);
  expect(best.match_score).toBeLessThanOrEqual(100);
  const score = scores.find((item: { district: { id: number } }) => item.district.id === best.district_id);
  expect(score).toBeDefined();
  expect(score.is_synthetic).toBe(false);
  expect(typeof score.score).toBe('number');
  expect(score.score).toBeGreaterThanOrEqual(0);
  expect(score.score).toBeLessThanOrEqual(100);
  const expected = { 'osm-centralny': 59.22, 'osm-kirovsky': 63.64, 'osm-leninsky': 57.67,
    'osm-oktyabrsky': 45.58, 'osm-sovetsky': 46.75, 'osm-sverdlovsky': 41.50, 'osm-zheleznodorozhny': 76.45 };
  expect(Object.fromEntries(scores.map((item: { district: { slug: string }; score: number }) => [item.district.slug, item.score]))).toEqual(expected);
  expect([...scores].sort((a, b) => b.score - a.score).map(item => item.district.slug)).toEqual([
    'osm-zheleznodorozhny', 'osm-kirovsky', 'osm-centralny', 'osm-leninsky', 'osm-sovetsky', 'osm-oktyabrsky', 'osm-sverdlovsky',
  ]);
  expect(score.objective.availability).toBe('AVAILABLE');
  expect(score.objective.score).toBe(score.score);
  expect(score.objective.weights).toEqual(Object.fromEntries(
    ['stop_availability', 'school', 'kindergarten', 'healthcare', 'parks'].map(key => [key, .2])));
  for (const item of scores) {
    expect(item.objective.availability).toBe('AVAILABLE');
    expect(item.objective.unavailable_reason).toBeNull();
    for (const component of Object.values(item.objective.components) as { score: number; unavailable_reason: string | null }[]) {
      expect(component.unavailable_reason).toBeNull();
      expect(component.score).toBeGreaterThanOrEqual(0);
      expect(component.score).toBeLessThanOrEqual(100);
    }
  }

  await expect(page).toHaveURL(`${frontend}/results`);
  await expect(page.getByRole('heading', { level: 1, name: /Ваши лучшие места/ })).toBeVisible();
  const card = page.getByRole('article').filter({ has: page.getByRole('heading', {
    level: 3, name: best.district_name, exact: true,
  }) });
  await expect(card).toHaveCount(1);
  await expect(card.getByText(/Match Score · MESTO Score \d+\/100/)).toBeVisible();
  const objective = page.getByRole('region', { name: 'Объективная оценка территории', exact: true });
  await expect(objective.getByLabel(`MESTO Score: ${Math.round(score.objective.score)} из 100`, { exact: true })).toBeVisible();
  for (const [key, label] of [['stop_availability', 'Остановки'], ['school', 'Школы'],
    ['kindergarten', 'Детские сады'], ['healthcare', 'Медицина'], ['parks', 'Парки']]) {
    await expect(objective.getByRole('article', { name: label, exact: true }).getByRole('meter'))
      .toHaveAttribute('aria-valuenow', String(score.objective.components[key].score));
  }
  // No Orca key: the real backend returns 503 and recommendations remain usable.
  expect((await summaryResponse).status()).toBe(503);
  const ai = page.getByRole('region', { name: 'Персональная ИИ-сводка', exact: true });
  await expect(ai.getByRole('alert')).toContainText('ИИ-сводка пока недоступна');
  await card.getByRole('link', { name: 'Район на карте', exact: true }).click();
  await expect(page).toHaveURL(`${frontend}/district?districtId=${best.district_id}`);
  await expect(page.getByRole('heading', { level: 1, name: /Город и ваши приоритеты/ })).toBeVisible();
  await expect(page.getByRole('heading', { level: 2, name: best.district_name, exact: true }).first()).toBeVisible();
  await expect(page.getByText('Объективная оценка территории', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('region', { name: 'Объективная оценка территории', exact: true })
    .getByLabel(`MESTO Score: ${Math.round(score.objective.score)} из 100`, { exact: true })).toBeVisible();
  const map = page.getByRole('application', { name: 'Карта административных районов и оценок ЖК', exact: true });
  await expect(map).toBeVisible();
  await expect(map.locator('canvas')).toBeVisible();
  await expect(page.getByRole('alert').filter({ hasText: /Не удалось получить оценку|Не удалось загрузить/ })).toHaveCount(0);

  // Verify the reported district through the real saved profile and API on both
  // screens. These assertions fail if bootstrap leaves V2 unavailable.
  const target = scores.find(item => item.district.slug === 'osm-zheleznodorozhny');
  expect(target.objective.score).toBe(76.45);
  await page.goto('/results');
  const targetCard = page.getByRole('article').filter({ has: page.getByRole('heading', {
    level: 3, name: target.district.name, exact: true,
  }) });
  await expect(targetCard).toHaveCount(1);
  await expect(targetCard.getByText('Match Score · MESTO Score 76/100', { exact: true })).toBeVisible();
  await targetCard.getByRole('button').click();
  const assertTarget = async () => {
    const region = page.getByRole('region', { name: 'Объективная оценка территории', exact: true });
    await expect(region.getByLabel('MESTO Score: 76 из 100', { exact: true })).toBeVisible();
    for (const [key, label, rounded] of [['stop_availability', 'Остановки', 71], ['school', 'Школы', 79],
      ['kindergarten', 'Детские сады', 78], ['healthcare', 'Медицина', 83], ['parks', 'Парки', 72]] as const) {
      const article = region.getByRole('article', { name: label, exact: true });
      await expect(article.getByLabel(`${label}: ${rounded} из 100`, { exact: true })).toBeVisible();
      await expect(article.getByRole('meter')).toHaveAttribute('aria-valuenow', String(target.objective.components[key].score));
    }
  };
  await assertTarget();
  await page.getByRole('region', { name: 'Объективная оценка территории', exact: true })
    .screenshot({ path: testInfo.outputPath('objective-v2-results.png') });
  await page.goto(`${frontend}/district?districtId=${target.district.id}`);
  await assertTarget();
  await page.getByRole('region', { name: 'Объективная оценка территории', exact: true })
    .screenshot({ path: testInfo.outputPath('objective-v2-district.png') });
  expect(externalRequests).toEqual([]);
  expect(pageErrors).toEqual([]);
});
