import { expect, test, type Page } from '@playwright/test';
import type { OnboardingDraft } from '../frontend/lib/onboarding-store';
import type { DistrictScoreResponse } from '../frontend/types/analytics';

const api = 'http://127.0.0.1:18100';
const keys = ['stop_availability', 'school', 'kindergarten', 'healthcare', 'parks'];
const labels = ['Остановки', 'Школы', 'Детские сады', 'Медицина', 'Парки'];
// Plain test data: the E2E runner installs only root tooling, not frontend dependencies.
const initialDraft: OnboardingDraft = {
  name: '', household_type: 'single', adults_count: 1, children: [], housing_goal: 'compare',
  commute_minutes: null, purchase_budget: 0, initial_payment: 0, comfortable_monthly_payment: 0,
  rent_budget: 0, planning_horizon: '3_5_years', car_availability: false,
  transport_preferences: ['public_transport'], future_changes: [], home_values: [],
  good_home_text: '', data_processing_consent: false, life_points: [],
  preferences: Object.fromEntries(['education_weight', 'kindergarten_weight', 'healthcare_weight',
    'transport_weight', 'ecology_weight', 'safety_weight', 'parks_weight', 'shopping_weight',
    'entertainment_weight', 'housing_price_weight', 'future_growth_weight', 'quiet_active',
    'green_urban', 'center_calm', 'price_vs_time', 'today_vs_future', 'car_dependency']
    .map(key => [key, { value: null, is_answered: false, source: 'default', confidence: 0 }])) as OnboardingDraft['preferences'],
  partner: { name: '', work_point: null, transport_preferences: ['public_transport'], preferences: {}, life_goals: [] },
};
// Deliberately different values catch key/label swaps and a legacy-score fallback.
function fixture(): DistrictScoreResponse {
  return {
    id: 1, district: { id: 1, name: 'Тестовый район', slug: 'presentation-test' },
    score: 99, current_score: 99, future_score: 72, future_growth_score: 35,
    categories: { lifestyle: 99, infrastructure: 99, transport: 99, market: 99, future_growth: 35 },
    confidence: 1, reasons: ['legacy reason'], warnings: ['private/backend/path', 'Growth: реализация не гарантирована'],
    is_synthetic: false, calculation_version: 'objective-mesto-v2', created_at: '2026-10-07T00:00:00Z',
    future_factors: [], future_impacts: {}, external_signal_impacts: [],
    objective: {
      calculation_version: 'objective-mesto-v2', availability: 'AVAILABLE', score: 60.4, coverage: 1,
      components: Object.fromEntries(keys.map((key, i) => [key, {
        score: 40.4 + i * 10, normalization_version: 'test', sampling_version: 'test',
        evidence_version: 'test', eligibility_version: 'test', reference_id: 'test', reference_checksum: 'test',
        unavailable_reason: null, limitations: [], provenance: {},
      }])), weights: Object.fromEntries(keys.map(key => [key, .2])),
      unavailable_reason: null, limitations: [], provenance: {},
    },
  };
}

async function setup(page: Page, score: DistrictScoreResponse) {
  // Isolated presentation tests only. The separate smoke test uses the real APIs.
  await page.addInitScript(draft => {
    localStorage.setItem('mesto-onboarding-v2', JSON.stringify({ version: 1,
      state: { step: 9, draft, profileId: '00000000-0000-4000-8000-000000000001' } }));
  }, initialDraft);
  await page.route(`${api}/api/**`, async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/api/districts') return route.fulfill({ json: [{ ...score.district, is_synthetic: false }] });
    if (pathname === '/api/analytics/score') return route.fulfill({ json: [score] });
    if (pathname === '/api/recommendations') return route.fulfill({ json: { recommendations: [{
      rank: 1, district_id: 1, district_name: score.district.name, match_score: 81,
      district_score: 99, reasons: ['Персональная причина'], warnings: [],
    }] } });
    if (pathname === '/api/ai/district-summary') return route.fulfill({ status: 503, json: { detail: 'disabled' } });
    return route.fulfill({ json: [] });
  });
}

for (const viewport of [{ width: 1440, height: 1000 }, { width: 360, height: 800 }]) {
  test(`V2 components, separation and layout at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const score = fixture();
    score.district.name = 'Район с очень длинным названием ' + 'ПространственнаяТерритория'.repeat(5);
    await setup(page, score);
    await page.goto('/results');
    const objective = page.getByRole('region', { name: 'Объективная оценка территории', exact: true });
    await expect(objective.getByLabel('MESTO Score: 60 из 100', { exact: true })).toBeVisible();
    await expect(objective.getByRole('article')).toHaveCount(5);
    await expect(objective.getByText('Вес: 20%', { exact: true })).toHaveCount(5);
    for (let i = 0; i < labels.length; i++) {
      const component = objective.getByRole('article', { name: labels[i], exact: true });
      await expect(component.getByLabel(`${labels[i]}: ${40 + i * 10} из 100`, { exact: true })).toBeVisible();
      await expect(component.getByRole('meter')).toHaveAttribute('aria-valuenow', String(40.4 + i * 10));
    }
    await expect(objective.getByText('Инфраструктура', { exact: true })).toHaveCount(0);
    await expect(page.getByText('Прежний Match · MESTO Score 60/100', { exact: true })).toBeVisible();
    await expect(page.getByText('Прежний Match: 81/100.', { exact: false })).toBeVisible();
    await expect(page.getByText('Growth · развитие', { exact: true }).locator('..')).toContainText('35/100');
    await expect(page.getByText('Будущий сценарий', { exact: true }).first().locator('..')).toContainText('72/100');
    await expect(page.getByRole('heading', { name: 'Жильё в выбранном районе', exact: true })).toBeVisible();
    await expect(page.getByText('private/backend/path')).toHaveCount(0);
    await expect(page.getByText('Growth: реализация не гарантирована', { exact: true })).toBeVisible();
    await objective.getByText('Как считается MESTO Score', { exact: true }).focus();
    await page.keyboard.press('Enter');
    await expect(objective.getByText(/Показатели отражают пространственную близость/)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await objective.screenshot({ path: `test-results/objective-v2-${viewport.width}.png` });
  });
}

for (const state of ['unavailable', 'null-score', 'missing-objective', 'null-objective']) {
  test(`${state} never substitutes legacy score or zero`, async ({ page }) => {
    const score = fixture();
    if (state === 'unavailable') {
      score.objective!.availability = 'UNAVAILABLE';
      score.objective!.unavailable_reason = 'parks:component_snapshot_unavailable_or_invalid:/private/backend';
      score.objective!.components.parks.score = null;
    } else if (state === 'null-score') score.objective!.score = null;
    else if (state === 'missing-objective') delete score.objective;
    else score.objective = null;
    await setup(page, score);
    await page.goto('/results');
    const objective = page.getByRole('region', { name: 'Объективная оценка территории', exact: true });
    await expect(objective.getByRole('status')).toContainText('Объективная оценка временно недоступна');
    await expect(objective.getByLabel(/^MESTO Score:/)).toHaveCount(0);
    await expect(objective.getByRole('article')).toHaveCount(5);
    await expect(page.getByText('Прежний Match · MESTO Score —', { exact: true })).toBeVisible();
    await expect(page.getByText('private/backend', { exact: false })).toHaveCount(0);
    if (state === 'unavailable') await expect(objective.getByRole('article', { name: 'Парки', exact: true }).getByRole('meter')).toHaveCount(0);
  });
}

test('a real zero remains a valid score', async ({ page }) => {
  const score = fixture();
  score.objective!.score = 0;
  Object.values(score.objective!.components).forEach(component => { component.score = 0; });
  await setup(page, score);
  await page.goto('/results');
  await expect(page.getByLabel('MESTO Score: 0 из 100', { exact: true })).toBeVisible();
  await expect(page.getByRole('meter')).toHaveCount(5);
  await expect(page.getByText('Объективная оценка временно недоступна')).toHaveCount(0);
});

test('loading and failed API remain distinct from unavailable evidence; retry works', async ({ page }) => {
  const score = fixture();
  await setup(page, score);
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  let attempt = 0;
  await page.route(`${api}/api/analytics/score`, async route => {
    if (attempt++ === 0) { await pending; return route.fulfill({ status: 503, json: {} }); }
    return route.fulfill({ json: [score] });
  });
  await page.goto('/results');
  await expect(page.getByRole('status').filter({ hasText: 'Получаем персональный анализ' })).toBeVisible();
  release();
  await expect(page.getByRole('alert').filter({ hasText: 'Не удалось получить анализ' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Объективная оценка территории', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Повторить запрос', exact: true }).click();
  await expect(page.getByLabel('MESTO Score: 60 из 100', { exact: true })).toBeVisible();
});
