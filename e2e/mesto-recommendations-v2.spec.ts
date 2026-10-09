import {expect,test} from '@playwright/test';
import type {OnboardingDraft} from '../frontend/lib/onboarding-store';
import {emptyMatchSettings} from '../frontend/lib/match-profile';
import {validMatchResponse} from '../frontend/lib/api/recommendations-v2';

const api='http://127.0.0.1:18100';
// Plain fixture: CI installs root E2E tooling, not host frontend dependencies.
const initialDraft:OnboardingDraft={name:'',household_type:'single',adults_count:1,children:[],housing_goal:'buy',
  commute_minutes:null,purchase_budget:8000000,initial_payment:0,comfortable_monthly_payment:0,rent_budget:0,
  planning_horizon:'3_5_years',car_availability:false,transport_preferences:['public_transport'],future_changes:[],
  home_values:[],good_home_text:'',data_processing_consent:false,life_points:[],match_v2:emptyMatchSettings(),
  partner:{name:'',work_point:null,transport_preferences:['public_transport'],preferences:{},life_goals:[]},
  preferences:Object.fromEntries(['education_weight','kindergarten_weight','healthcare_weight','transport_weight','ecology_weight',
    'safety_weight','parks_weight','shopping_weight','entertainment_weight','housing_price_weight','future_growth_weight',
    'quiet_active','green_urban','center_calm','price_vs_time','today_vs_future','car_dependency']
    .map(k=>[k,{value:null,is_answered:false,source:'default',confidence:0}])) as OnboardingDraft['preferences']};
const profile={version:'personal-match-v2',housing_goal:'buy',weights:{infrastructure:1,mobility:0,affordability:0},
  infrastructure:{stop:1,school:1,kindergarten:1,healthcare:1,parks:1},mode:'car',trips:[],frequency_weighting_confirmed:false,maximum_budget:8000000,comfortable_price:null,max_distance_m:{}};
test('real batch API has separate buckets, counts, canonical objective and stable results',async({request})=>{
  const response=await request.post(`${api}/api/recommendations/v2`,{data:{profile}});
  expect(response.status()).toBe(200);const data=await response.json();
  expect(data.version).toBe('match-recommendations-v2');expect(data.sample.count).toBe(108);
  expect(validMatchResponse(data)).toBe(true);
  expect(validMatchResponse({...data,candidates:[{...data.candidates[0],domains:{}}]})).toBe(false);
  expect(validMatchResponse({...data,candidates:[{...data.candidates[0],constraints:[{key:'budget',status:'PASS',actual:{bad:true},limit:1,reason:null}]}]})).toBe(false);
  expect(data.sample.complete_apartment_market).toBe(false);expect(data.districts).toHaveLength(7);
  expect(data.candidates.some((c:any)=>c.bucket==='verified')).toBe(true);
  expect(data.candidates.some((c:any)=>c.bucket==='failed')).toBe(true);
  expect(data.candidates.some((c:any)=>c.bucket==='unknown')).toBe(true);
  for(const c of data.candidates){
    expect(c.score).toBe(c.domains.infrastructure.score);
    expect(c.objective_district.score).not.toBeNull();
    if(c.bucket==='verified'){expect(c.eligibility).toBe('PASS');expect(c.score).not.toBeNull();}
  }
  const repeat=await request.post(`${api}/api/recommendations/v2`,{data:{profile}});
  expect(await repeat.json()).toEqual(data);
  const point=await request.post(`${api}/api/recommendations/v2`,{data:{profile,point:{latitude:56.01,longitude:92.85}}});
  const location=await point.json();expect(location.candidates[0].price_from).toBeNull();expect(location.candidates[0].eligibility).toBe('UNKNOWN');
  const legacy=await request.post(`${api}/api/analytics/match-v2`,{data:{candidate:{latitude:56.01,longitude:92.85},profile:{infrastructure:profile.infrastructure}}});
  expect((await legacy.json()).overall_match).toBeNull();
});

for(const width of [1440,390])test(`shared profile, real recommendations and comparison at ${width}px`,async({page})=>{
  await page.setViewportSize({width,height:1000});
  await page.addInitScript(draft=>{if(!localStorage.getItem('mesto-onboarding-v2'))localStorage.setItem('mesto-onboarding-v2',JSON.stringify({state:{step:9,profileId:null,draft},version:2}));},
    {...initialDraft,housing_goal:'buy',purchase_budget:8000000,match_v2:{...initialDraft.match_v2!,infrastructure:profile.infrastructure,domains:{infrastructure:3,mobility:0,affordability:0}}});
  await page.goto('/results');const panel=page.getByRole('region',{name:'Match V2 рекомендации',exact:true});
  await panel.getByLabel('Включить Match V2').check();
  const response=page.waitForResponse(r=>r.url()===`${api}/api/recommendations/v2`);
  await panel.getByRole('button',{name:'Рассчитать Match V2',exact:true}).click();expect((await response).status()).toBe(200);
  await expect(panel.getByRole('region',{name:'Проверенные варианты',exact:true})).toBeVisible();
  await expect(panel.getByRole('region',{name:'Непроверенные варианты',exact:true})).toBeVisible();
  await expect(panel.getByRole('region',{name:'Не подходят требованиям',exact:true})).toBeVisible();
  const choices=panel.getByRole('region',{name:'Проверенные варианты',exact:true}).getByRole('checkbox',{name:/Сравнить:/});
  await choices.nth(0).check();await choices.nth(1).check();
  await expect(panel.getByRole('region',{name:'Сравнение Match V2'})).toBeVisible();
  await panel.getByRole('link',{name:'Посмотреть сравнение (2)',exact:true}).first().click();
  await expect(panel.getByRole('heading',{name:'Сравнение на одинаковых предпочтениях',exact:true})).toBeInViewport();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await panel.getByRole('region',{name:'Проверенные варианты',exact:true}).locator('article').first()
    .screenshot({path:test.info().outputPath(`match-candidate-${width}.png`)});
  await panel.getByText('Уточнить общую анкету',{exact:true}).click();
  await panel.getByLabel('Приоритет: Школы',{exact:true}).selectOption('3');
  await expect(panel.getByRole('region',{name:'Проверенные варианты',exact:true})).toHaveCount(0);
  const stored=await page.evaluate(()=>JSON.parse(localStorage.getItem('mesto-onboarding-v2')!).state.draft.match_v2);
  expect(stored.infrastructure.school).toBe(3);
  await page.goto('/onboarding');
  await page.getByText('Настроить Match V2 — общий профиль рекомендаций',{exact:true}).click();
  await expect(page.getByLabel('Приоритет: Школы',{exact:true})).toHaveValue('3');
  await page.goto('/district');
  const foundation=page.getByRole('region',{name:'Ваши приоритеты',exact:true});
  await foundation.getByRole('button',{name:'Настроить приоритеты',exact:true}).click();
  await foundation.getByLabel('Важность: Школы',{exact:true}).selectOption('3');
  const mapped=page.getByRole('region',{name:'Match V2 рекомендации',exact:true});
  await mapped.getByLabel('Включить Match V2').check();
  await mapped.getByText('Уточнить общую анкету',{exact:true}).click();
  await expect(mapped.getByLabel('Приоритет: Школы',{exact:true})).toHaveValue('3');
  await mapped.getByLabel('Включить Match V2').uncheck();
  await expect(foundation).toBeVisible();
  await expect(foundation.getByLabel('Важность: Школы',{exact:true})).toHaveValue('3');
});

test('old drafts ask for explicit V2 priorities and never convert 90',async({page})=>{
  await page.addInitScript(draft=>localStorage.setItem('mesto-onboarding-v2',JSON.stringify({state:{step:9,profileId:null,draft},version:1})),
    {...initialDraft,match_v2:undefined,preferences:{...initialDraft.preferences,education_weight:{value:90,is_answered:true,source:'user',confidence:1}}});
  await page.goto('/results');const panel=page.getByRole('region',{name:'Match V2 рекомендации',exact:true});
  await panel.getByLabel('Включить Match V2').check();
  await expect(panel.getByLabel('Приоритет: Школы',{exact:true})).toHaveValue('');
  await expect(panel.getByLabel('Приоритет: Детские сады',{exact:true})).toHaveValue('');
});

test('new flow reports API failure, retries and discards an in-flight response after preferences change',async({page,request})=>{
  const response=await request.post(`${api}/api/recommendations/v2`,{data:{profile}});
  const data=await response.json();
  await page.addInitScript(draft=>{if(!localStorage.getItem('mesto-onboarding-v2'))localStorage.setItem('mesto-onboarding-v2',JSON.stringify({state:{step:9,profileId:null,draft},version:2}));},
    {...initialDraft,match_v2:{...emptyMatchSettings(),infrastructure:profile.infrastructure,domains:{infrastructure:3,mobility:0,affordability:0}}});
  await page.goto('/results');const panel=page.getByRole('region',{name:'Match V2 рекомендации',exact:true});
  await panel.getByLabel('Включить Match V2').check();
  await expect(page.getByRole('heading',{name:'Жильё в выбранном районе',exact:true})).toHaveCount(0);
  await page.route('**/api/recommendations/v2',r=>r.fulfill({status:500,body:'failure'}));
  await panel.getByRole('button',{name:'Рассчитать Match V2',exact:true}).click();
  await expect(panel.getByRole('alert')).toContainText('HTTP 500');
  await page.unroute('**/api/recommendations/v2');
  await panel.getByRole('button',{name:'Повторить',exact:true}).click();
  await expect(panel.getByRole('region',{name:'Проверенные варианты',exact:true})).toBeVisible();
  await page.route('**/api/recommendations/v2',async r=>{await new Promise(resolve=>setTimeout(resolve,900));await r.fulfill({json:data}).catch(()=>{});});
  const pending=page.waitForRequest('**/api/recommendations/v2');
  await panel.getByRole('button',{name:'Рассчитать Match V2',exact:true}).click();await pending;
  await panel.getByText('Уточнить общую анкету',{exact:true}).click();
  await panel.getByLabel('Приоритет: Парки',{exact:true}).selectOption('3');
  await page.waitForTimeout(1100);
  await expect(panel.getByRole('region',{name:'Проверенные варианты',exact:true})).toHaveCount(0);
  await panel.getByLabel('Включить Match V2').uncheck();
  await expect(page.getByRole('heading',{name:'Жильё в выбранном районе',exact:true})).toBeVisible();
});

test('rent and PT stay explicitly unavailable in the new UI',async({page})=>{
  const settings={...emptyMatchSettings(),infrastructure:profile.infrastructure,mode:'public_transport',
    domains:{infrastructure:1,mobility:1,affordability:0},frequency_weighting_confirmed:true,
    trips:{work:{importance:3,visits_per_week:5,comfortable_minutes:10,soft_limit_minutes:30,hard_limit_minutes:null}}};
  await page.addInitScript(draft=>{if(!localStorage.getItem('mesto-onboarding-v2'))localStorage.setItem('mesto-onboarding-v2',JSON.stringify({state:{step:9,profileId:null,draft},version:2}));},
    {...initialDraft,match_v2:settings,life_points:[{localId:'work',name:'Работа',type:'work',owner_type:'primary_user',latitude:56.01,longitude:92.85,importance:7,frequency_per_week:5}]});
  await page.goto('/results');const panel=page.getByRole('region',{name:'Match V2 рекомендации',exact:true});
  await panel.getByLabel('Включить Match V2').check();
  await panel.getByRole('button',{name:'Рассчитать Match V2',exact:true}).click();
  await expect(panel.getByText('Нет проверенного источника общественного транспорта.',{exact:true}).first()).toBeVisible();
  await expect(panel.getByRole('region',{name:'Проверенные варианты',exact:true}).locator('article')).toHaveCount(0);
  await panel.getByText('Уточнить общую анкету',{exact:true}).click();
  await panel.getByLabel('Сценарий жилья Match').selectOption('rent');
  await panel.getByRole('button',{name:'Рассчитать Match V2',exact:true}).click();
  await expect(panel.getByText('Для аренды и сравнения с арендой полный Match пока недоступен.',{exact:true}).first()).toBeVisible();
});
